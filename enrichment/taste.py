"""Load spotify-brain taste profile and score tracks against it."""
import json
import logging
from pathlib import Path

from config import TASTE_PROFILE_PATH
from storage.database import normalize_artist

logger = logging.getLogger("enrichment.taste")


class TasteProfile:
    """Loads and queries the spotify-brain fingerprint for track scoring."""

    def __init__(self, profile_path: Path = TASTE_PROFILE_PATH):
        self.top_artists = {}  # normalized_name -> weight
        self.decade_weights = {}  # "2020s" -> fraction
        self.loaded = False

        if not profile_path.exists():
            logger.info("No taste profile found, using neutral scoring")
            return

        try:
            with open(profile_path) as f:
                data = json.load(f)

            # Build artist lookup (normalized name -> weight)
            for artist in data.get("top_artists", []):
                name = artist.get("name", "")
                weight = artist.get("weight", 0.0)
                if name:
                    self.top_artists[normalize_artist(name)] = weight

            # Decade distribution
            self.decade_weights = data.get("decade_distribution", {})

            self.loaded = True
            logger.info(f"Taste profile loaded: {len(self.top_artists)} top artists, "
                        f"{len(self.decade_weights)} decades")
        except Exception as e:
            logger.warning(f"Failed to load taste profile: {e}")

    def score_track(self, artist_name_normalized: str) -> float:
        """Return 0-1 similarity score for a track against taste profile.

        Uses artist familiarity as a mild signal, not a gate.
        Unknown artists score neutral (0.5) because the user actively
        explores new music — a single play doesn't indicate preference,
        and the saved library is too sparse to penalize unknowns.
        """
        if not self.loaded:
            return 0.5  # neutral

        # Check if artist is in top artists
        if artist_name_normalized in self.top_artists:
            weight = self.top_artists[artist_name_normalized]
            return min(1.0, 0.6 + weight * 15)  # familiar artist: 0.6-0.9

        # Check for partial artist match (e.g., "tyler creator" in "tyler, the creator")
        for known_artist, weight in self.top_artists.items():
            if known_artist in artist_name_normalized or artist_name_normalized in known_artist:
                return min(1.0, 0.55 + weight * 10)

        # Unknown artist — neutral, don't penalize discovery
        return 0.5


_taste_profile = None


def get_taste_profile() -> TasteProfile:
    """Get singleton taste profile instance."""
    global _taste_profile
    if _taste_profile is None:
        _taste_profile = TasteProfile()
    return _taste_profile
