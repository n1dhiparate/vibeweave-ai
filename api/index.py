from functools import wraps
import json
import os
import secrets
import sys
import time
import traceback
from pathlib import Path

# Vercel Serverless pathing fix
sys.path.insert(0, str(Path(__file__).resolve().parent))

from dotenv import load_dotenv
from flask import Flask, jsonify, request, redirect
from flask_cors import CORS
from supabase import create_client, Client

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

FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:5173")

# CORS setup for the React frontend
CORS(app, supports_credentials=True, origins=[FRONTEND_URL])

# Database Configuration
db_url = os.getenv('DATABASE_URL') or os.getenv('POSTGRES_URL')
if not db_url:
    print("WARNING: DATABASE_URL is missing. Using in-memory SQLite.", file=sys.stderr)
    db_url = "sqlite:///:memory:"
elif db_url.startswith("postgres://"):
    # SQLAlchemy requires postgresql:// instead of postgres://
    db_url = db_url.replace("postgres://", "postgresql://", 1)

app.config['SQLALCHEMY_DATABASE_URI'] = db_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db.init_app(app)

# Supabase Client
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
if not SUPABASE_URL or not SUPABASE_KEY:
    print("WARNING: Missing Supabase credentials in .env", file=sys.stderr)
    supabase = None
else:
    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# Ensure tables exist lazily
@app.before_request
def init_db():
    if getattr(app, '_database_initialized', False):
        return

    # 🔥 FIX: Skip DB init in serverless (Vercel)
    if os.getenv("VERCEL"):
        app._database_initialized = True
        return

    try:
        db.create_all()
    except Exception as e:
        print("WARNING: Database creation failed:", str(e), file=sys.stderr)

    app._database_initialized = True
def error_response(message, status_code):
    return jsonify({"status": "error", "message": message}), status_code

def read_json():
    data = request.get_json(silent=True)
    if isinstance(data, str):
        data = json.loads(data)
    return data if isinstance(data, dict) else None

def require_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth_header = request.headers.get("Authorization")
        if not auth_header or not auth_header.startswith("Bearer "):
            return error_response("Missing or invalid authorization header", 401)
        
        token = auth_header.split(" ")[1]
        try:
            user_res = supabase.auth.get_user(token)
            supabase_user = user_res.user
        except Exception as e:
            return error_response(f"Unauthorized: {str(e)}", 401)
            
        if not supabase_user:
            return error_response("Unauthorized", 401)
            
        user_id = supabase_user.id
        email = supabase_user.email
        
        # 🔥 FIX: Avoid DB query that crashes on Vercel
        user = None
        try:
             user = User.query.get(user_id)
        except Exception:
             pass

        if not user:
            try:
                user = User(id=user_id, email=email)
                db.session.add(user)
            
                try:
                    db.session.commit()
                except Exception:
                    safe_db_session()
            except Exception:
                # fallback if DB fails (serverless safe)
                user = User(id=user_id, email=email)

        return f(user, *args, **kwargs)
    return decorated

def save_spotify_tokens(user, token_payload, display_name=None):
    expires_at = int(time.time()) + int(token_payload.get("expires_in", 3600))
    access_token = token_payload.get("access_token")
    refresh_token = token_payload.get("refresh_token")

    if not access_token:
        return

    user.spotify_access_token = access_token
    user.spotify_expires_at = expires_at
    if refresh_token:
        user.spotify_refresh_token = refresh_token
    if display_name:
        user.spotify_display_name = display_name
        
    try:
        db.session.commit()
    except Exception:
        safe_db_session()

def spotify_access_token_for_user(user):
    if not user.spotify_refresh_token:
        return None

    if user.spotify_access_token and (user.spotify_expires_at or 0) > time.time() + 60:
        return user.spotify_access_token

    try:
        refreshed = refresh_user_token(user.spotify_refresh_token)
    except Exception as exc:
        print("Spotify refresh failed:", str(exc))
        return None

    save_spotify_tokens(user, refreshed)
    return refreshed.get("access_token")

def listening_profile_for_user(user):
    access_token = spotify_access_token_for_user(user)
    if not access_token:
        return None
    try:
        return build_listening_profile(access_token)
    except Exception as exc:
        print("Spotify listening profile failed:", str(exc))
        return None

def playlist_row_payload(playlist):
    pl_json = json.loads(playlist.playlist_json) if isinstance(playlist.playlist_json, str) else playlist.playlist_json
    return {
        "id": playlist.id,
        "mood": playlist.mood,
        "context": playlist.context,
        "energy": playlist.energy,
        "intent": playlist.intent,
        "created_at": playlist.created_at.isoformat() if playlist.created_at else None,
        "playlist": pl_json,
    }

def safe_db_session():
    try:
        db.session.rollback()
    except Exception:
        pass
# ==========================================
# ROUTES
# ==========================================

@app.route("/api/auth/me")
@require_auth
def me(user):
    return jsonify({
        "status": "success",
        "user": {
            "id": user.id,
            "email": user.email,
            "spotify_connected": bool(user.spotify_refresh_token),
            "spotify_display_name": user.spotify_display_name,
        }
    })

