import json
import pylast as pl
import spotipy as sp
import time
import requests
import urllib3

from _library.advanced_pylast import advanced_pylast_User as pl_User
from _library.file_handler import (get_config, get_blacklist,
                                   get_opponent_list, write_yaml,
                                   get_saved_artists, save_artist_info,
                                   get_failed_artists, get_no_song_artists,
                                   append_string_to_txt)
from _library.errors import GenreError, ArtistNotFoundError, NoSongsFoundError, SearchError

BIG_NUMBER = 1000000  # Maybe replace this with numpy.inf or something...


class Playlist_Generator:
    def __init__(self, settings):
        self.general_settings = settings['general_settings']
        self.farming_settings = settings['farming_settings']
        self.stealing_settings = settings['stealing_settings']
        self.verbose = self.general_settings['verbose']
        self.genres = self.general_settings['genres']
        self.popular = self.general_settings['popular']
        self.Spotify_sleep_time = self.general_settings['sleep_time_Spotify']
        self.Lastfm_sleep_time = self.general_settings['sleep_time_Lastfm']
        self.instance_fail_list, self.instance_no_songs = {}, {}
        self.skipped_genres = {}
        self.saved_artists = get_saved_artists()
        self.failed_artists = get_failed_artists()
        self.no_song_artists = get_no_song_artists()
        self.remove_list = []

        try:
            with open('auth.json', 'r', encoding='UTF-8') as auth:
                credentials = json.load(auth)
        except FileNotFoundError:
            self.add_to_error_log("No auth.json found.", True)
            print("If you generate an auth.json your credentials will be saved in plain text.")
            print("It is possible to run the script without saving your credentials,")
            print("but they will still be in active memory.")
            print("I do not feel confident to say whether or not credentials cannot be extracted from memory.")
            print("I have no interest to construct a workaround for that at this point in time.")
            print("Use at own risk.")
            while True:
                generate_flag = input("Generate auth.json? Otherwise credentials will not be stored. (y/n): ")
                if generate_flag in ['Y', 'y']:
                    print("\nCredentials will be saved.\n")
                    break
                elif generate_flag in ['N', 'n']:
                    print("\nCredentials will NOT be saved.\n")
                    break
            credentials = {'LASTFM_API_KEY': input("last.fm API key: "),
                           'LASTFM_API_SECRET': input("last.fm API secret: "),
                           'LASTFM_USERNAME': input("last.fm API username: "),
                           'LASTFM_PASSWORD': input("last.fm API password: "),
                           'SPOTIFY_CLIENT_ID': input("Spotify client id: "),
                           'SPOTIFY_CLIENT_SECRET': input("Spotify client secret: "),
                           'FARMING_PLAYLIST_ID': input("Spotify Farming playlist id (must be public): "),
                           'STEALING_PLAYLIST_ID': input("Spotify Stealing playlist id (must be public): ")}
            if generate_flag in ['Y', 'y']:
                with open('auth.json', 'w', encoding='UTF-8') as auth:
                    json.dump(credentials, auth)
        self.my_Lastfm_username = credentials['LASTFM_USERNAME']
        self.farming_playlist = credentials['FARMING_PLAYLIST_ID']
        self.stealing_playlist = credentials['STEALING_PLAYLIST_ID']
        self.pl_net = pl.LastFMNetwork(api_key=credentials['LASTFM_API_KEY'],
                                       api_secret=credentials['LASTFM_API_SECRET'],
                                       username=self.my_Lastfm_username,
                                       password_hash=pl.md5(credentials['LASTFM_PASSWORD']))
        new_way = True
        if new_way:
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
                client_id=credentials['SPOTIFY_CLIENT_ID'],
                client_secret=credentials['SPOTIFY_CLIENT_SECRET'],
                redirect_uri="https://127.0.0.1:8080",
                scope="playlist-modify-public"
            ), requests_session=session)
        else:
            self.spot = sp.Spotify(auth_manager=sp.oauth2.SpotifyOAuth(
                client_id=credentials['SPOTIFY_CLIENT_ID'],
                client_secret=credentials['SPOTIFY_CLIENT_SECRET'],
                redirect_uri="https://127.0.0.1:8080",
                scope="playlist-modify-public")
            )
        self.blacklist_artists = get_blacklist()
        self.opponent_list = get_opponent_list()

    # LastFM Stuff
    def get_user_scrobbles(self, Lastfm_username, max_scrobbles=BIG_NUMBER, min_scrobbles=1,
                           min_artists=BIG_NUMBER, starting_page=1):
        """Fetches the 1000 top artist for the logged in user and filters out those with scrobbles over the target.
        If the result is less than min_artists, the process is repeated for the next 1000 top artists.

        Args:
            scrobble_target (int): Number of scrobbles that should be reached.
            min_artists (int, optional): The minimum number of artist fetched. Defaults to 20.

        Returns:
            {artist: scrobbles}: A dictionary with artist as keys and number of plays needed to reach target as values.
        """
        def find_first_entry_under_limit(group, limit):
            index = len(group) // 2
            divider = 4
            while True:
                if limit > int(group[index].weight):
                    if limit > int(group[index - 1].weight):
                        index -= len(group) // divider
                    else:
                        break
                else:
                    index += len(group) // divider
                divider *= 2
            return index

        def find_last_entry_over_limit(group, limit):
            index = len(group) // 2
            divider = 4
            while True:
                if int(group[index].weight) >= limit:
                    if int(group[index + 1].weight) >= limit:
                        index += len(group) // divider
                    else:
                        break
                else:
                    index -= len(group) // divider
                divider *= 2
            return index

        Lastfm_user = pl_User(Lastfm_username, self.pl_net)
        page_no = starting_page
        ret = {}
        while len(ret.keys()) < min_artists:
            try:
                top_artists = Lastfm_user.get_top_artists(limit=512, page=page_no)
                time.sleep(self.Lastfm_sleep_time)
            except pl.WSError as e:
                if e.details == "Connection to the API failed with HTTP code 500":
                    time.sleep(10)
                else:
                    self.add_to_error_log("Here follows an error from pyLast. I want to be able to handle it:", True)
                    self.add_to_error_log(e, True)
                    time.sleep(10)
            else:
                if len(top_artists):  # Failsafe, just in case all artists have been fetched.
                    if int(top_artists[-1].weight) >= max_scrobbles:
                        page_no += 1
                    else:
                        if max_scrobbles > int(top_artists[0].weight):
                            bottom_index = 0
                        else:
                            bottom_index = find_first_entry_under_limit(top_artists, max_scrobbles)
                        if int(top_artists[-1].weight) >= min_scrobbles:
                            ret.update({a.item.get_name(): int(a.weight) for a in top_artists[bottom_index:]})
                            page_no += 1
                        else:
                            top_index = find_last_entry_over_limit(top_artists, min_scrobbles)
                            ret.update({a.item.get_name(): int(a.weight) for a in top_artists[bottom_index:top_index]})
                            break
                else:
                    break
        return ret

    def get_own_full_dict(self):
        """Fetches all top artist for the logged in user.

        Returns:
            {artist: scrobbles}: A dictionary with artist as keys and scrobbles as values.
        """
        return self.get_user_scrobbles(Lastfm_username=self.my_Lastfm_username)

    def get_own_scrobbles(self, scrobble_target, min_artists=100, starting_page=1):
        """Fetches the 1000 top artist for the logged in user and filters out those with scrobbles over the target.
        If the result is less than min_artists, the process is repeated for the next 1000 top artists.

        Args:
            scrobble_target (int): Number of scrobbles that should be reached.
            min_artists (int, optional): The minimum number of artist fetched. Defaults to 20.
            starting_page (int, optional): The first relevant result page from lastfm. Defaults to 1.

        Returns:
            {artist: scrobbles}: A dictionary with artist as keys and number of plays needed to reach target as values.
        """
        return self.get_user_scrobbles(Lastfm_username=self.my_Lastfm_username,
                                       max_scrobbles=scrobble_target,
                                       min_artists=min_artists,
                                       starting_page=starting_page)

    def get_opponent_scrobbles(self, opponent_Lastfm_username, scrobble_target=30):
        """Fetches the top artists for the specified user that are over or equal to the target.

        Returns:
            {artist: scrobbles}: A dictionary with artist as keys and scrobbles as values.
        """
        return self.get_user_scrobbles(Lastfm_username=opponent_Lastfm_username,
                                       min_scrobbles=scrobble_target,
                                       starting_page=1)
    # End LastFM stuff

    # Spotify Things, Playlists
    def empty_playlist(self, playlist_id):
        """Empties a Spotify playlist of its entries.
        Because of limitations, only a hundred tracks are removed at a time.

        Args:
            playlist_id (str): The id of the playlist to be cleared.
        """
        tracks = self.spot.playlist_items(playlist_id)["items"]
        time.sleep(self.Spotify_sleep_time)
        counter = len(tracks)
        while len(tracks):
            self.spot.playlist_remove_all_occurrences_of_items(playlist_id, [track["track"]["uri"] for track in tracks])
            time.sleep(self.Spotify_sleep_time)
            tracks = self.spot.playlist_items(playlist_id)["items"]
            time.sleep(self.Spotify_sleep_time)
            counter += len(tracks)
        if self.verbose:
            print(f"Removed {counter} tracks from playlist")
        return True

    def add_to_playlist(self, track_ids, playlist_id):
        """Adds tracks to a Spotify playlist.
        Because of limitations, only a hundred tracks are added at a time.

        Args:
            track_ids ([str]): A list of Spotify track ids
            playlist_id (str): A Spotify playlist id
        """
        number_of_tracks = len(track_ids)
        tracks_added = 0
        while tracks_added < number_of_tracks:
            self.spot.user_playlist_add_tracks(user=self.spot.me()['id'],
                                               playlist_id=playlist_id,
                                               tracks=track_ids[tracks_added:tracks_added + 100])
            time.sleep(self.Spotify_sleep_time)
            tracks_added += 100
        if self.verbose:
            print(f"Added {number_of_tracks} tracks to playlist")
        return True
    # End Spotify Things, Playlists

    # Spotify Things
    def get_all_artist_tracks(self, artist_uri):
        album_uris = [a['uri'] for a in self.spot.artist_albums(artist_uri)['items']]
        time.sleep(self.Spotify_sleep_time)
        tracks = []
        for uri in album_uris:
            tracks.extend(self.spot.album_tracks(uri)['items'])
            time.sleep(self.Spotify_sleep_time)
        return tracks

    def get_artist_popular_tracks(self, artist_uri):
        tracks = self.spot.artist_top_tracks(artist_uri)["tracks"]
        time.sleep(self.Spotify_sleep_time)
        return tracks

    def search_artist(self, artist_name, max_retries=1):
        for i in range(max_retries):
            try:
                search_results = self.spot.search(q=artist_name, limit=50, type='artist')
                time.sleep(self.Spotify_sleep_time)
                return search_results["artists"]["items"]
            except KeyboardInterrupt:
                raise KeyboardInterrupt
            except Exception as e:
                self.add_to_error_log("Spotify artist search error I want to be able to handle:", True)
                self.add_to_error_log(e, True)
        raise SearchError(artist_name)

    def farm_crowns(self):
        """Populates the 'Farming playlist' with enough plays to reach target for each artist.
        The number of songs per artists are also limited to their Spotify top tracks.

        Args:
            scrobble_target (int, optional): The target number of scrobbles per artist. Defaults to 30.
            number_of_tracks (int, optional): Number of songs to be added to playlist. Defaults to 500.
        """
        scrobble_target = self.farming_settings['crown_goal']
        if self.verbose:
            print("\n## Generating list for farming own crowns ##")
        top_artists = self.get_own_scrobbles(scrobble_target, self.farming_settings['starting_page'])
        skip_artists = [a for a in self.blacklist_artists]
        skip_artists += [a for a in self.failed_artists.keys()]
        skip_artists += [a for a in self.no_song_artists.keys()]
        top_artists = [[key, scrobble_target - value] for key, value in top_artists.items() if key not in skip_artists]
        track_ids = self.get_track_ids(top_artists, self.farming_settings['playlist_length'])
        self.empty_playlist(self.farming_playlist)
        self.add_to_playlist(track_ids, self.farming_playlist)
        self.farming_settings['last_run'] = int(time.strftime('%j'))
        self.do_exit_stuff()
        return True

    def steal_crowns(self):
        """Populates the 'Stealing playlist' with enough plays to overtake opponents.
        The number of songs per artists are also limited to their Spotify top tracks.

        Args:
            scrobble_target (int, optional): Lower scrobble limit of opponent entries to target. Defaults to 30.
            number_of_tracks (int, optional): Number of songs to be added to playlist. Defaults to 500.
        """
        if self.verbose:
            print("\n## Generating list for stealing others crowns ##")
        scrobble_target = self.stealing_settings['crown_goal']
        number_of_tracks = self.stealing_settings['playlist_length']
        reuse = self.should_opp_scrobbles_be_reused()
        if reuse:
            if self.verbose:
                print("## Reusing previous opponent scrobbles ##")
            try:
                with open('opponent_scrobbles.json', 'r', encoding='UTF-8') as opp:
                    top_artists = json.load(opp)
            except FileNotFoundError:
                self.add_to_error_log("No previous opponent scrobbles found, getting new instead.", True)
                reuse = False
            if not len(top_artists):
                self.add_to_error_log("Old list empty, getting new instead.", True)
                reuse = False
        if not reuse:
            if self.verbose:
                print("## Downloading opponent scrobbles ##")
                print(f"\tOpponent 1 of {len(self.opponent_list)}")
            top_artists = self.get_opponent_scrobbles(self.opponent_list[0], scrobble_target)
            for i in range(1, len(self.opponent_list)):
                opponent = self.opponent_list[i]
                if self.verbose:
                    print(f"\tOpponent {i+1} of {len(self.opponent_list)}")
                opponent_dict = self.get_opponent_scrobbles(opponent, scrobble_target)
                for artist, scrobbles in opponent_dict.items():
                    top_artists.update({artist: max(scrobbles, top_artists.get(artist, 0))})
            if self.verbose:
                print("All opponents fetched.")
            skip_artists = [a for a in self.blacklist_artists]
            skip_artists += [a for a in self.failed_artists.keys()]
            skip_artists += [a for a in self.no_song_artists.keys()]
            for artist in skip_artists:
                try:
                    top_artists.pop(artist)
                except KeyError:
                    continue
            with open('opponent_scrobbles.json', 'w', encoding='UTF-8') as opp:
                json.dump(top_artists, opp)

        my_top_artists = self.get_own_full_dict()

        lim_multiplier = 1
        track_ids = []
        while True:
            top_artists_list = []
            for artist, scrobbles in top_artists.items():
                if scrobbles >= scrobble_target:
                    my_scrobble = my_top_artists.get(artist, 0)
                    if self.stealing_settings['overtake'] and not my_scrobble:
                        continue
                    scrobbles -= my_scrobble
                    if 0 <= scrobbles:
                        top_artists_list.append([artist, scrobbles + 1])
                    else:
                        self.remove_list.append(artist)

            top_artists_list.sort(key=lambda x: x[1])
            temp_track_ids = self.get_track_ids(top_artists_list, number_of_tracks, len(track_ids))
            if len(temp_track_ids):
                track_ids.extend(temp_track_ids)
                if len(track_ids) >= number_of_tracks:
                    break
            else:
                break
            lim_multiplier += 1

        self.empty_playlist(self.stealing_playlist)
        self.add_to_playlist(track_ids, self.stealing_playlist)
        if len(self.remove_list):
            for artist in self.remove_list:
                try:
                    top_artists.pop(artist)
                except KeyError:
                    continue
            with open('opponent_scrobbles.json', 'w', encoding='UTF-8') as opp:
                json.dump(top_artists, opp)
        if not reuse:
            self.stealing_settings['last_opponent_save'] = int(time.strftime('%j'))
            self.stealing_settings['saved_opponent_goal'] = self.stealing_settings['crown_goal']
        self.stealing_settings['last_run'] = int(time.strftime('%j'))
        self.do_exit_stuff()
        return True

    def clean_string(self, input_string):
        string_to_clean = input_string.lower()
        # if len(string_to_clean) > 4:
        #     if string_to_clean[0:4] == 'the ':
        #         string_to_clean = string_to_clean[4:]
        # while True:
        #     for i in range(len(string_to_clean)):
        #         if string_to_clean[i] == '&':
        #             string_to_clean = string_to_clean[:i] + "and" + string_to_clean[i + 1:]
        #             break
        #     else:
        #         break
        # string_to_clean = ''.join(e for e in string_to_clean if e.isalnum())
        return string_to_clean

    def check_genres(self, artist_genres):
        wanted_genres = self.genres
        for genre in wanted_genres:
            if genre[0] == '+':
                if genre[1:] in artist_genres:
                    return True
            else:
                for genre2 in artist_genres:
                    if genre in genre2:
                        return True
        return False

    def filter_tracks(self, artist_name, tracks):
        artist_name = self.clean_string(artist_name)
        return [track for track in tracks if self.clean_string(track['artists'][0]['name']) == artist_name]

    def get_artist_track_ids(self, artist):
        try:
            saved_artist = self.saved_artists[artist[0]]
            if not len(saved_artist['genres']):
                saved_artist['genres'] = ['+ NO GENRE +']
                self.saved_artists.update({artist[0]: saved_artist})
            if len(self.genres) and not self.check_genres(saved_artist['genres']):
                self.saved_artists.update({artist[0]: saved_artist})
                raise GenreError(saved_artist['genres'])
            elif self.popular:
                if not len(saved_artist['popular']):
                    try:
                        search_name = saved_artist['search_name']
                    except KeyError:
                        search_name = artist[0]
                    tracks = self.filter_tracks(search_name, self.get_artist_popular_tracks(saved_artist["uri"]))
                    saved_artist['popular'] = [track['uri'] for track in tracks]
                    self.saved_artists.update({artist[0]: saved_artist})
                return saved_artist['popular'][:artist[1]]
            else:
                if not len(saved_artist['full']):
                    try:
                        search_name = saved_artist['search_name']
                    except KeyError:
                        search_name = artist[0]
                    tracks = self.filter_tracks(search_name, self.get_all_artist_tracks(saved_artist["uri"]))
                    tracks = {track['name']: track for track in tracks}
                    tracks = [[track['uri'], track['duration_ms']] for track in tracks.values()]
                    tracks.sort(key=lambda x: x[1])
                    saved_artist['full'] = [track[0] for track in tracks]
                    self.saved_artists.update({artist[0]: saved_artist})
                return saved_artist['full'][:artist[1]]
        except KeyError:
            search_name_methods = [lambda x: x,
                                   lambda x: x.replace(' and ', ' & ').replace(' och ', ' & '),
                                   lambda x: x.lower(),
                                   lambda x: x.upper(),
                                   lambda x: ''.join(c for c in x if c.isalnum())]
            for search_name_method in search_name_methods:
                try:
                    search_name = search_name_method(artist[0])
                    search_results = self.search_artist(search_name)
                    for i in range(len(search_results)):
                        if self.clean_string(search_results[i]['name']) == self.clean_string(search_name):
                            artist_dict = {'full': [],
                                           'popular': [],
                                           'uri': search_results[i]["uri"],
                                           'genres': search_results[i]['genres'],
                                           'date': int(time.strftime('%j')),
                                           'search_name': search_name}
                            if not len(artist_dict['genres']):
                                artist_dict.update({'genres': ['+ NO GENRE +']})
                            if len(self.genres) and not self.check_genres(artist_dict['genres']):
                                self.saved_artists.update({artist[0]: artist_dict})
                                raise GenreError(search_results[i]['genres'])
                            if self.popular:
                                tracks = self.filter_tracks(search_name, self.get_artist_popular_tracks(artist_dict['uri']))
                                track_ids = [track['uri'] for track in tracks]
                                artist_dict['popular'] = track_ids
                            else:
                                tracks = self.filter_tracks(search_name, self.get_all_artist_tracks(artist_dict['uri']))
                                tracks = {track['name']: track for track in tracks}
                                tracks = [[track['uri'], track['duration_ms']] for track in tracks.values()]
                                tracks.sort(key=lambda x: x[1])
                                track_ids = [track[0] for track in tracks]
                                artist_dict['full'] = track_ids
                            self.saved_artists.update({artist[0]: artist_dict})
                            return track_ids[:artist[1]]
                except (IndexError, TypeError):
                    # Should this be search-error?
                    # Is this even reached?
                    print("### I am here ###")
                    raise ArtistNotFoundError(artist)
            else:
                raise ArtistNotFoundError(artist)

    def get_track_ids(self, top_artists, max_entries=500, no_of_old_results=0):
        """Generates a list of Spotify track ids from input artist and needed number of plays.

        Args:
            top_artists ([ [str, int] ]): An (preferrably) ordered list of pairs of artist names and number of plays.
            max_entries (int, optional): Number of tracks to add to playlist. Defaults to 500.

        Returns:
            [str]: A list of Spotify track ids. No longer than max_entries.
        """
        track_ids = [[], [], [], [], [], [], [], [], [], []]
        tracks_added = no_of_old_results
        return_track_ids = []
        for artist in top_artists:
            try:
                temp_tracks = self.get_artist_track_ids(artist)
                # if temp_tracks is None:
                #     if artist[0][:4].lower() == "the ":                                 # Remove 'the '
                #         temp_tracks = self.get_artist_track_ids([artist[0][4:], artist[1]])
                #     elif artist[0][:4].lower() != "the ":                                 # Add 'the '
                #         temp_tracks = self.get_artist_track_ids(["the " + artist[0], artist[1]])
                # if temp_tracks is None:
                #     temp_tracks = self.get_artist_track_ids([artist[0].lower(), artist[1]])
                # if temp_tracks is None:
                #     temp_tracks = self.get_artist_track_ids([artist[0].upper(), artist[1]])
                if temp_tracks is None:
                    print("### I am here ###")
                    raise ArtistNotFoundError(artist)
                elif len(temp_tracks):
                    if self.verbose:
                        art_print_string = artist[0] + ":"
                        if len(artist[0]) < 32:
                            art_print_string = " " * (8 - (len(artist[0]) + 1) % 8) + art_print_string
                        while len(art_print_string) < 32:
                            art_print_string = " " * 8 + art_print_string
                        print(art_print_string + f" {len(temp_tracks)} of {artist[1]}")
                    if len(temp_tracks) <= 10:
                        track_ids[len(temp_tracks) - 1].extend(temp_tracks)
                    else:
                        return_track_ids.extend(temp_tracks)
                    tracks_added += len(temp_tracks)
                    if tracks_added >= max_entries:
                        break
                else:
                    raise NoSongsFoundError(artist)
            except GenreError as e:
                self.add_skipped_genres(e.genres)
                continue
            except SearchError as e:
                print(f"Some error occurred when searching for {e.artist}")
                break
            except ArtistNotFoundError:
                if self.verbose:
                    print(f'Add {artist[0]} to failed artists')
                self.remove_list.append(artist[0])
                self.instance_fail_list.update({artist[0]: max(artist[1], self.instance_fail_list.get(artist[1], 0))})
                continue
            except NoSongsFoundError:
                if self.verbose:
                    print(f"Found no songs for {artist[0]}.")
                self.remove_list.append(artist[0])
                self.instance_no_songs.update({artist[0]: max(artist[1], self.instance_no_songs.get(artist[1], 0))})
                continue
            except KeyboardInterrupt:
                self.do_exit_stuff()
                raise KeyboardInterrupt
        ret = []
        for mini_list in track_ids:
            ret.extend(mini_list)
        return ret + return_track_ids

    def should_opp_scrobbles_be_reused(self):
        if self.stealing_settings['last_opponent_save'] == 0:
            return False
        elif self.stealing_settings['saved_opponent_goal'] > self.stealing_settings['crown_goal']:
            return False
        else:
            current_day = int(time.strftime('%j'))
            if self.stealing_settings['last_opponent_save'] > current_day:
                current_day += 366
            if current_day >= self.stealing_settings['last_opponent_save'] + self.stealing_settings['reuse']:
                return False
        return True

    def do_exit_stuff(self):
        self.update_bad_artists()
        self.save_failed_artists()
        self.save_local_artist_info()
        self.make_logs()
        self.save_settings()
        return True

    # List stuff
    def update_bad_artists(self):
        self.failed_artists.update(self.instance_fail_list)
        self.no_song_artists.update(self.instance_no_songs)
        return True

    def add_skipped_genres(self, genres):
        if len(genres):
            self.skipped_genres.update({genre: self.skipped_genres.get(genre, 0) + 1 for genre in genres})
        else:
            self.skipped_genres.update({'+ NO GENRE +': self.skipped_genres.get('+ NO GENRE +', 0) + 1})
        return True

    def save_local_artist_info(self):
        return save_artist_info(self.saved_artists)

    # File stuff
    def save_failed_artists(self):
        return write_yaml('failed_artists.yaml', self.failed_artists)

    def save_no_song_artists(self):
        return write_yaml('no_song_artists.yaml', self.no_song_artists)

    def make_logs(self):
        dumpfile = {'failed_artist': self.instance_fail_list,
                    'no_songs': self.instance_no_songs,
                    'skipped genres': self.skipped_genres}
        return write_yaml('log.yaml', dumpfile)

    def save_settings(self):
        dumpfile = {'general_settings': self.general_settings,
                    'farming_settings': self.farming_settings,
                    'stealing_settings': self.stealing_settings}
        return write_yaml('config.yaml', dumpfile)

    def add_to_error_log(self, error_string, printflag=False):
        append_string_to_txt('error_log.txt',
                             f"{time.strftime('%Y %m %d  %H:%M:%S', time.localtime())}\n{error_string}")
        if printflag:
            print(error_string)
        return True


if __name__ == "__main__":
    pg = Playlist_Generator(get_config())
    if pg.farming_settings['active']:
        try:
            pg.farm_crowns()
            print("Finished generating playlist for farming own crowns successfully.")
        except KeyboardInterrupt:
            print("User aborted generation of list for farming own crowns.")
    if pg.stealing_settings['active']:
        try:
            pg.steal_crowns()
            print("Finished generating playlist for stealing others crowns successfully.")
        except KeyboardInterrupt:
            print("User aborted generation of list for stealing others crowns.")
    if pg.verbose:
        print("Finished run.")
        print("You can close the window or wait for 30 seconds for it to close automatically.")
        # close = input("Finished. Press enter to exit.")  # Multifunction could do this AND a timer.
        try:
            time.sleep(30)
        except KeyboardInterrupt:
            pass
