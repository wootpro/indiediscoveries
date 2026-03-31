"""Data models for track discovery pipeline."""
from dataclasses import dataclass, field
from datetime import date
from typing import Optional


@dataclass
class RawTrack:
    """A track mention scraped from any source."""
    artist_name: str
    track_title: str
    source_name: str
    source_url: Optional[str] = None
    album_name: Optional[str] = None
    discovered_date: date = field(default_factory=date.today)
    genre_hint: Optional[str] = None
    spotify_uri: Optional[str] = None


@dataclass
class ScoredTrack:
    """A deduplicated, scored track ready for filtering."""
    id: Optional[int] = None
    artist_name: str = ""
    artist_name_normalized: str = ""
    track_title: str = ""
    track_title_normalized: str = ""
    album_name: Optional[str] = None
    genre: str = "Unknown"
    source_count: int = 0
    sources: str = ""
    max_source_weight: float = 0.0
    total_score: float = 0.0
    spotify_uri: Optional[str] = None
    spotify_track_id: Optional[str] = None
    release_date: Optional[str] = None
    first_seen: Optional[str] = None
    last_seen: Optional[str] = None


@dataclass
class PlaylistRecord:
    """Record of a created playlist."""
    id: Optional[int] = None
    playlist_name: str = ""
    spotify_playlist_id: str = ""
    created_date: str = ""
    track_count: int = 0