@app.route("/api/spotify/auth-url")
@require_auth
def spotify_auth_url(user):
    if not spotify_is_configured():
        return error_response("Spotify credentials are not configured", 400)

    # Generate state and save it temporarily
    auth_state = secrets.token_urlsafe(24)
    user.spotify_auth_state = auth_state
    try:
        db.session.commit()
    except Exception:
        safe_db_session()

    state = f"{user.id}::{auth_state}"
    # The redirect URI must precisely match the one defined in the Spotify Developer Dashboard.
    redirect_uri = os.getenv("SPOTIFY_REDIRECT_URI", "http://127.0.0.1:5000/api/spotify/callback")
    auth_url = build_spotify_auth_url(redirect_uri, state)

    return jsonify({"status": "success", "url": auth_url})

@app.route("/api/spotify/callback")
def spotify_callback():
    if request.args.get("error"):
        return redirect(f"{FRONTEND_URL}/?spotify=error")

    state = request.args.get("state")
    code = request.args.get("code")
    
    if not state or not code:
        return redirect(f"{FRONTEND_URL}/?spotify=error_state")

    try:
        user_id, expected_state = state.split("::", 1)
        user = None
        try:
           user = User.query.get(user_id)
        except Exception:
           pass
        if not user:
            return redirect(f"{FRONTEND_URL}/?spotify=error_user")

        if user.spotify_auth_state and user.spotify_auth_state != expected_state:
            return redirect(f"{FRONTEND_URL}/?spotify=error_mismatch")
            
        # Clear the state
        user.spotify_auth_state = None
        try:
            db.session.commit()
        except Exception:
            safe_db_session()

        redirect_uri = os.getenv("SPOTIFY_REDIRECT_URI", "http://127.0.0.1:5000/api/spotify/callback")
        token_payload = exchange_code_for_tokens(code, redirect_uri)
        profile = get_spotify_profile(token_payload["access_token"])
        display_name = profile.get("display_name") or profile.get("id")
        try:
            save_spotify_tokens(user, token_payload, display_name)
        except Exception:
            pass
        
        return redirect(f"{FRONTEND_URL}/?spotify=connected")
    except Exception as exc:
        print("Spotify callback failed:", str(exc))
        traceback.print_exc()
        return redirect(f"{FRONTEND_URL}/?spotify=error_catch")

@app.route("/api/spotify/disconnect", methods=["POST"])
@require_auth
def spotify_disconnect(user):
    user.spotify_access_token = None
    user.spotify_refresh_token = None
    user.spotify_expires_at = None
    user.spotify_display_name = None
    try:
        db.session.commit()
    except Exception:
        safe_db_session()
    return jsonify({"status": "success"})

@app.route("/api/generate-playlist", methods=["POST"])
@require_auth
def generate(user):
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

        spotify_profile = listening_profile_for_user(user)
        if not spotify_profile:
            return error_response("You must connect your Spotify account first.", 403)

        playlist_data = generate_playlist(mood, context, energy, intent, spotify_profile)

        # Save to database
        new_playlist = Playlist(
            user_id=user.id,
            mood=mood,
            context=context,
            energy=energy,
            intent=intent,
            playlist_json=json.dumps(playlist_data)
        )
        db.session.add(new_playlist)
        try:
            db.session.commit()
        except Exception:
            safe_db_session()

        return jsonify({
            "status": "success",
            "playlist": playlist_data,
            "saved_id": new_playlist.id
        }), 200

    except ValueError as ve:
        return error_response(str(ve), 400)
    except Exception as exc:
        print("ERROR:", str(exc))
        traceback.print_exc()
        return error_response("Playlist generation failed. Try again in a moment.", 500)

@app.route("/api/playlists")
@require_auth
def playlists(user):
    safe_db_session()

    try:
        pl_list = Playlist.query.filter_by(user_id=user.id)\
            .order_by(Playlist.created_at.desc(), Playlist.id.desc())\
            .limit(20).all()
    except Exception:
        pl_list = []

    return jsonify({
        "status": "success",
        "playlists": [playlist_row_payload(pl) for pl in pl_list]
    })

@app.route("/api/playlists/<int:playlist_id>", methods=["DELETE"])
@require_auth
def delete_playlist(user, playlist_id):
    pl = Playlist.query.filter_by(id=playlist_id, user_id=user.id).first()
    if not pl:
        return error_response("Playlist not found", 404)
        
    db.session.delete(pl)
    
    try:
        db.session.commit()
    except Exception:
        safe_db_session()

    return jsonify({"status": "success"}) 

@app.route("/health")
def health():
    return jsonify({
        "status": "running",
        "message": "Moodwave API is live"
    })

if __name__ == "__main__":
    port = int(os.getenv("PORT", "5000"))
    app.run(host="0.0.0.0", port=port, debug=os.getenv("FLASK_DEBUG") == "1")
