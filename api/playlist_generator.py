import json
import os
from dotenv import load_dotenv
from groq import Groq

load_dotenv(override=True)

MASTER_PROMPT = """You are an expert music curator.

Generate a personalized playlist based on the user's current state:

Mood: {mood}
Context: {context}
Energy level: {energy}
Intent: {intent}

CRITICAL RULE: You MUST exclusively select songs from the provided Spotify Library below. You are NOT allowed to suggest any song or artist that is not present in the provided list. Do not hallucinate or add external tracks.

User's Spotify Library:
{spotify_library}

Rules:
- 8 to 12 songs total (all strictly chosen from the library above)
- Smooth emotional and energy progression
- "reason" should be 1 short sentence explaining why this song fits right now
- "energy" per song must be exactly one of: low, medium, high

Return ONLY a valid JSON object. No markdown. No backticks. No explanation. No text before or after.

{{
  "playlist_name": "short evocative name",
  "theme_description": "one sentence describing the overall feel",
  "energy_curve": "e.g. low → medium → low",
  "tags": ["tag1", "tag2", "tag3"],
  "songs": [
    {{
      "title": "song title (from library)",
      "artist": "artist name (from library)",
      "energy": "low",
      "reason": "why this fits right now",
      "spotify_url": "url from library",
      "spotify_uri": "uri from library",
      "spotify_id": "id from library",
      "album_art": "album art from library",
      "preview_url": "preview url from library"
    }}
  ]
}}"""

def _spotify_library_text(spotify_profile):
    if not spotify_profile or "library_tracks" not in spotify_profile:
        return "No Spotify library provided."

    tracks = spotify_profile["library_tracks"]
    track_lines = [
        f"- \"{t.get('title')}\" by {t.get('artist')} "
        f"(URL: {t.get('spotify_url')}, URI: {t.get('spotify_uri')}, ID: {t.get('spotify_id')}, "
        f"Art: {t.get('album_art')}, Preview: {t.get('preview_url')})"
        for t in tracks
    ]

    return "\n".join([
        "Available Tracks:",
        *track_lines,
    ]).strip()

def generate_playlist(mood, context, energy, intent, spotify_profile=None):
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise ValueError("Groq API Key is missing. Please add GROQ_API_KEY to your .env file.")

    if not spotify_profile or not spotify_profile.get("library_tracks"):
        raise ValueError("Spotify library is empty or not connected. Please connect Spotify and save some tracks.")

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
            model=os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile"),
            messages=[
                {"role": "user", "content": prompt}
            ],
            response_format={"type": "json_object"}
        )
    except Exception as exc:
        print("Groq API failed:", str(exc))
        raise

    raw = response.choices[0].message.content.strip()

    if raw.startswith("```"):
        lines = raw.split("\n")
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines[-1].startswith("```"):
            lines = lines[:-1]
        raw = "\n".join(lines).strip()

    result = json.loads(raw)
    
    required = ["playlist_name", "theme_description", "energy_curve", "tags", "songs"]
    for key in required:
        if key not in result:
            raise ValueError(f"AI response missing field: {key}")

    return result
