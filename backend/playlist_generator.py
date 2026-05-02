import anthropic
import json
import os
from dotenv import load_dotenv

load_dotenv()

MASTER_PROMPT = """You are an expert music curator with deep knowledge of indie, mainstream, and underground music across all genres.

Generate a personalized playlist based on the user's current state:

Mood: {mood}
Context: {context}
Energy level: {energy}
Intent: {intent}

Rules:
- 8 to 12 songs total
- Smooth emotional and energy progression (don't jump wildly between vibes)
- Mix well-known and lesser-known tracks — avoid the most overplayed choices
- Each song should feel intentional, not random
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
      "title": "song title",
      "artist": "artist name",
      "energy": "low",
      "reason": "why this fits right now"
    }}
  ]
}}"""


FALLBACK_SONGS = {
    "low": [
        ("Pink Moon", "Nick Drake", "low"),
        ("Moon Song", "Phoebe Bridgers", "low"),
        ("Holocene", "Bon Iver", "low"),
        ("Sea of Love", "Cat Power", "low"),
        ("K.", "Cigarettes After Sex", "low"),
        ("Cherry-coloured Funk", "Cocteau Twins", "medium"),
        ("Fade Into You", "Mazzy Star", "low"),
        ("First Love / Late Spring", "Mitski", "medium"),
    ],
    "medium": [
        ("Sweet Disposition", "The Temper Trap", "medium"),
        ("Myth", "Beach House", "medium"),
        ("Electric Feel", "MGMT", "medium"),
        ("Lost in the World", "Kanye West", "medium"),
        ("1901", "Phoenix", "high"),
        ("Midnight City", "M83", "high"),
        ("The Less I Know The Better", "Tame Impala", "medium"),
        ("Young Folks", "Peter Bjorn and John", "medium"),
    ],
    "high": [
        ("Dog Days Are Over", "Florence + The Machine", "high"),
        ("Tongue Tied", "Grouplove", "high"),
        ("Lisztomania", "Phoenix", "high"),
        ("Dancing On My Own", "Robyn", "high"),
        ("Take a Walk", "Passion Pit", "high"),
        ("Supercut", "Lorde", "high"),
        ("Hard Times", "Paramore", "high"),
        ("Everybody Wants To Love You", "Japanese Breakfast", "high"),
    ],
}


def generate_fallback_playlist(mood, context, energy, intent):
    energy_key = energy.lower() if energy.lower() in FALLBACK_SONGS else "medium"
    mood_words = [word.strip(".,!?").lower() for word in mood.split() if len(word) > 2]
    main_mood = mood_words[0] if mood_words else "mood"

    return {
        "playlist_name": f"{main_mood.title()} {intent.title()} Mix",
        "theme_description": f"A {energy_key}-energy {context} playlist for when you feel {mood}.",
        "energy_curve": f"{energy_key} -> medium -> {energy_key}",
        "tags": [context, energy_key, intent],
        "songs": [
            {
                "title": title,
                "artist": artist,
                "energy": song_energy,
                "reason": f"This keeps the {intent} vibe steady while matching your {context} mood."
            }
            for title, artist, song_energy in FALLBACK_SONGS[energy_key]
        ]
    }


def generate_playlist(mood, context, energy, intent):
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        return generate_fallback_playlist(mood, context, energy, intent)

    client = anthropic.Anthropic(api_key=api_key)

    prompt = MASTER_PROMPT.format(
        mood=mood,
        context=context,
        energy=energy,
        intent=intent
    )

    try:
        message = client.messages.create(
            model=os.getenv("ANTHROPIC_MODEL", "claude-3-sonnet-20240229"),
            max_tokens=2000,
            messages=[
                {"role": "user", "content": prompt}
            ]
        )
    except Exception as exc:
        print("Anthropic API unavailable, using fallback playlist:", str(exc))
        return generate_fallback_playlist(mood, context, energy, intent)

    raw = ""

    for block in message.content:
        if block.type == "text":
           raw += block.text

    raw = raw.strip()

    if raw.startswith("```"):
        lines = raw.split("\n")
        raw = "\n".join(lines[1:-1])

    result = json.loads(raw)

    required = ["playlist_name", "theme_description", "energy_curve", "tags", "songs"]
    for key in required:
        if key not in result:
            raise ValueError(f"AI response missing field: {key}")

    if not isinstance(result["songs"], list):
        raise ValueError("AI response songs field must be a list")

    for index, song in enumerate(result["songs"], start=1):
        if not isinstance(song, dict):
            raise ValueError(f"AI response song #{index} must be an object")
        if "title" not in song or "artist" not in song:
            raise ValueError(f"AI response song #{index} missing title or artist")

    return result
