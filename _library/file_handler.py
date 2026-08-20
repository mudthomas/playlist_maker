import yaml
import json

from _library.music_services import MUSIC_SERVICES, DEFAULT_MUSIC_SERVICE

# Valid values for general_settings.genre_source.
# None disables genre checking entirely, avoiding any related API calls.
GENRE_SOURCES = [None, 'Spotify', 'LastFM']


# YAML Getters
def read_yaml(filename):
    try:
        with open(filename, 'r') as file:
            ret = yaml.safe_load(file)
    except FileNotFoundError:
        ret = {}
    return ret or {}


def _read_service_nested_yaml(filename):
    """Reads a YAML file whose contents are namespaced by music service, e.g.
    {"Spotify": {...}, "Tidal": {...}}. A pre-multi-service file (a flat dict with
    no known service name among its top-level keys) is treated as legacy Spotify
    data and wrapped accordingly, so nothing is lost or misread on upgrade.
    """
    data = read_yaml(filename)
    if data and not any(key in MUSIC_SERVICES for key in data.keys()):
        return {DEFAULT_MUSIC_SERVICE: data}
    return data


def get_failed_artists(music_service=DEFAULT_MUSIC_SERVICE):
    return _read_service_nested_yaml('failed_artists.yaml').get(music_service, {})


def get_no_song_artists(music_service=DEFAULT_MUSIC_SERVICE):
    return _read_service_nested_yaml('no_song_artists.yaml').get(music_service, {})


def get_config():
    try:
        with open('config.yaml', 'r') as file:
            settings = yaml.safe_load(file)
            # Backfill settings introduced after this config.yaml was first generated,
            # so older config files on disk do not break on a missing key.
            general = settings['general_settings']
            general.setdefault('genre_source', None)
            general.setdefault('music_service', DEFAULT_MUSIC_SERVICE)
            general.setdefault('own_scrobbles_cache_hours', 8)
            if 'sleep_time_Spotify' in general and 'sleep_time_music_service' not in general:
                general['sleep_time_music_service'] = general.pop('sleep_time_Spotify')
            general.setdefault('sleep_time_music_service', 2)
            # genres used to live under general_settings and applied to both farm and
            # steal. Migrate it into each section that doesn't already have its own.
            old_genres = general.pop('genres', None)
            settings['farming_settings'].setdefault('genres', old_genres if old_genres is not None else [])
            settings['stealing_settings'].setdefault('genres', old_genres if old_genres is not None else [])
            verify_config(settings)
    except FileNotFoundError:
        settings = generate_settings()
        write_yaml('config.yaml', settings)
    return settings


def verify_config(settings):
    for setting_set in settings.keys():
        for setting in settings[setting_set].keys():
            if setting == 'genres':
                if isinstance(settings[setting_set]['genres'], list):
                    for genre in settings[setting_set]['genres']:
                        if not isinstance(genre, str):
                            raise ValueError(
                                f"Error in config.yaml, {setting_set}, {setting}. Value should be an a list of strings."
                            )
                else:
                    raise ValueError(
                        f"Error in config.yaml, {setting_set}, {setting}. Value should be an a list of strings."
                    )
            elif setting == 'genre_source':
                if settings[setting_set]['genre_source'] not in GENRE_SOURCES:
                    raise ValueError(
                        f"Error in config.yaml, {setting_set}, {setting}. Value should be one of {GENRE_SOURCES}."
                    )
            elif setting == 'music_service':
                if settings[setting_set]['music_service'] not in MUSIC_SERVICES:
                    raise ValueError(
                        f"Error in config.yaml, {setting_set}, {setting}. "
                        f"Value should be one of {list(MUSIC_SERVICES.keys())}."
                    )
            else:
                if not isinstance(settings[setting_set][setting], int):
                    raise ValueError(f"Error in config.yaml, {setting_set}, {setting}. Value should be an integer.")


# YAML Setters
def write_yaml(filename, dumpfile):
    with open(filename, 'w') as yaml_file:
        yaml.dump(dumpfile, yaml_file)
    return True


def save_failed_artists(failed_artists, music_service=DEFAULT_MUSIC_SERVICE):
    all_failed = _read_service_nested_yaml('failed_artists.yaml')
    all_failed[music_service] = failed_artists
    return write_yaml('failed_artists.yaml', all_failed)


def save_no_song_artists(no_song_artists, music_service=DEFAULT_MUSIC_SERVICE):
    all_no_song = _read_service_nested_yaml('no_song_artists.yaml')
    all_no_song[music_service] = no_song_artists
    return write_yaml('no_song_artists.yaml', all_no_song)


def generate_settings():
    settings = {'general_settings': {'verbose': 1,
                                     'sleep_time_music_service': 2,
                                     'sleep_time_Lastfm': 2,
                                     'genre_source': None,
                                     'music_service': DEFAULT_MUSIC_SERVICE,
                                     'own_scrobbles_cache_hours': 8,
                                     'popular': 1},
                'farming_settings': {'active': 1,
                                     'crown_goal': 30,
                                     'genres': [],
                                     'last_run': 0,
                                     'playlist_length': 100,
                                     'starting_page': 1},
                'stealing_settings': {'active': 1,
                                      'crown_goal': 30,
                                      'genres': [],
                                      'last_opponent_save': 0,
                                      'last_run': 0,
                                      'overtake': 0,
                                      'playlist_length': 100,
                                      'reuse': 7,
                                      'saved_opponent_goal': 30}}
    return settings


