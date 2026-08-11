import time

import requests
import urllib3
import spotipy as sp

from _library.errors import SearchError
from .base import MusicService, ArtistResult, Track


class SpotifyService(MusicService):
    """Wraps the Spotify Web API (via spotipy) behind the common MusicService interface.

    This is a straight move of the Spotify-specific code that used to live directly on
    Playlist_Generator - behavior is unchanged, it's just reachable through self.service
    now instead of self.spot/self.<method> so other services can sit alongside it.
    """

    EXTRA_CREDENTIAL_KEYS = ['CLIENT_ID', 'CLIENT_SECRET']

    def __init__(self, credentials, sleep_time=0, verbose=False, error_logger=None):
        super().__init__(credentials, sleep_time=sleep_time, verbose=verbose, error_logger=error_logger)
        session = requests.Session()
        retry = urllib3.Retry(
            total=0,
            connect=None,
            read=0,
            allowed_methods=frozenset(['GET', 'POST', 'PUT', 'DELETE']),
            status=0,
            backoff_factor=0.3,
            status_forcelist=(429, 500, 502, 503, 504),
            respect_retry_after_header=False  # <---
        )
        adapter = requests.adapters.HTTPAdapter(max_retries=retry)
        session.mount('http://', adapter)
        session.mount('https://', adapter)
        self.spot = sp.Spotify(auth_manager=sp.oauth2.SpotifyOAuth(
            client_id=credentials['CLIENT_ID'],
            client_secret=credentials['CLIENT_SECRET'],
            redirect_uri="https://127.0.0.1:8080",
            scope="playlist-modify-public"
        ), requests_session=session)
        self._user_id = None  # lazily fetched and cached by _get_user_id - can't change during a run

    @staticmethod
    def _to_track(track):
        return Track(id=track['uri'],
                    name=track['name'],
                    artist_name=track['artists'][0]['name'],
                    duration_ms=track['duration_ms'])

    def search_artist(self, artist_name, max_retries=3):
        for attempt in range(max_retries):
            try:
                search_results = self.spot.search(q=artist_name, limit=50, type='artist')
                time.sleep(self.sleep_time)
                return [ArtistResult(id=item['uri'], name=item['name'], genres=item['genres'])
                       for item in search_results["artists"]["items"]]
            except KeyboardInterrupt:
                raise
            except Exception as e:
                self.error_logger("Spotify artist search error I want to be able to handle:", True)
                self.error_logger(e, True)
                if attempt < max_retries - 1:
                    time.sleep(2 ** attempt)  # exponential backoff before retrying: 1s, 2s, 4s, ...
        raise SearchError(artist_name)

    def get_artist_top_tracks(self, artist_id):
        tracks = self.spot.artist_top_tracks(artist_id)["tracks"]
        time.sleep(self.sleep_time)
        return [self._to_track(track) for track in tracks]

    def get_artist_all_tracks(self, artist_id):
        album_ids = [a['uri'] for a in self.spot.artist_albums(artist_id)['items']]
        time.sleep(self.sleep_time)
        tracks = []
        for album_id in album_ids:
            tracks.extend(self.spot.album_tracks(album_id)['items'])
            time.sleep(self.sleep_time)
        return [self._to_track(track) for track in tracks]

    def empty_playlist(self, playlist_id):
        """Empties a Spotify playlist of its entries.
        Because of limitations, only a hundred tracks are removed at a time.
        """
        tracks = self.spot.playlist_items(playlist_id)["items"]
        time.sleep(self.sleep_time)
        counter = len(tracks)
        while len(tracks):
            self.spot.playlist_remove_all_occurrences_of_items(
                playlist_id, [track["track"]["uri"] for track in tracks])
            time.sleep(self.sleep_time)
            tracks = self.spot.playlist_items(playlist_id)["items"]
            time.sleep(self.sleep_time)
            counter += len(tracks)
        if self.verbose:
            print(f"Removed {counter} tracks from playlist")
        return True

    def _get_user_id(self):
        if self._user_id is None:
            self._user_id = self.spot.me()['id']
        return self._user_id

    def add_to_playlist(self, track_ids, playlist_id):
        """Adds tracks to a Spotify playlist.
        Because of limitations, only a hundred tracks are added at a time.
        """
        number_of_tracks = len(track_ids)
        tracks_added = 0
        user_id = self._get_user_id()
        while tracks_added < number_of_tracks:
            self.spot.user_playlist_add_tracks(user=user_id,
                                               playlist_id=playlist_id,
                                               tracks=track_ids[tracks_added:tracks_added + 100])
            time.sleep(self.sleep_time)
            tracks_added += 100
        if self.verbose:
            print(f"Added {number_of_tracks} tracks to playlist")
        return True
