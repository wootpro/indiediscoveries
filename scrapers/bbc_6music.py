"""Scrape BBC Radio 6 Music tracklists via public BBC APIs.

Step 1: Fetch recent broadcasts from rms.api.bbc.co.uk to get episode PIDs
Step 2: Hit /programmes/{pid}/segments.json for each episode's full tracklist
"""
import logging
from datetime import date

from scrapers.base import BaseScraper
from storage.models import RawTrack

logger = logging.getLogger("scraper.bbc_6music")

BROADCASTS_URL = "https://rms.api.bbc.co.uk/v2/broadcasts/latest"
SEGMENTS_URL = "https://www.bbc.co.uk/programmes/{pid}/segments.json"


class BBC6MusicScraper(BaseScraper):
    """Scrape BBC Radio 6 Music tracklists from recent broadcasts."""

    def __init__(self):
        super().__init__("bbc_6music")

    def scrape(self) -> list[RawTrack]:
        episode_pids = self._get_recent_episodes()
        self.logger.info(f"Found {len(episode_pids)} recent BBC 6 Music episodes")

        tracks = []
        seen = set()

        for pid in episode_pids:
            try:
                self._rate_limit(0.5)
                episode_tracks = self._get_tracklist(pid)
                for artist, title in episode_tracks:
                    key = (artist.lower(), title.lower())
                    if key not in seen:
                        seen.add(key)
                        tracks.append(RawTrack(
                            artist_name=artist,
                            track_title=title,
                            source_name="bbc_6music",
                            source_url=f"https://www.bbc.co.uk/programmes/{pid}",
                            discovered_date=date.today(),
                        ))
            except Exception as e:
                self.logger.debug(f"BBC 6 Music tracklist failed for {pid}: {e}")

        self.logger.info(f"Found {len(tracks)} unique tracks from BBC 6 Music")
        return tracks

    def _get_recent_episodes(self) -> list[str]:
        """Fetch recent broadcast episode PIDs."""
        try:
            resp = self.session.get(
                BROADCASTS_URL,
                params={"service": "bbc_6music"},
                timeout=30,
            )
            resp.raise_for_status()
            data = resp.json()

            pids = []
            for broadcast in data.get("data", []):
                programme = broadcast.get("programme", {})
                pid = programme.get("id", "")
                if pid:
                    pids.append(pid)

            return pids

        except Exception as e:
            self.logger.error(f"BBC 6 Music broadcasts API failed: {e}")
            return []

    def _get_tracklist(self, pid: str) -> list[tuple[str, str]]:
        """Fetch tracklist for a specific episode PID."""
        url = SEGMENTS_URL.format(pid=pid)
        resp = self.session.get(url, timeout=15)
        resp.raise_for_status()
        data = resp.json()

        tracks = []
        for item in data.get("segment_events", []):
            segment = item.get("segment", {})
            if segment.get("type") != "music":
                continue

            artist = segment.get("artist", "").strip()
            title = segment.get("track_title", "").strip()
            if artist and title:
                tracks.append((artist, title))

        return tracks
