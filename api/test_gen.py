from app import app, db

from playlist_generator import generate_playlist
from spotify_service import build_listening_profile

with app.app_context():
    # Get the first user with a spotify token
    user = User.query.filter(User.spotify_refresh_token.isnot(None)).first()
    if not user:
        print("No user with Spotify connected.")
    else:
        print(f"Testing for user {user.email}")
        try:
            profile = build_listening_profile(user.spotify_access_token)
            print(f"Fetched {len(profile.get('library_tracks', []))} tracks from Spotify.")
            
            res = generate_playlist("I just want to relax after a long day of coding", "late night", "low", "relax", profile)
            print("Success!", res.keys())
        except Exception as e:
            import traceback
            traceback.print_exc()
