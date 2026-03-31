"""Score tracks based on source weight, mention count, genre match, taste profile, and recency."""
import logging
import math
from datetime import date

from config import SOURCE_WEIGHTS, SCORING_WEIGHTS, PREFERRED_GENRES
from enrichment.taste import get_taste_profile
from enrichment.feedback import get_feedback_score
from storage.models import ScoredTrack

logger = logging.getLogger("scoring.ranker")

MAX_SOURCE_WEIGHT = max(SOURCE_WEIGHTS.values()) if SOURCE_WEIGHTS else 3.0


def _genre_match_score(genre: str) -> float:
    """Return 1.0 if genre matches preferred, 0.6 if unknown (benefit of doubt), 0.0 if known-bad."""
    if genre == "Unknown":
        return 0.6  # unknown genre gets benefit of the doubt for a discovery-oriented listener
    genre_lower = genre.lower()
    for pref in PREFERRED_GENRES:
        if pref in genre_lower:
            return 1.0
    # Known genre but not in preferred list — not a dealbreaker, just less likely to match
    return 0.15


def compute_score(track: ScoredTrack) -> float:
    """Compute total score for a track."""
    scores = {}
    taste = get_taste_profile()

    # Source weight (0-1): how trusted is the best source that mentioned this track
    scores["source_weight"] = track.max_source_weight / MAX_SOURCE_WEIGHT

    # Source count (0-1, log-scaled): multiple independent sources = strong signal
    scores["source_count"] = min(1.0, math.log2(1 + track.source_count) / math.log2(5))

    # Genre match (0, 0.5, or 1): broad genre list tuned to Peter's taste
    scores["genre_match"] = _genre_match_score(track.genre)

    # Taste profile (mild signal — sparse library, single plays ≠ preference)
    scores["taste_profile"] = taste.score_track(track.artist_name_normalized)

    # Feedback (0-1): learned from user engagement with previous playlists
    scores["feedback"] = get_feedback_score(track.artist_name_normalized)

    # Recency (0-1, linear decay over 14 days — wider window for weekly runs)
    if track.first_seen:
        try:
            first = date.fromisoformat(track.first_seen)
            days_old = (date.today() - first).days
            scores["recency"] = max(0.0, 1.0 - days_old / 14.0)
        except ValueError:
            scores["recency"] = 0.5
    else:
        scores["recency"] = 0.5

    total = sum(scores.get(k, 0.5) * w for k, w in SCORING_WEIGHTS.items())
    return round(total, 4)


def score_all_tracks(tracks: list[ScoredTrack]) -> list[ScoredTrack]:
    """Score all tracks and return sorted by score descending."""
    for track in tracks:
        track.total_score = compute_score(track)

    tracks.sort(key=lambda t: t.total_score, reverse=True)
    logger.info(f"Scored {len(tracks)} tracks (top score: {tracks[0].total_score if tracks else 0})")
    return tracks
