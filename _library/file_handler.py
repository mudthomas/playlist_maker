import yaml


def get_config():
    try:
        with open('config.yaml', 'r') as file:
            settings = yaml.safe_load(file)
            verify_config(settings)
    except FileNotFoundError:
        settings = generate_config()
    return settings


def get_saved_artists():
    try:
        with open('saved_artists.yaml', 'r') as file:
            return yaml.safe_load(file)
    except FileNotFoundError:
        return {}


def save_artist_info(artist_info):
    try:
        with open('saved_artists.yaml', 'w') as file:
            yaml.dump(artist_info, file)
        return True
    except:
        return False


def verify_config(settings):
    for setting_set in settings.keys():
        for setting in settings[setting_set].keys():
            if setting == 'genres':
                if isinstance(settings[setting_set]['genres'], list):
                    for genre in settings[setting_set]['genres']:
                        if not isinstance(genre, str):
                            raise ValueError(f"Error in config.yaml, {setting_set}, {setting}. Value should be an a list of strings.")
                else:
                    raise ValueError(f"Error in config.yaml, {setting_set}, {setting}. Value should be an a list of strings.")
            else:
                if not isinstance(settings[setting_set][setting], int):
                    raise ValueError(f"Error in config.yaml, {setting_set}, {setting}. Value should be an integer.")


def generate_config():
    settings = {'general_settings': {'verbose': 1,
                                     'sleep_time_spotify': 0,
                                     'sleep_time_lastfm': 0,
                                     'genres': [],
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
    with open('config.yaml', 'w') as yaml_file:
        yaml.dump(settings, yaml_file)
    return settings


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


def write_yaml(filename, dumpfile):
    with open(filename, 'w') as yaml_file:
        yaml.dump(dumpfile, yaml_file)
    return True
