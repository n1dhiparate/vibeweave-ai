from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timezone

db = SQLAlchemy()

class User(db.Model):
    __tablename__ = 'users'
    
    id = db.Column(db.String(36), primary_key=True) # Supabase Auth UUID
    email = db.Column(db.String(255), unique=True, nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    
    spotify_access_token = db.Column(db.Text, nullable=True)
    spotify_refresh_token = db.Column(db.Text, nullable=True)
    spotify_expires_at = db.Column(db.Integer, nullable=True)
    spotify_display_name = db.Column(db.String(255), nullable=True)
    spotify_auth_state = db.Column(db.String(255), nullable=True)

    
    playlists = db.relationship('Playlist', backref='user', lazy=True, cascade="all, delete-orphan")

class Playlist(db.Model):
    __tablename__ = 'playlists'
    
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id = db.Column(db.String(36), db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    mood = db.Column(db.Text, nullable=False)
    context = db.Column(db.Text, nullable=False)
    energy = db.Column(db.Text, nullable=False)
    intent = db.Column(db.Text, nullable=False)
    playlist_json = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
