from functools import wraps
from pathlib import Path
import json
import os
import secrets
import sqlite3
import time
import traceback

from dotenv import load_dotenv
from flask import Flask, jsonify, redirect, request, send_file, send_from_directory, session, url_for
from flask_cors import CORS
from werkzeug.security import check_password_hash, generate_password_hash

from playlist_generator import generate_playlist
from spotify_service import (
    build_listening_profile,
    build_spotify_auth_url,
    enrich_playlist_with_user_spotify,
    exchange_code_for_tokens,
    get_spotify_profile,
    refresh_user_token,
    spotify_is_configured,
)

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent
FRONTEND_FILE = BASE_DIR.parents[0] / "frontend" / "moodwave-kawaii.html"
ASSETS_DIR = BASE_DIR.parents[0] / "frontend" / "assets"
DB_PATH = Path(os.getenv("DATABASE_PATH", BASE_DIR / "data" / "moodwave.sqlite3"))
DATA_DIR = DB_PATH.parent

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "dev-secret-change-me")
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
)
CORS(app, supports_credentials=True)


def get_db():
    DATA_DIR.mkdir(exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with get_db() as db:
        db.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS playlists (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                mood TEXT NOT NULL,
                context TEXT NOT NULL,
                energy TEXT NOT NULL,
                intent TEXT NOT NULL,
                playlist_json TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            );
        """)
        ensure_user_column(db, "spotify_access_token", "TEXT")
        ensure_user_column(db, "spotify_refresh_token", "TEXT")
        ensure_user_column(db, "spotify_expires_at", "INTEGER")
        ensure_user_column(db, "spotify_display_name", "TEXT")


def ensure_user_column(db, column_name, column_type):
    columns = {
        row["name"]
        for row in db.execute("PRAGMA table_info(users)").fetchall()
    }
    if column_name not in columns:
        db.execute(f"ALTER TABLE users ADD COLUMN {column_name} {column_type}")


def error_response(message, status_code):
    return jsonify({
        "status": "error",
        "message": message
    }), status_code


def current_user():
    user_id = session.get("user_id")
    if not user_id:
        return None

    with get_db() as db:
        return db.execute(
            "SELECT * FROM users WHERE id = ?",
            (user_id,)
        ).fetchone()


def login_required(handler):
    @wraps(handler)
    def wrapped(*args, **kwargs):
        if not current_user():
            return error_response("Please log in first", 401)
        return handler(*args, **kwargs)

    return wrapped


def user_payload(user):
    return {
        "id": user["id"],
        "username": user["username"],
        "created_at": user["created_at"],
        "spotify_connected": bool(user["spotify_refresh_token"]),
        "spotify_display_name": user["spotify_display_name"],
    }


def normalize_playlist(playlist):
    songs = playlist.get("songs") or []

    return {
        "playlist_name": playlist.get("playlist_name") or "ur playlist",
        "theme_description": playlist.get("theme_description") or "",
        "energy_curve": playlist.get("energy_curve") or "",
        "tags": playlist.get("tags") or [],
        "songs": [
            {
                "title": song.get("title") or "",
                "artist": song.get("artist") or "",
                "energy": (song.get("energy") or "medium").lower(),
                "reason": song.get("reason") or "",
                "spotify_url": song.get("spotify_url"),
                "spotify_uri": song.get("spotify_uri"),
                "spotify_id": song.get("spotify_id"),
                "album_art": song.get("album_art"),
                "preview_url": song.get("preview_url"),
                "spotify_popularity": song.get("spotify_popularity"),
            }
            for song in songs
        ]
    }


def read_json():
    data = request.get_json(silent=True)
    if isinstance(data, str):
        data = json.loads(data)
    return data if isinstance(data, dict) else None


def playlist_row_payload(row):
    playlist = json.loads(row["playlist_json"])
    return {
        "id": row["id"],
        "mood": row["mood"],
        "context": row["context"],
        "energy": row["energy"],
        "intent": row["intent"],
        "created_at": row["created_at"],
        "playlist": playlist,
    }


def spotify_redirect_uri():
    configured = os.getenv("SPOTIFY_REDIRECT_URI")
    if configured:
        return configured

    return url_for("spotify_callback", _external=True)


def save_spotify_tokens(user_id, token_payload, display_name=None):
    expires_at = int(time.time()) + int(token_payload.get("expires_in", 3600))
    access_token = token_payload.get("access_token")
    refresh_token = token_payload.get("refresh_token")

    if not access_token:
        return

    with get_db() as db:
        if refresh_token:
            db.execute(
                """
                UPDATE users
                SET spotify_access_token = ?,
                    spotify_refresh_token = ?,
                    spotify_expires_at = ?,
                    spotify_display_name = COALESCE(?, spotify_display_name)
                WHERE id = ?
                """,
                (access_token, refresh_token, expires_at, display_name, user_id),
            )
        else:
            db.execute(
                """
                UPDATE users
                SET spotify_access_token = ?,
                    spotify_expires_at = ?,
                    spotify_display_name = COALESCE(?, spotify_display_name)
                WHERE id = ?
                """,
                (access_token, expires_at, display_name, user_id),
            )
        db.commit()


def spotify_access_token_for_user(user_id):
    with get_db() as db:
        user = db.execute(
            """
            SELECT spotify_access_token, spotify_refresh_token, spotify_expires_at
            FROM users
            WHERE id = ?
            """,
            (user_id,),
        ).fetchone()

    if not user or not user["spotify_refresh_token"]:
        return None

    if user["spotify_access_token"] and int(user["spotify_expires_at"] or 0) > time.time() + 60:
        return user["spotify_access_token"]

    try:
        refreshed = refresh_user_token(user["spotify_refresh_token"])
    except Exception as exc:
        print("Spotify refresh failed:", str(exc))
        return None

    save_spotify_tokens(user_id, refreshed)
    return refreshed.get("access_token")


def listening_profile_for_user(user_id):
    access_token = spotify_access_token_for_user(user_id)
    if not access_token:
        return None, None

    try:
        return build_listening_profile(access_token), access_token
    except Exception as exc:
        print("Spotify listening profile failed:", str(exc))
        return None, access_token


@app.route("/")
def frontend():
    if FRONTEND_FILE.exists():
        return send_file(FRONTEND_FILE)

    return error_response("Frontend file not found", 404)


@app.route("/assets/<path:filename>")
def frontend_assets(filename):
    return send_from_directory(ASSETS_DIR, filename)


@app.route("/api/auth/register", methods=["POST"])
def register():
    data = read_json()
    if not data:
        return error_response("Request body must be JSON", 400)

    username = str(data.get("username", "")).strip().lower()
    password = str(data.get("password", ""))

    if len(username) < 3:
        return error_response("Username must be at least 3 characters", 400)
    if len(password) < 6:
        return error_response("Password must be at least 6 characters", 400)

    try:
        with get_db() as db:
            cursor = db.execute(
                "INSERT INTO users (username, password_hash) VALUES (?, ?)",
                (username, generate_password_hash(password))
            )
            db.commit()
            session["user_id"] = cursor.lastrowid
            user = db.execute(
                "SELECT * FROM users WHERE id = ?",
                (cursor.lastrowid,)
            ).fetchone()
    except sqlite3.IntegrityError:
        return error_response("That username is already taken", 409)

    return jsonify({"status": "success", "user": user_payload(user)}), 201


@app.route("/api/auth/login", methods=["POST"])
def login():
    data = read_json()
    if not data:
        return error_response("Request body must be JSON", 400)

    username = str(data.get("username", "")).strip().lower()
    password = str(data.get("password", ""))

    with get_db() as db:
        user = db.execute(
            "SELECT * FROM users WHERE username = ?",
            (username,)
        ).fetchone()

    if not user or not check_password_hash(user["password_hash"], password):
        return error_response("Invalid username or password", 401)

    session["user_id"] = user["id"]
    return jsonify({"status": "success", "user": user_payload(user)})


@app.route("/api/auth/logout", methods=["POST"])
def logout():
    session.clear()
    return jsonify({"status": "success"})


@app.route("/api/auth/me")
def me():
    user = current_user()
    return jsonify({
        "status": "success",
        "user": user_payload(user) if user else None
    })


@app.route("/api/spotify/login")
@login_required
def spotify_login():
    if not spotify_is_configured():
        return error_response("Spotify credentials are not configured", 400)

    state = secrets.token_urlsafe(24)
    session["spotify_oauth_state"] = state

    auth_url = build_spotify_auth_url(spotify_redirect_uri(), state)
    if not auth_url:
        return error_response("Spotify credentials are not configured", 400)

    return redirect(auth_url)


@app.route("/api/spotify/callback")
@login_required
def spotify_callback():
    if request.args.get("error"):
        return redirect("/?spotify=error")

    state = request.args.get("state")
    expected_state = session.pop("spotify_oauth_state", None)
    if not state or state != expected_state:
        return error_response("Spotify login state did not match", 400)

    code = request.args.get("code")
    if not code:
        return error_response("Spotify authorization code missing", 400)

    try:
        token_payload = exchange_code_for_tokens(code, spotify_redirect_uri())
        profile = get_spotify_profile(token_payload["access_token"])
        display_name = profile.get("display_name") or profile.get("id")
        save_spotify_tokens(session["user_id"], token_payload, display_name)
    except Exception as exc:
        print("Spotify callback failed:", str(exc))
        return redirect("/?spotify=error")

    return redirect("/?spotify=connected")


@app.route("/api/spotify/status")
@login_required
def spotify_status():
    user = current_user()
    return jsonify({
        "status": "success",
        "spotify_connected": bool(user["spotify_refresh_token"]),
        "spotify_display_name": user["spotify_display_name"],
    })


@app.route("/api/spotify/disconnect", methods=["POST"])
@login_required
def spotify_disconnect():
    with get_db() as db:
        db.execute(
            """
            UPDATE users
            SET spotify_access_token = NULL,
                spotify_refresh_token = NULL,
                spotify_expires_at = NULL,
                spotify_display_name = NULL
            WHERE id = ?
            """,
            (session["user_id"],),
        )
        db.commit()

    return jsonify({"status": "success"})


@app.route("/generate-playlist", methods=["POST"])
@login_required
def generate():
    try:
        data = read_json()
        if data is None:
            return error_response("Request body must be JSON", 400)

        required_fields = ["mood", "context", "energy", "intent"]
        for field in required_fields:
            if not str(data.get(field, "")).strip():
                return error_response(f"Missing field: {field}", 400)

        mood = str(data["mood"]).strip()
        context = str(data["context"]).strip()
        energy = str(data["energy"]).strip()
        intent = str(data["intent"]).strip()

        spotify_profile, user_spotify_token = listening_profile_for_user(session["user_id"])
        playlist = normalize_playlist(
            generate_playlist(mood, context, energy, intent, spotify_profile)
        )
        playlist = enrich_playlist_with_user_spotify(playlist, user_spotify_token)

        with get_db() as db:
            cursor = db.execute(
                """
                INSERT INTO playlists
                    (user_id, mood, context, energy, intent, playlist_json)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    session["user_id"],
                    mood,
                    context,
                    energy,
                    intent,
                    json.dumps(playlist),
                )
            )
            db.commit()

        return jsonify({
            "status": "success",
            "playlist": playlist,
            "saved_id": cursor.lastrowid
        }), 200

    except Exception as exc:
        print("ERROR:", str(exc))
        traceback.print_exc()
        return error_response("Playlist generation failed. Try again in a moment.", 500)


