import base64
import os
import time

import requests

SPOTIFY_TOKEN_URL = "https://accounts.spotify.com/api/token"
SPOTIFY_SEARCH_URL = "https://api.spotify.com/v1/search"

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


def _get_access_token():
    if _token_cache["access_token"] and _token_cache["expires_at"] > time.time() + 30:
        return _token_cache["access_token"]

    client_id, client_secret = _spotify_credentials()
    if not client_id or not client_secret:
        return None

    raw_auth = f"{client_id}:{client_secret}".encode("utf-8")
    auth_header = base64.b64encode(raw_auth).decode("utf-8")

    response = requests.post(
        SPOTIFY_TOKEN_URL,
        data={"grant_type": "client_credentials"},
        headers={
            "Authorization": f"Basic {auth_header}",
            "Content-Type": "application/x-www-form-urlencoded",
        },
        timeout=10,
    )
    response.raise_for_status()

    payload = response.json()
    _token_cache["access_token"] = payload["access_token"]
    _token_cache["expires_at"] = time.time() + int(payload.get("expires_in", 3600))
    return _token_cache["access_token"]


def _best_album_image(track):
    images = track.get("album", {}).get("images") or []
    if not images:
        return None

    medium = sorted(images, key=lambda image: abs((image.get("width") or 0) - 300))
    return medium[0].get("url")


def _search_track(title, artist, access_token):
    query = f'track:"{title}" artist:"{artist}"'
    response = requests.get(
        SPOTIFY_SEARCH_URL,
        params={"q": query, "type": "track", "limit": 1},
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=10,
    )
    response.raise_for_status()

    items = response.json().get("tracks", {}).get("items") or []
    if not items:
        return None

    track = items[0]
    return {
        "spotify_url": track.get("external_urls", {}).get("spotify"),
        "spotify_uri": track.get("uri"),
        "spotify_id": track.get("id"),
        "album_art": _best_album_image(track),
        "preview_url": track.get("preview_url"),
        "spotify_popularity": track.get("popularity"),
    }


def enrich_playlist_with_spotify(playlist):
    try:
        access_token = _get_access_token()
    except requests.RequestException as exc:
        print("Spotify token request failed:", str(exc))
        return playlist

    if not access_token:
        return playlist

    for song in playlist.get("songs", []):
        title = song.get("title")
        artist = song.get("artist")
        if not title or not artist:
            continue

        try:
            spotify_data = _search_track(title, artist, access_token)
        except requests.RequestException as exc:
            print("Spotify search failed:", str(exc))
            continue

        if spotify_data:
            song.update(spotify_data)

    return playlist
