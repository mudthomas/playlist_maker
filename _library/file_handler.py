import yaml
import json

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
    return ret


def get_failed_artists():
    return read_yaml('failed_artists.yaml')


def get_no_song_artists():
    return read_yaml('no_song_artists.yaml')


def get_config():
    try:
        with open('config.yaml', 'r') as file:
            settings = yaml.safe_load(file)
            # Backfill settings introduced after this config.yaml was first generated,
            # so older config files on disk do not break on the missing key.
            settings['general_settings'].setdefault('genre_source', None)
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
            else:
                if not isinstance(settings[setting_set][setting], int):
                    raise ValueError(f"Error in config.yaml, {setting_set}, {setting}. Value should be an integer.")


# YAML Setters
def write_yaml(filename, dumpfile):
    with open(filename, 'w') as yaml_file:
        yaml.dump(dumpfile, yaml_file)
    return True


def generate_settings():
    settings = {'general_settings': {'verbose': 1,
                                     'sleep_time_Spotify': 0,
                                     'sleep_time_Lastfm': 0,
                                     'genres': [],
                                     'genre_source': None,
                                     'popular': 1},
                'farming_settings': {'active': 1,
                                     'crown_goal': 30,
                                     'last_run': 0,
                                     'playlist_length': 500,
                                     'starting_page': 1},
                'stealing_settings': {'active': 1,
                                      'crown_goal': 30,
                                      'last_opponent_save': 0,
                                      'last_run': 0,
                                      'overtake': 0,
                                      'playlist_length': 500,
                                      'reuse': 7,
                                      'saved_opponent_goal': 30}}
    return settings


# JSON
def get_saved_artists():
    try:
        with open('saved_artists.json', 'r', encoding='UTF-8') as file:
            saved_art = json.load(file)
    except FileNotFoundError:
        try:
            with open('saved_artists.yaml', 'r') as file:
                saved_art = yaml.safe_load(file)
        except FileNotFoundError:
            saved_art = {}
    return _migrate_saved_artists(saved_art)


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


def save_artist_info(artist_info):
    return write_json('saved_artists.json', artist_info)


def write_json(filename, dumpfile):
    with open(filename, 'w') as json_file:
        json.dump(dumpfile, json_file)
    return True


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
