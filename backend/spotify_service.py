import base64
import os
import time
from urllib.parse import urlencode

import requests

SPOTIFY_AUTHORIZE_URL = "https://accounts.spotify.com/authorize"
SPOTIFY_TOKEN_URL = "https://accounts.spotify.com/api/token"
SPOTIFY_SEARCH_URL = "https://api.spotify.com/v1/search"
SPOTIFY_TOP_ITEMS_URL = "https://api.spotify.com/v1/me/top/{item_type}"
SPOTIFY_PROFILE_URL = "https://api.spotify.com/v1/me"
SPOTIFY_SCOPES = "user-top-read user-read-private"

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
    if not client_id or not client_secret:
        raise ValueError("Spotify credentials are not configured")

    response = requests.post(
        SPOTIFY_TOKEN_URL,
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri,
        },
        auth=(client_id, client_secret),
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=10,
    )
    response.raise_for_status()
    return response.json()


def refresh_user_token(refresh_token):
    client_id, client_secret = _spotify_credentials()
    if not client_id or not client_secret:
        raise ValueError("Spotify credentials are not configured")

    response = requests.post(
        SPOTIFY_TOKEN_URL,
        data={
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
        },
        auth=(client_id, client_secret),
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=10,
    )
    response.raise_for_status()
    return response.json()


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


def get_spotify_profile(access_token):
    response = requests.get(
        SPOTIFY_PROFILE_URL,
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=10,
    )
    response.raise_for_status()
    return response.json()


def get_user_top_items(access_token, item_type, time_range="medium_term", limit=20):
    response = requests.get(
        SPOTIFY_TOP_ITEMS_URL.format(item_type=item_type),
        params={"time_range": time_range, "limit": limit},
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=10,
    )
    response.raise_for_status()
    return response.json().get("items", [])


def build_listening_profile(access_token):
    top_tracks = []
    top_artists = []

    for time_range in ("short_term", "medium_term"):
        for track in get_user_top_items(access_token, "tracks", time_range=time_range, limit=10):
            top_tracks.append({
                "title": track.get("name"),
                "artist": ", ".join(artist.get("name", "") for artist in track.get("artists", [])),
                "spotify_url": track.get("external_urls", {}).get("spotify"),
                "spotify_uri": track.get("uri"),
                "album_art": _best_album_image(track),
            })

    for artist in get_user_top_items(access_token, "artists", time_range="medium_term", limit=12):
        top_artists.append({
            "name": artist.get("name"),
            "genres": artist.get("genres") or [],
        })

    unique_tracks = []
    seen_tracks = set()
    for track in top_tracks:
        key = (track.get("title"), track.get("artist"))
        if track.get("title") and key not in seen_tracks:
            seen_tracks.add(key)
            unique_tracks.append(track)

    return {
        "top_tracks": unique_tracks[:18],
        "top_artists": top_artists,
    }


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


def enrich_playlist_with_user_spotify(playlist, access_token):
    if not access_token:
        return enrich_playlist_with_spotify(playlist)

    for song in playlist.get("songs", []):
        title = song.get("title")
        artist = song.get("artist")
        if not title or not artist:
            continue

        try:
            spotify_data = _search_track(title, artist, access_token)
        except requests.RequestException as exc:
            print("Spotify user search failed:", str(exc))
            continue

        if spotify_data:
            song.update(spotify_data)

    return playlist
