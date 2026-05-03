<div align="center">
  <img src="./public/assets/headphones.png" alt="Moodwave Logo" width="120" />
  <h1>✿ Moodwave ✿</h1>
  <p><strong>An AI-powered, full-stack playlist curator that matches your exact vibe using your personal Spotify library.</strong></p>

  [![Vite](https://img.shields.io/badge/Vite-B73BFE?style=for-the-badge&logo=vite&logoColor=FFD62E)](https://vitejs.dev/)
  [![React](https://img.shields.io/badge/React-20232A?style=for-the-badge&logo=react&logoColor=61DAFB)](https://reactjs.org/)
  [![Flask](https://img.shields.io/badge/Flask-000000?style=for-the-badge&logo=flask&logoColor=white)](https://flask.palletsprojects.com/)
  [![PostgreSQL](https://img.shields.io/badge/PostgreSQL-316192?style=for-the-badge&logo=postgresql&logoColor=white)](https://www.postgresql.org/)
  [![Supabase](https://img.shields.io/badge/Supabase-181818?style=for-the-badge&logo=supabase&logoColor=white)](https://supabase.com/)
</div>

<br />

## 🎵 Overview

**Moodwave** is a full-stack web application designed to eliminate the friction of music curation. By leveraging the **Spotify API** and advanced **Groq Large Language Models (LLM)**, Moodwave analyzes a user's explicit intent, energy level, and mood, and curates a customized playlist drawn **exclusively** from their own saved Spotify library. 

This ensures that the AI never hallucinates unknown tracks, delivering a highly personalized listening experience wrapped in a nostalgic Y2K/Kawaii aesthetic.

## ✨ Key Features

- **Strict AI Curation Strategy:** Powered by LLaMA-3.3 (via Groq), the prompt engineering explicitly restricts the LLM to only select tracks from the authenticated user's Spotify library (Top Tracks + Liked Tracks).
- **Secure Authentication:** Implements JWT-based authentication using **Supabase GoTrue Auth**, ensuring user sessions and Spotify tokens are securely managed.
- **Dynamic React SPA:** A highly responsive frontend built with Vite and React, featuring custom CSS animations, real-time feedback, and dynamic state management without full-page reloads.
- **Serverless Architecture Ready:** The monolithic Flask application is configured for seamless deployment on Vercel as Serverless Python Functions, complete with API routing rewrites.
- **Persistent Data:** Playlists and user metadata are stored securely in a Supabase-hosted **PostgreSQL** database using SQLAlchemy ORM.

## 🛠️ Architecture & Tech Stack

### Frontend
- **Framework:** React 18, Vite
- **Styling:** Custom Vanilla CSS (Keyframe Animations, Variables, Responsive Grid)
- **State Management:** React Hooks (`useState`, `useEffect`)
- **API Client:** Fetch API with JWT Bearer authorization

### Backend
- **Framework:** Python, Flask
- **Database ORM:** Flask-SQLAlchemy
- **Authentication:** `@supabase/supabase-js` (Frontend) & `python-jose` (Backend validation)
- **AI Integration:** Groq SDK (`llama-3.3-70b-versatile`)
- **External APIs:** Spotify Web API (OAuth 2.0 Auth Code Flow)

---

## 🚀 Local Development Setup

To run this project locally, you will need two terminal windows running concurrently.

### 1. Environment Variables
Create a `.env` file at the root of the project with the following keys:
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
SPOTIFY_CLIENT_ID=your_spotify_id
SPOTIFY_CLIENT_SECRET=your_spotify_secret
SPOTIFY_REDIRECT_URI=http://127.0.0.1:5000/api/spotify/callback
```

### 2. Run the Backend (Flask)
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
python backend/app.py
```

### 3. Run the Frontend (React / Vite)
```bash
npm install
npm run dev
```
The application will be available at `http://localhost:5173`.

---

## ☁️ Deployment (Vercel)

This repository is structured as a Vercel-compatible monorepo. 

1. Push the code to GitHub.
2. Import the project into Vercel.
3. Vercel will automatically detect **Vite** for the frontend build.
4. Add all environment variables in the Vercel Dashboard.
5. The `vercel.json` file automatically routes all `/api/*` traffic to the Python Serverless Functions.

*Note: Remember to update your Spotify Developer Dashboard to include your live Vercel URL (e.g., `https://vibeweave-ai.vercel.app/api/spotify/callback`).*

---
<div align="center">
  <p>Made with ♥ by Nidhi Parate</p>
</div>
