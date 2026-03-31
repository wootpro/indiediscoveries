"""IndieMusic Discovery - Main entry point."""
import logging
import sys

from config import LOG_FILE, MAX_TRACKS


def setup_logging():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        handlers=[
            logging.FileHandler(str(LOG_FILE), encoding="utf-8"),
            logging.StreamHandler(sys.stdout),
        ],
    )


def main():
    setup_logging()
    logger = logging.getLogger("main")
    logger.info("=" * 60)
    logger.info("IndieMusic Discovery starting")

    # 1. Initialize database
    from storage.database import (
        init_db, insert_track_mention, batch_insert_track_mentions,
        clean_old_mentions, build_scored_tracks, get_scored_tracks,
        batch_update_scores, batch_update_genres, update_track_spotify,
        normalize_track,
    )
    from storage.models import RawTrack
    init_db()
    clean_old_mentions()

    # 2. Collect feedback from previous playlists, load affinity scores into memory
    from enrichment.feedback import collect_feedback, load_affinity_cache
    try:
        collect_feedback()
    except Exception as e:
        logger.warning(f"Feedback collection failed (non-fatal): {e}")
        load_affinity_cache()  # still load whatever affinity data exists

    # 3. Run all scrapers
    from scrapers import get_all_scrapers
    all_raw_tracks = []
    scrapers = get_all_scrapers()

    if not scrapers:
        logger.warning("No scrapers available!")
        return

    source_stats = {}
    for scraper in scrapers:
        try:
            logger.info(f"Running scraper: {scraper.name}")
            tracks = scraper.scrape()
            logger.info(f"  -> {len(tracks)} tracks found")
            all_raw_tracks.extend(tracks)
            source_stats[scraper.name] = {"count": len(tracks), "status": "ok"}
        except Exception as e:
            logger.error(f"  -> Scraper {scraper.name} FAILED: {e}", exc_info=True)
            source_stats[scraper.name] = {"count": 0, "status": f"FAILED: {e}"}

    raw_count = len(all_raw_tracks)
    logger.info(f"Total raw track mentions: {raw_count}")

    # 4. Store track mentions
    batch_insert_track_mentions(all_raw_tracks)

    # 5. Build scored tracks (aggregate mentions)
    build_scored_tracks()
    scored_tracks = get_scored_tracks()
    scored_count = len(scored_tracks)
    logger.info(f"Unique tracks after dedup: {scored_count}")

    # 6. Enrich genres — only for artists on tracks likely to make the playlist.
    #    First do a quick partial score (without genre), pre-filter, then enrich
    #    only the survivors. This avoids MusicBrainz lookups for tracks that will
    #    be filtered out anyway.
    from enrichment.genre import lookup_genre
    from scoring.ranker import score_all_tracks
    from scoring.filters import apply_pre_spotify_filters, apply_post_spotify_filters, filter_dealbreaker_genres

    # 6a. Partial score (genre data may be stale/unknown — that's fine for ranking)
    scored_tracks = score_all_tracks(scored_tracks)

    # 6b. Pre-filter (dealbreaker genres from cache, remastered, already-played, artist limit)
    pre_filtered = apply_pre_spotify_filters(scored_tracks)
    logger.info(f"Tracks after pre-Spotify filters: {len(pre_filtered)} (from {scored_count})")

    # 6c. Take a generous candidate pool (2.5x playlist size) for genre enrichment
    CANDIDATE_POOL = int(MAX_TRACKS * 2.5)
    candidates = pre_filtered[:CANDIDATE_POOL]

    # 6d. Enrich genres only for candidate artists
    candidate_artists = {t.artist_name_normalized for t in candidates if t.genre == "Unknown"}
    logger.info(f"Enriching genres for {len(candidate_artists)} candidate artists...")

    genre_updates = {}
    for artist_norm in candidate_artists:
        try:
            genre = lookup_genre(artist_norm, artist_norm)
            for track in candidates:
                if track.artist_name_normalized == artist_norm and track.genre == "Unknown":
                    track.genre = genre
                    genre_updates[track.id] = genre
        except Exception as e:
            logger.warning(f"Genre enrichment failed for '{artist_norm}': {e}")
    if genre_updates:
        batch_update_genres(genre_updates)

    # 6e. Re-score candidates with updated genre data, re-sort, batch persist
    candidates = score_all_tracks(candidates)
    batch_update_scores({t.id: t.total_score for t in candidates})

    # 6f. Re-filter dealbreaker genres only (remastered/already-played/artist-limit
    #     don't change between passes) then trim to candidate pool
    candidates = filter_dealbreaker_genres(candidates)
    candidates = candidates[:CANDIDATE_POOL]
    logger.info(f"Candidates for Spotify search: {len(candidates)}")

    # 7. Expand AOTY album entries into real tracks, then search Spotify
    #    Only search the candidate pool, not all scored tracks.
    from spotify.search import search_track, search_album_tracks, RateLimitError

    rate_limited = False

    # For AOTY entries, search by album to get actual track names
    aoty_tracks = [t for t in candidates if "album_of_the_year" in t.sources and not t.spotify_uri]
    if aoty_tracks and not rate_limited:
        logger.info(f"Expanding {len(aoty_tracks)} AOTY album entries into tracks...")
        expanded = []
        try:
            for track in aoty_tracks:
                album_results = search_album_tracks(track.artist_name, track.track_title, max_tracks=3)
                if album_results:
                    first = album_results[0]
                    track.track_title = first["track_title"]
                    track.track_title_normalized = normalize_track(first["track_title"])
                    track.spotify_uri = first["spotify_uri"]
                    track.spotify_track_id = first["spotify_track_id"]
                    track.release_date = first.get("release_date")
                    update_track_spotify(track.id, first["spotify_uri"], first["spotify_track_id"], first.get("release_date"))

                    for extra in album_results[1:]:
                        insert_track_mention(RawTrack(
                            artist_name=extra["artist_name"],
                            track_title=extra["track_title"],
                            source_name="album_of_the_year",
                            album_name=extra.get("album_name"),
                            spotify_uri=extra["spotify_uri"],
                        ))
                        expanded.append(extra)
        except RateLimitError as e:
            logger.warning(f"Spotify rate limit hit during AOTY expansion: {e}")
            rate_limited = True

        if expanded:
            logger.info(f"  Expanded into {len(expanded)} additional tracks from AOTY albums")

    # Search Spotify only for candidate tracks without URIs
    no_uri_count = sum(1 for t in candidates if not t.spotify_uri)
    if no_uri_count and not rate_limited:
        logger.info(f"Searching Spotify for {no_uri_count} candidate tracks (skipped {scored_count - len(candidates)} low-ranked)...")
        searched = 0
        try:
            for track in candidates:
                if not track.spotify_uri:
                    result = search_track(track.artist_name, track.track_title)
                    searched += 1
                    if result:
                        track.spotify_uri = result["spotify_uri"]
                        track.spotify_track_id = result["spotify_track_id"]
                        track.release_date = result.get("release_date")
                        update_track_spotify(track.id, result["spotify_uri"], result["spotify_track_id"], result.get("release_date"))
        except RateLimitError as e:
            logger.warning(f"Spotify rate limit hit after {searched}/{no_uri_count} searches: {e}")
            rate_limited = True

    if rate_limited:
        cached_uri_count = sum(1 for t in candidates if t.spotify_uri)
        logger.info(f"Rate limited — proceeding with {cached_uri_count} cached Spotify URIs")

    # 8. Apply post-Spotify filters (remove tracks without URIs)
    filtered_tracks = apply_post_spotify_filters(candidates)
    after_filter_count = len(filtered_tracks)
    logger.info(f"Tracks after all filtering: {after_filter_count}")

    # 9. Create playlist (top MAX_TRACKS)
    playlist_tracks = filtered_tracks[:MAX_TRACKS]
    from spotify.playlist import create_weekly_playlist
    playlist_url = create_weekly_playlist(playlist_tracks)

    # 10. Log summary and generate HTML report
    from reporting.logger import log_summary, generate_html_report
    log_summary(
        raw_count=raw_count,
        scored_count=scored_count,
        after_filter_count=after_filter_count,
        playlist_count=len(playlist_tracks),
        playlist_url=playlist_url,
    )
    generate_html_report(
        raw_count=raw_count,
        scored_count=scored_count,
        after_filter_count=after_filter_count,
        playlist_tracks=playlist_tracks,
        playlist_url=playlist_url,
        source_stats=source_stats,
        rate_limited=rate_limited,
    )

    logger.info("Done!")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        logging.exception("Unhandled exception in main")
        sys.exit(1)
