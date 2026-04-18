# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Running the pipeline

```bash
python main.py
```

This runs the full discovery pipeline and opens `last_run_report.html` when done. There is no test suite and no linter configured.

## Required setup before first run

- Copy `.env.example` to `.env` and add Spotify credentials (`SPOTIFY_CLIENT_ID`, `SPOTIFY_CLIENT_SECRET`)
- Copy `user_config.yaml.example` to `user_config.yaml` and configure preferences
- Both files are gitignored

## Architecture

The pipeline is a linear sequence orchestrated entirely in `main.py`. There is no framework — just function calls in order.

**Configuration is split across three layers:**
- `config.py` — infrastructure constants (paths, delays, request settings) and defaults; reads `user_config.yaml` and `.env` at import time
- `user_config.yaml` — user preferences: `preferred_genres`, `dealbreaker_genres`, `enabled_scrapers`, `source_weights`, `playlist.max_tracks`
- `.env` — Spotify OAuth credentials only

**Pipeline stages (in execution order):**
1. `storage/database.py` — init SQLite DB; prune mentions older than `LOOKBACK_DAYS`
2. `enrichment/feedback.py` — check previous Spotify playlists for saves/removals; update `artist_affinity` table
3. `scrapers/` — run each enabled scraper; results go into `track_mentions` table
4. `storage/database.py` `build_scored_tracks()` — aggregate mentions into `scored_tracks` (dedup by normalized artist+title)
5. `scoring/ranker.py` — first-pass score without fresh genre data; sort descending
6. `scoring/filters.py` `apply_pre_spotify_filters()` — remove dealbreakers, remasters, already-played (8-week window), >3 tracks/artist
7. Genre enrichment (MusicBrainz, `enrichment/genre.py`) — only for top 2.5× playlist size candidates, not all tracks
8. Re-score with genre data; Spotify URI search (`spotify/search.py`) for candidates only
9. `scoring/filters.py` `apply_post_spotify_filters()` — remove tracks older than `MAX_RELEASE_AGE_YEARS` and those not found on Spotify
10. `spotify/playlist.py` — create playlist with top `MAX_TRACKS` tracks
11. `reporting/logger.py` — write `indie_music.log` and `last_run_report.html`

**Two-pass scoring is intentional:** genre enrichment is expensive (MusicBrainz rate-limits at 1.1s/request), so the pipeline pre-filters by partial score first, then only enriches the candidate pool (step 6c in `main.py`).

## Data models

`storage/models.py` defines three dataclasses:
- `RawTrack` — one scraper mention (artist, title, source, optional Spotify URI)
- `ScoredTrack` — deduplicated aggregate with computed `total_score`, genre, `source_count`, `sources` (comma-separated)
- `PlaylistRecord` — created playlist metadata

Deduplication keys: `normalize_artist()` and `normalize_track()` in `database.py` strip features, collabs, remixes, and bracketed suffixes before matching.

## Scoring formula

Six signals in `scoring/ranker.py`, weights configurable in `user_config.yaml` under `scoring_weights`:

| Signal | Default weight | Notes |
|---|---|---|
| `source_weight` | 0.25 | Trust score of the highest-weight source |
| `source_count` | 0.20 | Log-scaled; 5 sources = full score |
| `genre_match` | 0.20 | 1.0 preferred / 0.6 unknown / 0.15 other |
| `release_recency` | 0.20 | Linear decay to 0 at `MAX_RELEASE_AGE_YEARS` |
| `recency` | 0.05 | Days since first seen (14-day window) |
| `taste_profile` | 0.05 | From `taste_profile.json` (optional) |
| `feedback` | 0.05 | Learned from Spotify save/remove signals |

Unknown genre scores 0.6, not 0.0 — discovery-oriented design choice.

## Adding a new scraper

1. Create `scrapers/yourname.py` — subclass `BaseScraper`, implement `scrape() -> list[RawTrack]`
2. Add an entry to `_SCRAPER_MAP` in `scrapers/__init__.py`
3. Add a default weight in `config.py` under `_default_weights`
4. Enable it by adding the key to `enabled_scrapers` in `user_config.yaml`

`BaseScraper.fetch()` handles rate limiting (2s between requests) and retry (3 attempts, exponential backoff) automatically.

## SQLite caching

The DB at `storage/indie_music.db` contains two persistent caches that survive between runs:
- `genre_cache` — MusicBrainz genre lookups (permanent; never expires)
- `spotify_search_cache` — Spotify URI lookups keyed by `artist_norm::track_norm`

Delete the DB to force a full re-scrape. The feedback loop (`playlist_feedback`, `artist_affinity`) also lives here and accumulates over time.