# JSON
def _read_json_or_none(filename):
    try:
        with open(filename, 'r', encoding='UTF-8') as file:
            return json.load(file)
    except FileNotFoundError:
        return None


def _read_service_nested_json(filename):
    """Same idea as _read_service_nested_yaml, but for the JSON artist cache."""
    data = _read_json_or_none(filename)
    if data is None:
        try:
            with open(filename.replace('.json', '.yaml'), 'r') as file:
                data = yaml.safe_load(file)
        except FileNotFoundError:
            data = None
    data = data or {}
    if data and not any(key in MUSIC_SERVICES for key in data.keys()):
        return {DEFAULT_MUSIC_SERVICE: data}
    return data


def get_saved_artists(music_service=DEFAULT_MUSIC_SERVICE):
    all_saved = _read_service_nested_json('saved_artists.json')
    return _migrate_saved_artists(all_saved.get(music_service, {}))


def _migrate_saved_artists(saved_art):
    """Migrates entries saved before genres were split by source.

    Older cache entries store a single 'genres' list (Spotify-sourced). This moves
    that data to 'genres_spotify' and adds an empty 'genres_lastfm', so both sources
    can be cached independently going forward.
    """
    for artist_info in saved_art.values():
        if 'genres' in artist_info:
            artist_info.setdefault('genres_spotify', artist_info.pop('genres'))
        artist_info.setdefault('genres_spotify', [])
        artist_info.setdefault('genres_lastfm', [])
    return saved_art


def save_artist_info(artist_info, music_service=DEFAULT_MUSIC_SERVICE):
    all_saved = _read_service_nested_json('saved_artists.json')
    all_saved[music_service] = artist_info
    return write_json('saved_artists.json', all_saved)


def write_json(filename, dumpfile):
    with open(filename, 'w') as json_file:
        json.dump(dumpfile, json_file)
    return True


# Own-scrobbles cache
# A snapshot of the logged-in last.fm user's full top-artists dict, shared by
# Playlist_Generator.get_own_full_dict (steal_crowns) and get_own_scrobbles
# (farm_crowns) so a full last.fm crawl isn't repeated needlessly - see
# general_settings.own_scrobbles_cache_hours for the freshness window. Not
# nested by music_service: this is pure last.fm data, independent of which
# music_service is active.
def get_own_scrobbles_cache():
    """Returns the cached {'timestamp': <unix seconds>, 'data': {artist: scrobbles}}
    snapshot, or None if there isn't one yet.
    """
    return _read_json_or_none('own_scrobbles_cache.json')


def save_own_scrobbles_cache(timestamp, data):
    return write_json('own_scrobbles_cache.json', {'timestamp': timestamp, 'data': data})


# Credentials
# last.fm credentials are shared regardless of which music_service is active.
# Each music service gets its own auth_<service>.json, holding whatever keys its
# MusicService subclass declares via required_credential_keys() (see
# _library/music_services/base.py) - so adding a new service never touches
# another service's stored credentials.
def get_lastfm_credentials():
    return _read_json_or_none('auth_lastfm.json')


def save_lastfm_credentials(credentials):
    return write_json('auth_lastfm.json', credentials)


def _service_credentials_filename(music_service):
    return f"auth_{music_service.lower()}.json"


def get_service_credentials(music_service):
    return _read_json_or_none(_service_credentials_filename(music_service))


def save_service_credentials(music_service, credentials):
    return write_json(_service_credentials_filename(music_service), credentials)


def migrate_legacy_auth_json():
    """One-time migration: splits a pre-multi-service auth.json (a single flat file
    holding last.fm and Spotify credentials together) into auth_lastfm.json and
    auth_spotify.json, so existing users don't need to re-enter anything after
    upgrading. The old auth.json is left on disk afterward, just unused.
    """
    legacy = _read_json_or_none('auth.json')
    if legacy is None:
        return
    if get_lastfm_credentials() is None:
        lastfm_keys = ['LASTFM_API_KEY', 'LASTFM_API_SECRET', 'LASTFM_USERNAME', 'LASTFM_PASSWORD']
        if all(key in legacy for key in lastfm_keys):
            save_lastfm_credentials({key: legacy[key] for key in lastfm_keys})
    if get_service_credentials('Spotify') is None:
        spotify_key_map = {
            'CLIENT_ID': 'SPOTIFY_CLIENT_ID',
            'CLIENT_SECRET': 'SPOTIFY_CLIENT_SECRET',
            'FARMING_PLAYLIST_ID': 'FARMING_PLAYLIST_ID',
            'STEALING_PLAYLIST_ID': 'STEALING_PLAYLIST_ID',
        }
        if all(old_key in legacy for old_key in spotify_key_map.values()):
            save_service_credentials(
                'Spotify', {new_key: legacy[old_key] for new_key, old_key in spotify_key_map.items()}
            )


# TXT Getters
def get_blacklist():
    return _get_list_from_txt('blacklist_artists.txt')


def get_opponent_list():
    return _get_list_from_txt('opponent_list.txt')


def _get_list_from_txt(filename):
    ret_list = []
    try:
        with open(filename, 'r') as f:
            while True:
                line = f.readline()
                if not line:
                    break
                ret_list.append(line.strip())
    except FileNotFoundError:
        # self.add_to_error_log(f"{filename} not found. Generating new, empty file.", True)
        with open(filename, 'x') as f:
            pass
    return ret_list


# TXT Setters
def append_string_to_txt(filename, dump_string):
    with open(filename, 'a') as f:
        print(dump_string, file=f)
    return True
