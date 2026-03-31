"""Abstract base scraper with shared HTTP, rate limiting, and retry logic."""
import logging
import time
from abc import ABC, abstractmethod

import requests
from tenacity import retry, stop_after_attempt, wait_exponential

from config import USER_AGENT, REQUEST_DELAY_SECONDS
from storage.models import RawTrack


class BaseScraper(ABC):
    """All scrapers inherit from this."""

    def __init__(self, name: str):
        self.name = name
        self.logger = logging.getLogger(f"scraper.{name}")
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": USER_AGENT})
        self._last_request_time = 0.0

    def _rate_limit(self, delay: float = REQUEST_DELAY_SECONDS):
        elapsed = time.time() - self._last_request_time
        if elapsed < delay:
            time.sleep(delay - elapsed)
        self._last_request_time = time.time()

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=2, max=30))
    def fetch(self, url: str) -> str:
        """Fetch a URL with rate limiting and retry."""
        self._rate_limit()
        resp = self.session.get(url, timeout=30)
        resp.raise_for_status()
        return resp.text

    @abstractmethod
    def scrape(self) -> list[RawTrack]:
        """Return list of RawTrack objects. Must handle own exceptions."""
        ...
