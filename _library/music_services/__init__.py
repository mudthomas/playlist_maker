"""Registry of playable-music backends (Spotify, Tidal, ...) that Playlist_Generator
can drive through the common MusicService interface (see base.py).

To add a new service:
    1. Write a MusicService subclass in this package (see spotify_service.py for a template).
    2. Register it below, keyed by the name users will write in config.yaml's music_service
       setting.
That's the whole integration point - config validation, credential prompts, and caching
are all driven off this registry, not hardcoded to any particular service.
"""
from .base import MusicService, ArtistResult, Track
from .spotify_service import SpotifyService
from .tidal_service import TidalService

MUSIC_SERVICES = {
    'Spotify': SpotifyService,
    'Tidal': TidalService
}


DEFAULT_MUSIC_SERVICE = 'Tidal'


def get_music_service_class(name):
    """Looks up a registered MusicService subclass by config name.

    Raises:
        ValueError: If name isn't a registered service.
    """
    try:
        return MUSIC_SERVICES[name]
    except KeyError:
        raise ValueError(
            f"Unknown music_service '{name}'. Available: {list(MUSIC_SERVICES.keys())}"
        )
