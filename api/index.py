from functools import wraps
import json
import os
import secrets
import sys
import time
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from dotenv import load_dotenv
from flask import Flask, jsonify, request, redirect
from flask_cors import CORS
from supabase import create_client

from models import db, User, Playlist
from playlist_generator import generate_playlist
from spotify_service import (
    build_listening_profile,
    build_spotify_auth_url,
    exchange_code_for_tokens,
    get_spotify_profile,
    refresh_user_token,
    spotify_is_configured,
)

load_dotenv(override=True)

app = Flask(__name__)

frontend_url = os.getenv("FRONTEND_URL")
if not frontend_url and os.getenv("VERCEL") == "1":
    frontend_url = "https://vibeweave-ai.vercel.app"
FRONTEND_URL = frontend_url or "http://localhost:5173"
CORS(app, supports_credentials=True)

spotify_redirect_uri = os.getenv("SPOTIFY_REDIRECT_URI")
if not spotify_redirect_uri:
    spotify_redirect_uri = f"{FRONTEND_URL}/api/spotify/callback"
SPOTIFY_REDIRECT_URI = spotify_redirect_uri

print(f"[Moodwave] FRONTEND_URL={FRONTEND_URL}")
print(f"[Moodwave] SPOTIFY_REDIRECT_URI={SPOTIFY_REDIRECT_URI}")

# ================= DB =================
db_url = os.getenv('DATABASE_URL') or os.getenv('POSTGRES_URL')

if not db_url:
    db_url = "sqlite:///:memory:"
elif db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql://", 1)

app.config['SQLALCHEMY_DATABASE_URI'] = db_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db.init_app(app)
with app.app_context():
    db.create_all()

# ================= SUPABASE =================
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

supabase = create_client(SUPABASE_URL, SUPABASE_KEY) if SUPABASE_URL and SUPABASE_KEY else None

# ================= UTILS =================
def safe_db_session():
    try:
        db.session.rollback()
    except Exception:
        pass

def error_response(msg, code):
    return jsonify({"status": "error", "message": msg}), code

def read_json():
    data = request.get_json(silent=True)
    if isinstance(data, str):
        data = json.loads(data)
    return data if isinstance(data, dict) else None

# ================= AUTH =================
def require_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth_header = request.headers.get("Authorization")
        if not auth_header or not auth_header.startswith("Bearer "):
            return error_response("Missing auth", 401)

        token = auth_header.split(" ")[1]

        try:
            user_res = supabase.auth.get_user(token)
            supabase_user = user_res.user
        except Exception:
            return error_response("Unauthorized", 401)

        if not supabase_user:
            return error_response("Unauthorized", 401)

        user = User(id=supabase_user.id, email=supabase_user.email)
        return f(user, *args, **kwargs)

    return decorated

# ================= SPOTIFY TOKEN SAVE =================
def save_spotify_tokens(user, token_payload, display_name=None):
    try:
        supabase.table("users").update({
            "spotify_access_token": token_payload.get("access_token"),
            "spotify_refresh_token": token_payload.get("refresh_token"),
            "spotify_display_name": display_name,
            "spotify_expires_at": int(time.time()) + token_payload.get("expires_in", 3600)
        }).eq("email", user.email).execute()
    except Exception as e:
        print("SAVE TOKEN ERROR:", str(e))

# ================= ROUTES =================

@app.route("/api/auth/me")
@require_auth
def me(user):
    try:
        res = supabase.table("users").select("*").eq("email", user.email).single().execute()

        print("FULL USER DATA:", res.data)

        spotify_connected = bool(res.data.get("spotify_access_token"))

        return jsonify({
            "status": "success",
            "user": {
                "id": user.id,
                "email": user.email,
                "spotify_connected": spotify_connected,
                "spotify_display_name": res.data.get("spotify_display_name")
            }
        })

    except Exception as e:
        print("ME ROUTE ERROR:", str(e))

        return jsonify({
            "status": "success",
            "user": {
                "id": user.id,
                "email": user.email,
                "spotify_connected": False,
                "spotify_display_name": None
            }
        })
    res = supabase.table("users").select("*").eq("id", user.id).single().execute()

    print("FULL USER DATA:", res.data)

    spotify_connected = bool(res.data.get("spotify_access_token"))

    return jsonify({
        "status": "success",
        "user": {
            "id": user.id,
            "email": user.email,
            "spotify_connected": spotify_connected,
            "spotify_display_name": res.data.get("spotify_display_name")
        }
    })

@app.route("/api/spotify/auth-url")
@require_auth
def spotify_auth_url(user):
    if not spotify_is_configured():
        return error_response(
            f"Spotify not configured. Ensure SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET are set. Expected redirect URI: {SPOTIFY_REDIRECT_URI}",
            400
        )

    state = f"{user.email}::{secrets.token_urlsafe(16)}"
    url = build_spotify_auth_url(SPOTIFY_REDIRECT_URI, state)
    if not url:
        return error_response(
            "Spotify auth URL could not be generated. Check SPOTIFY_CLIENT_ID, SPOTIFY_CLIENT_SECRET, and SPOTIFY_REDIRECT_URI.",
            500
        )

    app.logger.info(f"Spotify auth URL created for user {user.id} with redirect URI {SPOTIFY_REDIRECT_URI}")
    return jsonify({"status": "success", "url": url, "redirect_uri": SPOTIFY_REDIRECT_URI})


