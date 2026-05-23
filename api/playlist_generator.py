import os
import json

from dotenv import load_dotenv
from groq import Groq

load_dotenv(override=True)

MASTER_PROMPT = """
You are an emotionally intelligent music therapist and expert playlist curator.

Your job is NOT to randomly pick songs.

Your job is to emotionally guide the listener through a feeling.

The playlist should feel:
- psychologically coherent
- emotionally immersive
- cinematic
- deeply personal
- emotionally progressive

USER STATE:

Mood: {mood}
Context: {context}
Energy: {energy}
Intent: {intent}

AVAILABLE SPOTIFY LIBRARY:
{spotify_library}

CRITICAL RULES:
- ONLY use songs from the provided Spotify library
- NEVER invent songs
- NEVER use artists outside the library
- Songs must match emotional tone, lyrics, atmosphere, pacing, and emotional transition
- Sequence matters A LOT
- Think like making a movie soundtrack for the user's emotional state

PLAYLIST FLOW RULES:
- opening songs should emotionally validate the current feeling
- middle songs should deepen or stabilize the emotion
- ending songs should resolve, soothe, empower, or transform the emotional state depending on intent

ENERGY RULES:
- "low" = intimate, soft, vulnerable, reflective
- "medium" = emotionally active, warm, rhythmic
- "high" = energetic, cathartic, empowering

OUTPUT:
Return ONLY valid JSON.

Required format:

{{
  "playlist_name": "emotionally evocative title",
  "theme_description": "short cinematic emotional summary",
  "energy_curve": "low → medium → low",
  "tags": ["late-night", "healing", "melancholic"],
  "songs": [
    {{
      "title": "song title",
      "artist": "artist",
      "energy": "low",
      "reason": "specific emotional reason this song belongs here",
      "spotify_url": "url",
      "spotify_uri": "uri",
      "spotify_id": "id",
      "album_art": "art",
      "preview_url": "preview"
    }}
  ]
}}
"""

def _spotify_library_text(spotify_profile):
    if not spotify_profile:
        return "No Spotify profile found."

    tracks = spotify_profile.get("library_tracks", [])

    if not tracks:
        return "No saved Spotify tracks found."

    lines = []

    for track in tracks:
        lines.append(
            f'- "{track.get("title")}" by {track.get("artist")} '
            f'(URL: {track.get("spotify_url")}, '
            f'URI: {track.get("spotify_uri")}, '
            f'ID: {track.get("spotify_id")}, '
            f'Art: {track.get("album_art")}, '
            f'Preview: {track.get("preview_url")})'
        )

    return "\n".join(lines)


def generate_playlist(
    mood,
    context,
    energy,
    intent,
    spotify_profile=None
):
    api_key = os.getenv("GROQ_API_KEY")

    if not api_key:
        raise ValueError(
            "Groq API Key missing. Add GROQ_API_KEY to .env"
        )

    if not spotify_profile or not spotify_profile.get("library_tracks"):
        raise ValueError(
            "Spotify library empty. Connect Spotify and save tracks first."
        )

    client = Groq(api_key=api_key)

    prompt = MASTER_PROMPT.format(
        mood=mood,
        context=context,
        energy=energy,
        intent=intent,
        spotify_library=_spotify_library_text(spotify_profile),
    )

    try:
        response = client.chat.completions.create(
            model=os.getenv(
                "GROQ_MODEL",
                "llama-3.3-70b-versatile"
            ),
            temperature=0.8,
            max_tokens=4000,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a world-class emotional music curator. "
                        "You MUST ONLY use tracks from the provided Spotify library."
                    )
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            response_format={"type": "json_object"}
        )

    except Exception as exc:
        print("Groq API failed:", str(exc))
        raise ValueError("AI playlist generation failed.")

    raw = response.choices[0].message.content.strip()

    if raw.startswith("```"):
        raw = raw.replace("```json", "").replace("```", "").strip()

    try:
        result = json.loads(raw)

    except Exception as exc:
        print("JSON PARSE ERROR:", str(exc))
        print("RAW AI OUTPUT:", raw)
        raise ValueError("AI returned invalid JSON.")

    required = [
        "playlist_name",
        "theme_description",
        "energy_curve",
        "tags",
        "songs"
    ]

    for key in required:
        if key not in result:
            raise ValueError(f"AI response missing field: {key}")

    if not isinstance(result["songs"], list):
        raise ValueError("Songs must be a list.")

    if len(result["songs"]) < 1:
        raise ValueError("Playlist returned empty.")

    return result