"""SQLite database operations: schema, CRUD, deduplication, caching."""
import re
import sqlite3
from datetime import date, datetime, timedelta
from typing import Optional

from config import DB_PATH, SOURCE_WEIGHTS, LOOKBACK_DAYS
from storage.models import RawTrack, ScoredTrack


def normalize_artist(name: str) -> str:
    """Normalize artist name for deduplication.

    Extracts the primary artist from collabs/features so that
    'Courtney Barnett, Waxahatchee' and 'Courtney Barnett' dedup together.
    """
    n = name.strip().lower()
    n = re.sub(r"^the\s+", "", n)
    n = re.sub(r"\s*\(.*?\)\s*", "", n)

    # Remove featuring suffixes
    n = re.sub(r"\s*feat\.?\s+.*$", "", n)
    n = re.sub(r"\s*ft\.?\s+.*$", "", n)
    n = re.sub(r"\s*featuring\s+.*$", "", n)

    # Split on " x " collab separator (but not in the middle of a word)
    n = re.sub(r"\s+x\s+.*$", "", n)

    # Split on " & " collab separator
    n = re.sub(r"\s*&\s+.*$", "", n)

    # Split on ", " collab separator — but protect known comma-in-name artists
    # by only splitting if the part after comma looks like a new artist name
    # (starts with a capital-letter word pattern in the original, or is >2 words)
    if ", " in n:
        parts = n.split(", ")
        first = parts[0].strip()
        # Keep full name if it's a known pattern like "tyler, the creator"
        # Heuristic: if second part starts with common articles/prepositions, it's one name
        if len(parts) > 1:
            second = parts[1].strip()
            connectors = ("the ", "a ", "an ", "le ", "la ", "el ", "of ", "de ")
            if not any(second.startswith(c) for c in connectors):
                n = first

    n = re.sub(r"\s+", " ", n).strip()
    return n


def normalize_track(title: str) -> str:
    """Normalize track title for deduplication."""
    n = title.strip().lower()

    # Remove featuring in parentheses: (feat. X), (ft. X), (with X)
    n = re.sub(r"\s*\((?:feat\.?|ft\.?|featuring|with)\s+[^)]+\)\s*", "", n)

    # Remove remix/remaster/version in parentheses
    n = re.sub(r"\s*\(.*?(remix|version|edit|mix|live|demo|remaster).*?\)\s*", "", n)

    # Remove all bracketed content
    n = re.sub(r"\s*\[.*?\]\s*", "", n)

    # Remove "- feat. X" suffix
    n = re.sub(r"\s*-\s*(?:feat\.?|ft\.?|featuring)\s+.*$", "", n, flags=re.IGNORECASE)

    # Remove "- Remaster/Remix/etc" suffix (with optional year like "2012 Remaster")
    n = re.sub(r"\s*-\s*\d*\s*(remix|version|edit|mix|live|demo|remaster).*$", "", n, flags=re.IGNORECASE)

    n = re.sub(r"\s+", " ", n).strip()
    return n