@app.route("/api/spotify/callback")
def spotify_callback():
    if request.args.get("error"):
        return redirect(f"{FRONTEND_URL}/?spotify=error")

    state = request.args.get("state")
    code = request.args.get("code")

    if not state or not code:
        return redirect(f"{FRONTEND_URL}/?spotify=error_state")

    try:
        user_email, _ = state.split("::", 1)

        token_payload = exchange_code_for_tokens(code, SPOTIFY_REDIRECT_URI)

        display_name = None
        try:
            profile = get_spotify_profile(token_payload["access_token"])
            display_name = profile.get("display_name") or profile.get("id")
        except Exception:
            pass

        user = User(email=user_email)
        save_spotify_tokens(user, token_payload, display_name)

        return redirect(f"{FRONTEND_URL}/?spotify=connected")

    except Exception as e:
        print("Spotify error:", str(e))
        traceback.print_exc()
        return redirect(f"{FRONTEND_URL}/?spotify=error_catch")


@app.route("/api/spotify/disconnect", methods=["POST"])
@require_auth
def spotify_disconnect(user):
    try:
        supabase.table("users").update({
            "spotify_access_token": None,
            "spotify_refresh_token": None,
            "spotify_display_name": None
        }).eq("email", user.email).execute()

        return jsonify({
            "status": "success",
            "message": "Spotify disconnected"
        })

    except Exception as e:
        print("Failed to disconnect Spotify:", str(e))
        return error_response("Failed to disconnect Spotify", 500)


@app.route("/api/generate-playlist", methods=["POST"])
@require_auth
def generate(user):
    data = read_json()

    if not data:
        return error_response("Invalid JSON", 400)

    spotify_profile = None

    try:
        # Get REAL database user
        res = supabase.table("users").select("*").eq(
            "email",
            user.email
        ).single().execute()

        db_user = res.data

        if not db_user:
            return error_response("User not found", 404)

        real_user_id = db_user["id"]

        access_token = db_user.get("spotify_access_token")
        refresh_token = db_user.get("spotify_refresh_token")

        if not access_token:
            return error_response(
                "Connect Spotify first",
                403
            )

        # Try current token
        try:
            spotify_profile = build_listening_profile(
                access_token
            )

        except Exception as e:
            print("ACCESS TOKEN FAILED:", str(e))

            # Refresh token flow
            if not refresh_token:
                return error_response(
                    "Spotify session expired. Reconnect Spotify.",
                    401
                )

            try:
                refreshed = refresh_user_token(
                    refresh_token
                )

                access_token = refreshed.get(
                    "access_token"
                )

                if refreshed.get("refresh_token"):
                    refresh_token = refreshed.get(
                        "refresh_token"
                    )

                # Save refreshed tokens
                supabase.table("users").update({
                    "spotify_access_token": access_token,
                    "spotify_refresh_token": refresh_token
                }).eq(
                    "email",
                    user.email
                ).execute()

                print("TOKEN REFRESH SUCCESS")

                # Retry Spotify fetch
                spotify_profile = build_listening_profile(
                    access_token
                )

            except Exception as refresh_error:
                print(
                    "REFRESH FAILED:",
                    str(refresh_error)
                )

                return error_response(
                    "Spotify refresh failed. Reconnect Spotify.",
                    401
                )

    except Exception as e:
        app.logger.error(
            f"Error fetching Spotify data: {str(e)}"
        )

        traceback.print_exc()

        return error_response(
            "Failed to load Spotify profile",
            500
        )

    if not spotify_profile:
        return error_response(
            "Connect Spotify first",
            403
        )

    try:
        # Generate playlist
        playlist = generate_playlist(
            data["mood"],
            data["context"],
            data["energy"],
            data["intent"],
            spotify_profile
        )

        # Save playlist
        supabase.table("playlists").insert({
            "user_id": real_user_id,

            "mood": data["mood"],
            "context": data["context"],
            "energy": data["energy"],
            "intent": data["intent"],

            "name": playlist["playlist_name"],
            "theme_description": playlist["theme_description"],
            "energy_curve": playlist["energy_curve"],

            "tags": playlist["tags"],
            "songs": playlist["songs"],

            "playlist_json": json.dumps(playlist)
        }).execute()

    except Exception as e:
        app.logger.error(
            f"Failed to generate playlist: {str(e)}"
        )

        traceback.print_exc()

        return error_response(
            "Failed to generate playlist. Please try again.",
            500
        )

    return jsonify({
        "status": "success",
        "playlist": playlist
    })
@app.route("/health")
def health():
    return jsonify({"status": "running"})

@app.route("/api/playlists", methods=["GET"])
@require_auth
def get_playlists(user):
    try:
        # Query all playlists for the given user from the database
        user_playlists = Playlist.query.filter_by(user_id=user.id).order_by(Playlist.created_at.desc()).all()
        playlists = []
        for p in user_playlists:
            playlists.append({
                "id": p.id,
                "mood": p.mood,
                "context": p.context,
                "energy": p.energy,
                "intent": p.intent,
                "created_at": p.created_at.isoformat(),
                "playlist": json.loads(p.playlist_json)
            })
        return jsonify({"status": "success", "playlists": playlists})
    except Exception as e:
        print("Failed to fetch playlists:", str(e))
        return jsonify({"status": "error", "message": str(e)}), 500


if __name__ == "__main__":
    app.run(debug=True)