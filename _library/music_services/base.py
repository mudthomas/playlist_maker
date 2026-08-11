from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List


@dataclass(frozen=True)
class ArtistResult:
    """A single artist search result, normalized across music services.

    Attributes:
        id (str): The service's identifier for this artist (e.g. a Spotify URI).
        name (str): The artist's display name, as returned by the service.
        genres ([str]): Genre tags for the artist, if the service exposes any.
            Services that don't provide per-artist genres (most don't) should
            always return an empty list here rather than omitting the field.
    """
    id: str
    name: str
    genres: List[str] = field(default_factory=list)


@dataclass(frozen=True)
class Track:
    """A single track, normalized across music services.

    Attributes:
        id (str): The service's identifier for this track, suitable for adding
            straight to a playlist (e.g. a Spotify track URI).
        name (str): The track's title.
        artist_name (str): The name of the track's primary/first-billed artist.
        duration_ms (int): Track length in milliseconds.
    """
    id: str
    name: str
    artist_name: str
    duration_ms: int


class MusicService(ABC):
    """Common interface a music-playback backend must implement so Playlist_Generator
    can drive playlist creation without knowing which service is behind it.

    To add a new service (e.g. Tidal):
        1. Subclass MusicService and implement the abstract methods below,
           returning ArtistResult/Track objects from base.py so the rest of the
           code never has to know which service it's talking to.
        2. Set EXTRA_CREDENTIAL_KEYS to whatever credential fields (beyond the
           playlist ids every service needs) your service requires - Playlist_Generator
           uses this to know what to prompt for on first run.
        3. Register the class in this package's __init__.py MUSIC_SERVICES dict,
           keyed by the name users will write in config.yaml's music_service setting.
    That's it - farm_crowns/steal_crowns and the rest of Playlist_Generator don't change.
    """

    #: Credential keys (beyond FARMING_PLAYLIST_ID/STEALING_PLAYLIST_ID, which every
    #: service needs since every service writes to two playlists) required to
    #: authenticate with this service. E.g. Spotify needs a client id/secret.
    EXTRA_CREDENTIAL_KEYS = []

    def __init__(self, credentials, sleep_time=0, verbose=False, error_logger=None):
        """
        Args:
            credentials (dict): This service's credentials, keyed by required_credential_keys().
            sleep_time (int, optional): Seconds to sleep between API calls. Defaults to 0.
            verbose (bool, optional): Whether to print progress messages. Defaults to False.
            error_logger (callable, optional): error_logger(message, printflag=True) used to
                record/print recoverable errors. Defaults to a plain print().
        """
        self.credentials = credentials
        self.sleep_time = sleep_time
        self.verbose = verbose
        self.error_logger = error_logger or (lambda message, printflag=True: print(message))

    @classmethod
    def required_credential_keys(cls):
        """All credential keys needed to use this service, playlist ids included."""
        return ['FARMING_PLAYLIST_ID', 'STEALING_PLAYLIST_ID'] + cls.EXTRA_CREDENTIAL_KEYS

    @abstractmethod
    def search_artist(self, artist_name, max_retries=1):
        """Searches for an artist by name.

        Args:
            artist_name (str): The name to search for.
            max_retries (int, optional): How many times to retry on error. Defaults to 1.

        Returns:
            [ArtistResult]: Candidate matches.
        """

    @abstractmethod
    def get_artist_top_tracks(self, artist_id):
        """Returns an artist's most popular tracks.

        Args:
            artist_id (str): The service's artist id, as returned by search_artist.

        Returns:
            [Track]
        """

    @abstractmethod
    def get_artist_all_tracks(self, artist_id):
        """Returns an artist's full discography.

        Args:
            artist_id (str): The service's artist id, as returned by search_artist.

        Returns:
            [Track]
        """

    @abstractmethod
    def empty_playlist(self, playlist_id):
        """Removes every track from the given playlist.

        Args:
            playlist_id (str): The service's id for the playlist to clear.
        """

    @abstractmethod
    def add_to_playlist(self, track_ids, playlist_id):
        """Adds the given track ids to the given playlist, in order.

        Args:
            track_ids ([str]): Track ids as returned on Track.id.
            playlist_id (str): The service's id for the playlist to add to.
        """
