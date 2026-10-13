from random import shuffle
from secrets import choice

import spotipy

from daily_drive.config import Settings
from daily_drive.core.auth import Auth
from daily_drive.core.logging import setup_logger
from services.playlist_service import PlaylistService
from services.podcast_service import PodcastService
from services.user_service import UserService

#refresh pipeline
#0

def _start_services(sp: spotipy.Spotify) -> tuple[PlaylistService, UserService, PodcastService]:
    settings = Settings()
    playlist_service = PlaylistService(sp, settings.podcasts)
    user_service = UserService(sp)
    podcast_service = PodcastService(sp)
    return playlist_service, user_service, podcast_service


def _random_time_range() -> str:
    return choice(["short_term", "medium_term", "long_term"])


def main() -> None:
    log = setup_logger()
    settings = Settings()
    tracks = []

    if not settings.spotify_client_id or not settings.spotify_client_secret:
        log.error("Spotify credentials not found.")
        return

    auth = Auth(
        settings.spotify_client_id,
        settings.spotify_client_secret,
        settings.spotify_redirect_uri,
        settings.spotify_scope,
    )
    sp = auth.authenticate()
    log.info("Successfully authenticated with Spotify API.")

    playlist_service, user_service, podcast_service = _start_services(sp)
    log.info("Services initialized successfully.")

    for i in range(3):
        # Get top tracks
        tracks.extend(user_service.get_user_top_tracks(
            time_range=_random_time_range(),
            offset=i*50,
            limit=50
        ))
    shuffle(tracks)
    log.info(f"Retrieved {len(tracks)} top tracks for the user.")

    required_track_count = PlaylistService.required_track_count(
        len(settings.podcasts),
        settings.daily_drive_tracks_after_welcome,
        settings.daily_drive_tracks_between_episodes,
        settings.daily_drive_final_tracks,
    )

    # Discover tracks based on the user's top artists
    original_track_ids = {track.id for track in tracks if track.id}

    artist_names = []
    for time_range in ("short_term", "medium_term", "long_term"):
        top_artists = user_service.get_user_top_artists(
            time_range=time_range,
            limit=20,
        )
        artist_names.extend(
            artist.name for artist in top_artists if artist.name
        )

    artist_names = list(dict.fromkeys(artist_names))
    discovered_tracks = user_service.search_new_tracks(
        artist_names,
        limit=100,
    )

    new_tracks = []
    seen_ids = set(original_track_ids)

    for track in discovered_tracks:
        if track.id and track.id not in seen_ids:
            new_tracks.append(track)
            seen_ids.add(track.id)

        if len(new_tracks) == 3:
            break

    # Preserve playlist length and replace only the last three tracks
    tracks = tracks[:required_track_count]

    if len(tracks) >= 3 and len(new_tracks) == 3:
        tracks = tracks[:-3] + new_tracks
        log.info("Added 3 new track discoveries.")
    else:
        log.warning(
            f"Found only {len(new_tracks)} new tracks; "
            "keeping the original selection."
        )

    log.info(
        f"Using {len(tracks)} tracks for the playlist structure "
        f"(required={required_track_count})."
    )

    # Get podcast episodes
    podcast_episodes = []
    for podcast in playlist_service.podcasts:
        episode = podcast_service.get_last_podcast_episode(podcast=podcast)
        if episode:
            podcast_episodes.append(episode)
        else:
            log.warning(f"Episode for podcast '{podcast.name}' not found.")

    log.info(
        f"Retrieved {len(podcast_episodes)} podcast episodes for the user.")

    # Create/update daily drive playlist
    result = playlist_service.create_daily_drive_playlist(
        tracks,
        podcast_episodes,
        tracks_after_welcome=settings.daily_drive_tracks_after_welcome,
        tracks_between_episodes=settings.daily_drive_tracks_between_episodes,
        final_tracks=settings.daily_drive_final_tracks,
    )
    log.info(result)


if __name__ == "__main__":
    main()
