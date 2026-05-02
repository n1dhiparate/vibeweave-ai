# Moodwave

Moodwave is a full-stack Flask web app that generates and saves mood-based playlists.

## Features

- Register, login, logout
- Session-based authentication
- Playlist generation
- Saved playlist history per user
- SQLite persistence
- Local fallback playlists when the AI API is unavailable

## Run Locally

```powershell
cd backend
..\venv\Scripts\activate
python app.py
```

Open `http://localhost:5000/`.

## Deploy On Render

Use these settings if you create the Render service manually:

- Runtime: Python 3
- Build Command: `pip install -r backend/requirements.txt`
- Start Command: `gunicorn --chdir backend app:app`

Environment variables:

- `FLASK_SECRET_KEY`: any long random string
- `ANTHROPIC_API_KEY`: optional. The app falls back to local playlists without it.
- `DATABASE_PATH`: optional. Defaults to `backend/data/moodwave.sqlite3`.

## Deploy On Vercel

This repo includes a root `app.py` adapter so Vercel can find the Flask app.

Environment variables:

- `FLASK_SECRET_KEY`: any long random string
- `DATABASE_PATH`: `/tmp/moodwave.sqlite3`
- `ANTHROPIC_API_KEY`: optional

Note: `/tmp` storage on Vercel is temporary. Use Render or an external database
such as Neon/Supabase Postgres if you want saved accounts and playlists to persist.
