import time
from pathlib import Path

import tidalapi as td

from _library.errors import SearchError
from .base import MusicService, ArtistResult, Track


class TidalService(MusicService):
    """Wraps the TIDAL API (via the unofficial python-tidal/tidalapi library) behind
    the common MusicService interface.

    Unlike Spotify, TIDAL doesn't need a client id/secret from the user - tidalapi
    ships with working default app credentials and authenticates through an
    interactive OAuth device-code flow instead (visit a URL, log in, done). That
    flow only needs to happen once: the resulting session is cached to
    SESSION_FILE and silently reused (refreshing the access token as needed) on
    later runs, the same way spotipy caches its own token in the background for
    SpotifyService. So EXTRA_CREDENTIAL_KEYS stays empty here - the only
    credentials this service asks for are the playlist ids every service needs.

    Note: TIDAL artists don't carry genre tags the way Spotify's do, so
    ArtistResult.genres is always empty here. general_settings.genre_source:
    'Spotify' won't produce any genre data while music_service is 'Tidal'.
    """

    SESSION_FILE = 'tidal_session.json'

    def __init__(self, credentials, sleep_time=0, verbose=False, error_logger=None):
        super().__init__(credentials, sleep_time=sleep_time, verbose=verbose, error_logger=error_logger)
        self.session = td.Session()
        # Loads a previously saved session from SESSION_FILE if there is one and it's
        # still valid; otherwise walks through the interactive OAuth login and saves
        # the result to SESSION_FILE for next time.
        self.session.login_session_file(Path(self.SESSION_FILE))
        self._playlist_cache = {}  # playlist_id -> tidalapi Playlist, populated by _get_playlist

    @staticmethod
    def _to_track(track):
        if track.artist is not None:
            artist_name = track.artist.name
        elif track.artists:
            artist_name = track.artists[0].name
        else:
            artist_name = ''
        return Track(id=str(track.id),
                    name=track.name,
                    artist_name=artist_name,
                    duration_ms=(track.duration or 0) * 1000)  # TIDAL reports duration in seconds

    def search_artist(self, artist_name, max_retries=3):
        for attempt in range(max_retries):
            try:
                search_results = self.session.search(artist_name, models=[td.Artist], limit=50)
                time.sleep(self.sleep_time)
                return [ArtistResult(id=str(artist.id), name=artist.name, genres=[])
                       for artist in search_results['artists']]
            except KeyboardInterrupt:
                raise
            except Exception as e:
                self.error_logger("Tidal artist search error I want to be able to handle:", True)
                self.error_logger(e, True)
                if attempt < max_retries - 1:
                    time.sleep(2 ** attempt)  # exponential backoff before retrying: 1s, 2s, 4s, ...
        raise SearchError(artist_name)

    def get_artist_top_tracks(self, artist_id):
        tracks = self.session.artist(artist_id).get_top_tracks(limit=50)
        time.sleep(self.sleep_time)
        return [self._to_track(track) for track in tracks]

    def get_artist_all_tracks(self, artist_id):
        albums = self.session.artist(artist_id).get_albums(limit=50)
        time.sleep(self.sleep_time)
        tracks = []
        for album in albums:
            tracks.extend(album.tracks())
            time.sleep(self.sleep_time)
        return [self._to_track(track) for track in tracks]

    def _get_playlist(self, playlist_id):
        """Returns the tidalapi Playlist for playlist_id, fetching it once and reusing
        it for the rest of this service's lifetime - empty_playlist and add_to_playlist
        are always called back-to-back on the same playlist_id, so this halves the
        playlist-fetch calls for a farm_crowns/steal_crowns run.
        """
        if playlist_id not in self._playlist_cache:
            self._playlist_cache[playlist_id] = self.session.playlist(playlist_id)
        return self._playlist_cache[playlist_id]

    def empty_playlist(self, playlist_id):
        """Empties a TIDAL playlist of its entries."""
        playlist = self._get_playlist(playlist_id)
        counter = playlist.num_tracks
        playlist.clear()
        time.sleep(self.sleep_time)
        if self.verbose:
            print(f"Removed {counter} tracks from playlist")
        return True

    def add_to_playlist(self, track_ids, playlist_id):
        """Adds tracks to a TIDAL playlist.
        Chunked to 100 at a time, matching the pattern used for Spotify - TIDAL's API
        isn't documented as having the same hard limit, but there's no upside to risking it.
        """
        playlist = self._get_playlist(playlist_id)
        number_of_tracks = len(track_ids)
        tracks_added = 0
        while tracks_added < number_of_tracks:
            playlist.add(track_ids[tracks_added:tracks_added + 100])
            time.sleep(self.sleep_time)
            tracks_added += 100
        if self.verbose:
            print(f"Added {number_of_tracks} tracks to playlist")
        return True