def get_connection() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db():
    """Create tables if they don't exist."""
    conn = get_connection()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS track_mentions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            artist_name TEXT NOT NULL,
            artist_name_normalized TEXT NOT NULL,
            track_title TEXT NOT NULL,
            track_title_normalized TEXT NOT NULL,
            album_name TEXT,
            source_name TEXT NOT NULL,
            source_url TEXT,
            genre_hint TEXT,
            spotify_uri TEXT,
            discovered_date TEXT NOT NULL,
            scraped_at TEXT NOT NULL,
            UNIQUE(artist_name_normalized, track_title_normalized, source_name)
        );

        CREATE TABLE IF NOT EXISTS scored_tracks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            artist_name TEXT NOT NULL,
            artist_name_normalized TEXT NOT NULL,
            track_title TEXT NOT NULL,
            track_title_normalized TEXT NOT NULL,
            album_name TEXT,
            genre TEXT DEFAULT 'Unknown',
            source_count INTEGER DEFAULT 1,
            sources TEXT DEFAULT '',
            max_source_weight REAL DEFAULT 0.0,
            total_score REAL DEFAULT 0.0,
            spotify_uri TEXT,
            spotify_track_id TEXT,
            release_date TEXT,
            first_seen TEXT,
            last_seen TEXT,
            UNIQUE(artist_name_normalized, track_title_normalized)
        );

        CREATE TABLE IF NOT EXISTS playlists (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            playlist_name TEXT NOT NULL,
            spotify_playlist_id TEXT NOT NULL,
            created_date TEXT NOT NULL,
            track_count INTEGER DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS playlist_tracks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            playlist_id INTEGER NOT NULL,
            spotify_uri TEXT NOT NULL,
            artist_name_normalized TEXT NOT NULL,
            track_title_normalized TEXT NOT NULL,
            added_at TEXT NOT NULL,
            FOREIGN KEY (playlist_id) REFERENCES playlists(id),
            UNIQUE(playlist_id, spotify_uri)
        );

        CREATE TABLE IF NOT EXISTS genre_cache (
            artist_name_normalized TEXT PRIMARY KEY,
            genre TEXT NOT NULL,
            cached_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS spotify_search_cache (
            artist_track_key TEXT PRIMARY KEY,
            spotify_uri TEXT,
            spotify_track_id TEXT,
            release_date TEXT,
            cached_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS playlist_feedback (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            playlist_id INTEGER NOT NULL,
            spotify_track_id TEXT NOT NULL,
            artist_name_normalized TEXT NOT NULL,
            was_saved INTEGER DEFAULT 0,
            was_removed INTEGER DEFAULT 0,
            checked_at TEXT NOT NULL,
            FOREIGN KEY (playlist_id) REFERENCES playlists(id),
            UNIQUE(playlist_id, spotify_track_id)
        );

        CREATE TABLE IF NOT EXISTS artist_affinity (
            artist_name_normalized TEXT PRIMARY KEY,
            positive_count INTEGER DEFAULT 0,
            negative_count INTEGER DEFAULT 0,
            affinity_score REAL DEFAULT 0.5,
            updated_at TEXT NOT NULL
        );
    """)
    conn.commit()
    conn.close()


def insert_track_mention(raw: RawTrack):
    """Insert a track mention, merging on conflict."""
    conn = get_connection()
    artist_norm = normalize_artist(raw.artist_name)
    track_norm = normalize_track(raw.track_title)
    now = datetime.now().isoformat()

    try:
        conn.execute("""
            INSERT INTO track_mentions (
                artist_name, artist_name_normalized,
                track_title, track_title_normalized,
                album_name, source_name, source_url, genre_hint,
                spotify_uri, discovered_date, scraped_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(artist_name_normalized, track_title_normalized, source_name)
            DO UPDATE SET
                scraped_at = excluded.scraped_at,
                spotify_uri = COALESCE(excluded.spotify_uri, track_mentions.spotify_uri),
                album_name = COALESCE(excluded.album_name, track_mentions.album_name),
                genre_hint = COALESCE(excluded.genre_hint, track_mentions.genre_hint)
        """, (
            raw.artist_name.strip(),
            artist_norm,
            raw.track_title.strip(),
            track_norm,
            raw.album_name,
            raw.source_name,
            raw.source_url,
            raw.genre_hint,
            raw.spotify_uri,
            raw.discovered_date.isoformat(),
            now,
        ))
        conn.commit()
    finally:
        conn.close()


def batch_insert_track_mentions(tracks: list):
    """Insert multiple track mentions in a single transaction."""
    conn = get_connection()
    now = datetime.now().isoformat()
    rows = []
    for raw in tracks:
        rows.append((
            raw.artist_name.strip(),
            normalize_artist(raw.artist_name),
            raw.track_title.strip(),
            normalize_track(raw.track_title),
            raw.album_name,
            raw.source_name,
            raw.source_url,
            raw.genre_hint,
            raw.spotify_uri,
            raw.discovered_date.isoformat(),
            now,
        ))
    conn.executemany("""
        INSERT INTO track_mentions (
            artist_name, artist_name_normalized,
            track_title, track_title_normalized,
            album_name, source_name, source_url, genre_hint,
            spotify_uri, discovered_date, scraped_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(artist_name_normalized, track_title_normalized, source_name)
        DO UPDATE SET
            scraped_at = excluded.scraped_at,
            spotify_uri = COALESCE(excluded.spotify_uri, track_mentions.spotify_uri),
            album_name = COALESCE(excluded.album_name, track_mentions.album_name),
            genre_hint = COALESCE(excluded.genre_hint, track_mentions.genre_hint)
    """, rows)
    conn.commit()
    conn.close()


def clean_old_mentions():
    """Remove track mentions older than LOOKBACK_DAYS."""
    cutoff = (date.today() - timedelta(days=LOOKBACK_DAYS)).isoformat()
    conn = get_connection()
    conn.execute("DELETE FROM track_mentions WHERE discovered_date < ?", (cutoff,))
    conn.commit()
    conn.close()


def build_scored_tracks():
    """Aggregate track_mentions into scored_tracks table."""
    conn = get_connection()
    conn.execute("DELETE FROM scored_tracks")

    conn.execute("""
        INSERT INTO scored_tracks (
            artist_name, artist_name_normalized,
            track_title, track_title_normalized,
            album_name, genre, source_count, sources,
            max_source_weight, spotify_uri,
            first_seen, last_seen
        )
        SELECT
            artist_name,
            artist_name_normalized,
            track_title,
            track_title_normalized,
            MAX(album_name),
            COALESCE(MAX(CASE WHEN genre_hint IS NOT NULL AND genre_hint != '' THEN genre_hint END), 'Unknown'),
            COUNT(DISTINCT source_name),
            GROUP_CONCAT(DISTINCT source_name),
            0.0,
            MAX(spotify_uri),
            MIN(discovered_date),
            MAX(discovered_date)
        FROM track_mentions
        GROUP BY artist_name_normalized, track_title_normalized
    """)

    # Update max_source_weight from SOURCE_WEIGHTS config
    rows = conn.execute("SELECT id, sources FROM scored_tracks").fetchall()
    for row in rows:
        sources = row["sources"].split(",") if row["sources"] else []
        max_weight = max((SOURCE_WEIGHTS.get(s.strip(), 1.0) for s in sources), default=1.0)
        conn.execute("UPDATE scored_tracks SET max_source_weight = ? WHERE id = ?",
                      (max_weight, row["id"]))

    conn.commit()
    conn.close()


def get_scored_tracks() -> list[ScoredTrack]:
    """Get all scored tracks sorted by total_score descending."""
    conn = get_connection()
    rows = conn.execute("""
        SELECT * FROM scored_tracks ORDER BY total_score DESC
    """).fetchall()
    conn.close()

    return [ScoredTrack(
        id=row["id"],
        artist_name=row["artist_name"],
        artist_name_normalized=row["artist_name_normalized"],
        track_title=row["track_title"],
        track_title_normalized=row["track_title_normalized"],
        album_name=row["album_name"],
        genre=row["genre"],
        source_count=row["source_count"],
        sources=row["sources"],
        max_source_weight=row["max_source_weight"],
        total_score=row["total_score"],
        spotify_uri=row["spotify_uri"],
        spotify_track_id=row["spotify_track_id"] if "spotify_track_id" in row.keys() else None,
        release_date=row["release_date"] if "release_date" in row.keys() else None,
        first_seen=row["first_seen"],
        last_seen=row["last_seen"],
    ) for row in rows]


def batch_update_scores(scores: dict):
    """Update total_score for multiple tracks in one transaction. scores = {track_id: score}"""
    conn = get_connection()
    conn.executemany(
        "UPDATE scored_tracks SET total_score = ? WHERE id = ?",
        [(score, tid) for tid, score in scores.items()]
    )
    conn.commit()
    conn.close()


def batch_update_genres(genres: dict):
    """Update genre for multiple tracks in one transaction. genres = {track_id: genre}"""
    conn = get_connection()
    conn.executemany(
        "UPDATE scored_tracks SET genre = ? WHERE id = ?",
        [(genre, tid) for tid, genre in genres.items()]
    )
    conn.commit()
    conn.close()


def update_track_spotify(track_id: int, spotify_uri: str, spotify_track_id: str,
                         release_date: str | None = None):
    conn = get_connection()
    conn.execute(
        "UPDATE scored_tracks SET spotify_uri = ?, spotify_track_id = ?, release_date = ? WHERE id = ?",
        (spotify_uri, spotify_track_id, release_date, track_id)
    )
    conn.commit()
    conn.close()


def get_unique_artists() -> list[str]:
    conn = get_connection()
    rows = conn.execute(
        "SELECT DISTINCT artist_name_normalized FROM scored_tracks"
    ).fetchall()
    conn.close()
    return [row["artist_name_normalized"] for row in rows]


# --- Playlist history ---

def record_playlist(name: str, spotify_id: str, track_count: int) -> int:
    conn = get_connection()
    cursor = conn.execute(
        "INSERT INTO playlists (playlist_name, spotify_playlist_id, created_date, track_count) VALUES (?, ?, ?, ?)",
        (name, spotify_id, datetime.now().isoformat(), track_count)
    )
    playlist_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return playlist_id


def record_playlist_tracks(playlist_id: int, tracks: list[ScoredTrack]):
    conn = get_connection()
    now = datetime.now().isoformat()
    for t in tracks:
        conn.execute("""
            INSERT OR IGNORE INTO playlist_tracks
                (playlist_id, spotify_uri, artist_name_normalized, track_title_normalized, added_at)
            VALUES (?, ?, ?, ?, ?)
        """, (playlist_id, t.spotify_uri, t.artist_name_normalized, t.track_title_normalized, now))
    conn.commit()
    conn.close()


def get_recently_played_keys(weeks: int = 8) -> set[tuple[str, str]]:
    """Get (artist_norm, track_norm) pairs from recent playlists."""
    cutoff = (datetime.now() - timedelta(weeks=weeks)).isoformat()
    conn = get_connection()
    rows = conn.execute("""
        SELECT artist_name_normalized, track_title_normalized
        FROM playlist_tracks WHERE added_at > ?
    """, (cutoff,)).fetchall()
    conn.close()
    return {(row["artist_name_normalized"], row["track_title_normalized"]) for row in rows}


# --- Genre cache ---

def get_cached_genre(artist_norm: str) -> Optional[str]:
    conn = get_connection()
    row = conn.execute(
        "SELECT genre FROM genre_cache WHERE artist_name_normalized = ?",
        (artist_norm,)
    ).fetchone()
    conn.close()
    return row["genre"] if row else None


def cache_genre(artist_norm: str, genre: str):
    conn = get_connection()
    conn.execute(
        "INSERT OR REPLACE INTO genre_cache (artist_name_normalized, genre, cached_at) VALUES (?, ?, ?)",
        (artist_norm, genre, datetime.now().isoformat())
    )
    conn.commit()
    conn.close()


# --- Spotify search cache ---

def get_cached_spotify(artist_norm: str, track_norm: str) -> Optional[dict]:
    key = f"{artist_norm}::{track_norm}"
    conn = get_connection()
    row = conn.execute(
        "SELECT spotify_uri, spotify_track_id, release_date FROM spotify_search_cache WHERE artist_track_key = ?",
        (key,)
    ).fetchone()
    conn.close()
    if row:
        return {
            "spotify_uri": row["spotify_uri"],
            "spotify_track_id": row["spotify_track_id"],
            "release_date": row["release_date"] if "release_date" in row.keys() else None,
        }
    return None


def get_unchecked_playlists() -> list[dict]:
    """Get playlists that haven't had feedback collected yet."""
    conn = get_connection()
    rows = conn.execute("""
        SELECT p.id, p.spotify_playlist_id, p.playlist_name, p.created_date
        FROM playlists p
        WHERE p.id NOT IN (SELECT DISTINCT playlist_id FROM playlist_feedback)
        ORDER BY p.created_date
    """).fetchall()
    conn.close()
    return [dict(row) for row in rows]


def get_playlist_track_ids(playlist_id: int) -> list[dict]:
    """Get spotify track info for tracks in a playlist."""
    conn = get_connection()
    rows = conn.execute("""
        SELECT pt.spotify_uri, pt.artist_name_normalized, pt.track_title_normalized,
               st.spotify_track_id
        FROM playlist_tracks pt
        LEFT JOIN scored_tracks st
            ON st.artist_name_normalized = pt.artist_name_normalized
            AND st.track_title_normalized = pt.track_title_normalized
        WHERE pt.playlist_id = ?
    """, (playlist_id,)).fetchall()
    conn.close()
    return [dict(row) for row in rows]


def insert_feedback(playlist_id: int, spotify_track_id: str, artist_norm: str,
                    was_saved: bool, was_removed: bool):
    conn = get_connection()
    conn.execute("""
        INSERT OR REPLACE INTO playlist_feedback
            (playlist_id, spotify_track_id, artist_name_normalized, was_saved, was_removed, checked_at)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (playlist_id, spotify_track_id, artist_norm, int(was_saved), int(was_removed),
          datetime.now().isoformat()))
    conn.commit()
    conn.close()


def rebuild_artist_affinity():
    """Recalculate artist_affinity from all playlist_feedback records."""
    conn = get_connection()
    now = datetime.now().isoformat()
    conn.execute("DELETE FROM artist_affinity")
    conn.execute("""
        INSERT INTO artist_affinity (artist_name_normalized, positive_count, negative_count, affinity_score, updated_at)
        SELECT
            artist_name_normalized,
            SUM(was_saved) as pos,
            SUM(was_removed) as neg,
            CASE
                WHEN SUM(was_saved) + SUM(was_removed) = 0 THEN 0.5
                ELSE ROUND(0.5 + 0.5 * (CAST(SUM(was_saved) AS REAL) - CAST(SUM(was_removed) AS REAL))
                     / (SUM(was_saved) + SUM(was_removed)), 4)
            END as score,
            ?
        FROM playlist_feedback
        GROUP BY artist_name_normalized
    """, (now,))
    conn.commit()
    conn.close()


def get_all_artist_affinities() -> dict:
    """Load all artist affinity scores into memory at once."""
    conn = get_connection()
    rows = conn.execute("SELECT artist_name_normalized, affinity_score FROM artist_affinity").fetchall()
    conn.close()
    return {row["artist_name_normalized"]: row["affinity_score"] for row in rows}


def cache_spotify(artist_norm: str, track_norm: str, spotify_uri: Optional[str],
                  spotify_track_id: Optional[str], release_date: Optional[str] = None):
    key = f"{artist_norm}::{track_norm}"
    conn = get_connection()
    conn.execute(
        "INSERT OR REPLACE INTO spotify_search_cache (artist_track_key, spotify_uri, spotify_track_id, release_date, cached_at) VALUES (?, ?, ?, ?, ?)",
        (key, spotify_uri, spotify_track_id, release_date, datetime.now().isoformat())
    )
    conn.commit()
    conn.close()
