import base64
import logging
import os
import time
from urllib.parse import urlencode
import requests

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

SPOTIFY_AUTHORIZE_URL = "https://accounts.spotify.com/authorize"
SPOTIFY_TOKEN_URL = "https://accounts.spotify.com/api/token"
SPOTIFY_SEARCH_URL = "https://api.spotify.com/v1/search"
SPOTIFY_TOP_ITEMS_URL = "https://api.spotify.com/v1/me/top/{item_type}"
SPOTIFY_SAVED_TRACKS_URL = "https://api.spotify.com/v1/me/tracks"
SPOTIFY_PROFILE_URL = "https://api.spotify.com/v1/me"
SPOTIFY_SCOPES = "user-top-read user-read-private user-library-read"

_token_cache = {
    "access_token": None,
    "expires_at": 0,
}

def _spotify_credentials():
    client_id = os.getenv("SPOTIFY_CLIENT_ID")
    client_secret = os.getenv("SPOTIFY_CLIENT_SECRET")
    if not client_id or not client_secret:
        return None, None
    return client_id, client_secret

def spotify_is_configured():
    return all(_spotify_credentials())

def build_spotify_auth_url(redirect_uri, state):
    client_id, _ = _spotify_credentials()
    if not client_id:
        return None
    params = {
        "client_id": client_id,
        "response_type": "code",
        "redirect_uri": redirect_uri,
        "scope": SPOTIFY_SCOPES,
        "state": state,
    }
    return f"{SPOTIFY_AUTHORIZE_URL}?{urlencode(params)}"

def exchange_code_for_tokens(code, redirect_uri):
    client_id, client_secret = _spotify_credentials()
    logger.info("Exchanging authorization code for tokens")
    response = requests.post(
        SPOTIFY_TOKEN_URL,
        data={"grant_type": "authorization_code", "code": code, "redirect_uri": redirect_uri},
        auth=(client_id, client_secret),
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=10,
    )
    response.raise_for_status()
    logger.info("Successfully exchanged authorization code for tokens")
    return response.json()

def refresh_user_token(refresh_token):
    import requests
    import os

    response = requests.post(
        "https://accounts.spotify.com/api/token",
        data={
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": os.getenv("SPOTIFY_CLIENT_ID"),
            "client_secret": os.getenv("SPOTIFY_CLIENT_SECRET"),
        },
    )

    response.raise_for_status()

    return response.json()

def get_spotify_profile(access_token):
    logger.info("Fetching Spotify user profile")
    response = requests.get(SPOTIFY_PROFILE_URL, headers={"Authorization": f"Bearer {access_token}"}, timeout=10)
    response.raise_for_status()
    logger.info("Successfully fetched Spotify user profile")
    return response.json()

def get_user_saved_tracks(access_token, limit=50):
    logger.info(f"Fetching user saved tracks (limit={limit})")
    response = requests.get(
        SPOTIFY_SAVED_TRACKS_URL,
        params={"limit": limit},
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=10,
    )
    response.raise_for_status()
    items = response.json().get("items", [])
    logger.info(f"Successfully fetched {len(items)} saved tracks")
    return items

def get_user_top_items(access_token, item_type, time_range="medium_term", limit=20):
    logger.info(f"Fetching user top {item_type} (time_range={time_range}, limit={limit})")
    response = requests.get(
        SPOTIFY_TOP_ITEMS_URL.format(item_type=item_type),
        params={"time_range": time_range, "limit": limit},
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=10,
    )
    response.raise_for_status()
    items = response.json().get("items", [])
    logger.info(f"Successfully fetched {len(items)} top {item_type}")
    return items

def build_listening_profile(access_token):
    # Fetch user's saved tracks and top tracks to form a solid library pool
    logger.info("Building listening profile from Spotify library")
    tracks_pool = []
    
    # 1. Saved Tracks (Liked Songs)
    try:
        saved_items = get_user_saved_tracks(access_token, limit=50)
        for item in saved_items:
            track = item.get("track")
            if track:
                tracks_pool.append(track)
    except Exception as exc:
        logger.error(f"Failed to fetch saved tracks: {str(exc)}")

    # 2. Top Tracks
    try:
        top_items = get_user_top_items(access_token, "tracks", time_range="short_term", limit=20)
        tracks_pool.extend(top_items)
    except Exception as exc:
        logger.error(f"Failed to fetch top tracks: {str(exc)}")

    unique_tracks = []
    seen = set()
    for track in tracks_pool:
        if not track: continue
        title = track.get("name")
        artist = ", ".join(a.get("name", "") for a in track.get("artists", []))
        key = (title, artist)
        if title and key not in seen:
            seen.add(key)
            unique_tracks.append({
                "title": title,
                "artist": artist,
                "spotify_url": track.get("external_urls", {}).get("spotify"),
                "spotify_uri": track.get("uri"),
                "spotify_id": track.get("id"),
                "album_art": _best_album_image(track),
                "preview_url": track.get("preview_url"),
                "spotify_popularity": track.get("popularity"),
            })

    # Shuffle or limit? We return up to 70 tracks. The LLM will pick from these.
    return {
        "library_tracks": unique_tracks[:70]
    }

def _best_album_image(track):
    images = track.get("album", {}).get("images") or []
    if not images:
        return None
    medium = sorted(images, key=lambda image: abs((image.get("width") or 0) - 300))
    return medium[0].get("url")

# enrich_playlist_with_user_spotify is removed because the LLM is already outputting tracks 
# that came directly from the user's library (with all spotify URLs intact) 
# so we don't need to re-search them.
