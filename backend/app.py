from functools import wraps
from pathlib import Path
import json
import os
import sqlite3
import traceback

from dotenv import load_dotenv
from flask import Flask, jsonify, request, send_file, send_from_directory, session
from flask_cors import CORS
from werkzeug.security import check_password_hash, generate_password_hash

from playlist_generator import generate_playlist
from spotify_service import enrich_playlist_with_spotify

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
            "SELECT id, username, created_at FROM users WHERE id = ?",
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
                "reason": song.get("reason") or ""
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
                "SELECT id, username, created_at FROM users WHERE id = ?",
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
    return jsonify({
        "status": "success",
        "user": {
            "id": user["id"],
            "username": user["username"],
            "created_at": user["created_at"],
        }
    })


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

        playlist = normalize_playlist(generate_playlist(mood, context, energy, intent))
        playlist = enrich_playlist_with_spotify(playlist)

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