@app.route("/api/playlists")
@login_required
def playlists():
    with get_db() as db:
        rows = db.execute(
            """
            SELECT * FROM playlists
            WHERE user_id = ?
            ORDER BY created_at DESC, id DESC
            LIMIT 20
            """,
            (session["user_id"],)
        ).fetchall()

    return jsonify({
        "status": "success",
        "playlists": [playlist_row_payload(row) for row in rows]
    })


@app.route("/api/playlists/<int:playlist_id>")
@login_required
def playlist_detail(playlist_id):
    with get_db() as db:
        row = db.execute(
            "SELECT * FROM playlists WHERE id = ? AND user_id = ?",
            (playlist_id, session["user_id"])
        ).fetchone()

    if not row:
        return error_response("Playlist not found", 404)

    return jsonify({"status": "success", "playlist": playlist_row_payload(row)})


@app.route("/api/playlists/<int:playlist_id>", methods=["DELETE"])
@login_required
def delete_playlist(playlist_id):
    with get_db() as db:
        cursor = db.execute(
            "DELETE FROM playlists WHERE id = ? AND user_id = ?",
            (playlist_id, session["user_id"])
        )
        db.commit()

    if cursor.rowcount == 0:
        return error_response("Playlist not found", 404)

    return jsonify({"status": "success"})


@app.route("/health")
def health():
    return jsonify({
        "status": "running",
        "message": "Playlist API is live"
    })


init_db()

if __name__ == "__main__":
    port = int(os.getenv("PORT", "5000"))
    app.run(host="0.0.0.0", port=port, debug=os.getenv("FLASK_DEBUG") == "1")
