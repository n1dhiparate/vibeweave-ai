<div align="center">
  <img src="./public/assets/headphones.png" alt="Moodwave Logo" width="120" />
  <h1>✿ Moodwave ✿</h1>
  <p><strong>An AI-powered playlist curator that creates mood-driven Spotify playlists from your own library.</strong></p>

  [![Live Demo](https://img.shields.io/badge/Live-vibeweave--ai.vercel.app-blue?style=for-the-badge&logo=vercel&logoColor=white)](https://vibeweave-ai.vercel.app/)
  [![Vite](https://img.shields.io/badge/Vite-B73BFE?style=for-the-badge&logo=vite&logoColor=FFD62E)](https://vitejs.dev/)
  [![React](https://img.shields.io/badge/React-20232A?style=for-the-badge&logo=react&logoColor=61DAFB)](https://reactjs.org/)
  [![Flask](https://img.shields.io/badge/Flask-000000?style=for-the-badge&logo=flask&logoColor=white)](https://flask.palletsprojects.com/)
  [![Supabase](https://img.shields.io/badge/Supabase-181818?style=for-the-badge&logo=supabase&logoColor=white)](https://supabase.com/)
</div>

<br />

## Overview

Moodwave is a full-stack web experience that turns your Spotify mood and intent into a smart playlist built from your own saved tracks.

The app uses:
- Spotify saved tracks and top tracks as the curated pool
- Supabase authentication to secure user sessions
- Groq LLM prompt guidance to keep playlist suggestions strictly within the user’s library
- A Vite + React frontend for fast, interactive UI
- A Flask-based Python backend that runs on Vercel serverless functions

## Live Demo

Visit the live app here:

- https://vibeweave-ai.vercel.app/
- [Open Moodwave live](https://vibeweave-ai.vercel.app/)

---

## What Makes Moodwave Different

- Personalized playlist curation from your own Spotify library
- Mood, energy, and intent input for more precise results
- No hallucinated tracks because the AI is forced to choose only from authenticated user data
- Clean serverless deployment via Vercel with API routing from `vercel.json`
- Modern React UI with smooth interactions and responsive visual polish

---

## Tech Stack

### Frontend
- React 19, Vite 8
- `@supabase/supabase-js` for authentication and user session handling
- Responsive layouts and CSS animations

### Backend
- Python 3, Flask
- Flask-CORS for cross-origin requests
- Flask-SQLAlchemy for data persistence
- Supabase Python client for auth and database access
- Groq SDK for AI playlist generation
- Spotify Web API OAuth 2.0

---

## Local Development

### 1. Create environment variables
Create a `.env` file at the project root with:

```env
# Frontend
VITE_SUPABASE_URL=your_supabase_url
VITE_SUPABASE_ANON_KEY=your_supabase_anon_key
VITE_API_URL=http://localhost:5000

# Backend
SUPABASE_URL=your_supabase_url
SUPABASE_KEY=your_supabase_service_key
DATABASE_URL=postgresql://postgres:password@db.../postgres
GROQ_API_KEY=gsk_your_groq_key
SPOTIFY_CLIENT_ID=your_spotify_client_id
SPOTIFY_CLIENT_SECRET=your_spotify_client_secret
SPOTIFY_REDIRECT_URI=http://127.0.0.1:5000/api/spotify/callback
FRONTEND_URL=http://localhost:5173

# In production, set FRONTEND_URL to your deployed app URL and SPOTIFY_REDIRECT_URI to that URL plus /api/spotify/callback.
# Example: FRONTEND_URL=https://vibeweave-ai.vercel.app
#          SPOTIFY_REDIRECT_URI=https://vibeweave-ai.vercel.app/api/spotify/callback
```

### 2. Start the backend

```bash
cd api
python -m venv venv
venv\Scripts\activate   # Windows
# source venv/bin/activate  # macOS / Linux
pip install -r ../requirements.txt
python index.py
```

### 3. Start the frontend

```bash
cd ..
npm install
npm run dev
```

Open `http://localhost:5173` to use Moodwave locally.

---

## Deployment to Vercel

This repository is configured for Vercel with the following deployment setup:

- `vercel.json` rewrites `/api/*` requests to `api/index.py`
- the React frontend is served from `index.html`

### Deployment steps
1. Push your repository to GitHub.
2. Import it into Vercel.
3. Confirm Vercel detects the Vite frontend.
4. Add all required environment variables in Vercel.
5. Set your Spotify callback URI to:
   `https://vibeweave-ai.vercel.app/api/spotify/callback`

---

## Project Structure

- `api/` — Flask backend, Spotify auth, playlist generation, Supabase integration
- `src/` — React frontend source code
- `public/` — static assets and HTML entrypoint
- `vercel.json` — Vercel rewrite configuration
- `package.json` — frontend scripts and dependencies
- `requirements.txt` — backend dependencies

---

<div align="center">
  <p>Made with ♥ by Nidhi Parate</p>
</div>
