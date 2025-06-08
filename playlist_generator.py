import json
import pylast
import spotipy
import time
import yaml

BIG_NUMBER = 1000000  # Maybe replace this with inf or something...


class advanced_User(pylast.User):
    PERIOD_OVERALL = "overall"

    def get_top_artists(self, period=PERIOD_OVERALL, limit=None, page=1):
        """Returns the top artists played by a user.
        * period: The period of time. Possible values:
          o PERIOD_OVERALL
          o PERIOD_7DAYS
          o PERIOD_1MONTH
          o PERIOD_3MONTHS
          o PERIOD_6MONTHS
          o PERIOD_12MONTHS
        """
        params = self._get_params()
        params["period"] = period
        params["page"] = page
        if limit:
            params["limit"] = limit
        doc = self._request(self.ws_prefix + ".getTopArtists", True, params)
        return pylast._extract_top_artists(doc, self.network)


class Playlist_Generator:
    def __init__(self, settings):
        self.general_settings = settings['general_settings']
        self.farming_settings = settings['farming_settings']
        self.stealing_settings = settings['stealing_settings']
        self.verbose = self.general_settings['verbose']
        self.fail_list, self.no_songs_list = {}, {}

        try:
            with open('auth.json', 'r', encoding='UTF-8') as auth:
                credentials = json.load(auth)
                API_KEY = credentials['LASTFM_API_KEY']
                API_SECRET = credentials['LASTFM_API_SECRET']
                self.my_lastfm_username = credentials['LASTFM_USERNAME']
                PASSWORD = pylast.md5(credentials['LASTFM_PASSWORD'])
                self.pylast_net = pylast.LastFMNetwork(api_key=API_KEY,
                                                       api_secret=API_SECRET,
                                                       username=self.my_lastfm_username,
                                                       password_hash=PASSWORD)
                CLIENT_ID = credentials['SPOTIFY_CLIENT_ID']
                CLIENT_SECRET = credentials['SPOTIFY_CLIENT_SECRET']
                self.spot = spotipy.Spotify(auth_manager=spotipy.oauth2.SpotifyOAuth(client_id=CLIENT_ID,
                                                                                     client_secret=CLIENT_SECRET,
                                                                                     redirect_uri="https://localhost:8080",
                                                                                     scope="playlist-modify-public"))
                self.farming_playlist = credentials['FARMING_PLAYLIST_ID']
                self.stealing_playlist = credentials['STEALING_PLAYLIST_ID']
        except FileNotFoundError:
            print("No auth.json found. If you generate an auth.json your credentials will be saved in plain text. It is possible to run the script without credentials saved, but they will still be stored in memory, I have no interest to construct a workaround for that at this point in time.")
            while True:
                generate_flag = input("Generate auth.json? Otherwise credentials will not be saved. (y/n): ")
                if generate_flag in ['Y', 'y', 'N', 'n']:
                    break
            API_KEY = input("last.fm API key: ")
            API_SECRET = input("last.fm API secret: ")
            self.my_lastfm_username = input("last.fm API username: ")
            PASSWORD = input("last.fm API password: ")
            self.pylast_net = pylast.LastFMNetwork(api_key=API_KEY,
                                                   api_secret=API_SECRET,
                                                   username=self.my_lastfm_username,
                                                   password_hash=pylast.md5(PASSWORD))
            CLIENT_ID = input("Spotify client id: ")
            CLIENT_SECRET = input("Spotify client secret: ")
            self.spot = spotipy.Spotify(auth_manager=spotipy.oauth2.SpotifyOAuth(client_id=CLIENT_ID,
                                                                                 client_secret=CLIENT_SECRET,
                                                                                 redirect_uri="https://localhost:8080",
                                                                                 scope="playlist-modify-public"))
            self.farming_playlist = input("Spotify Farming playlist id (must be public): ")
            self.stealing_playlist = input("Spotify Stealing playlist id (must be public): ")

            if generate_flag in ['Y', 'y']:
                credentials = {'LASTFM_API_KEY': API_KEY,
                               'LASTFM_API_SECRET': API_SECRET,
                               'LASTFM_USERNAME': self.my_lastfm_username,
                               'LASTFM_PASSWORD': PASSWORD,
                               'SPOTIFY_CLIENT_ID': CLIENT_ID,
                               'SPOTIFY_CLIENT_SECRET': CLIENT_SECRET,
                               'FARMING_PLAYLIST_ID': self.farming_playlist,
                               'STEALING_PLAYLIST_ID': self.stealing_playlist}
                with open('auth.json', 'w', encoding='UTF-8') as auth:
                    json.dump(credentials, auth)

        self.blacklist_artists = []
        try:
            with open('blacklist_artists.txt', 'r') as f:
                while True:
                    line = f.readline()
                    if not line:
                        break
                    self.blacklist_artists.append(line.strip())
        except FileNotFoundError:
            print("No blacklist_artists.txt found. Generating new, empty file.")
            with open('blacklist_artists.txt', 'x') as f:
                pass

        self.opponent_list = []
        try:
            with open('opponent_list.txt', 'r') as f:
                while True:
                    line = f.readline().strip()
                    if not line:
                        break
                    if line != self.my_lastfm_username.strip():  # Sanity check if own name is in opponent list
                        self.opponent_list.append(line)
        except FileNotFoundError:
            print("No opponent_list.txt found. Generating new, empty file.")
            with open('opponent_list.txt', 'x') as f:
                pass


    def empty_playlist(self, playlist_id):
        """Empties a spotify playlist of its entries.
        Because of limitations, only a hundred tracks are removed at a time.

        Args:
            playlist_id (str): The id of the playlist to be cleared.
        """
        tracks = self.spot.playlist_items(playlist_id)["items"]
        counter = len(tracks)
        while len(tracks):
            self.spot.playlist_remove_all_occurrences_of_items(playlist_id, [track["track"]["uri"] for track in tracks])
            tracks = self.spot.playlist_items(playlist_id)["items"]
            counter += len(tracks)
        if self.verbose:
            print(f"Removed {counter} tracks from playlist")

    def add_to_playlist(self, track_ids, playlist_id):
        """Adds tracks to a spotify playlist.
        Because of limitations, only a hundred tracks are added at a time.

        Args:
            track_ids ([str]): A list of spotify track ids
            playlist_id (str): A spotify playlist id
        """
        number_of_tracks = len(track_ids)
        tracks_added = 0
        while tracks_added < number_of_tracks:
            self.spot.user_playlist_add_tracks(user=self.spot.me()['id'],
                                               playlist_id=playlist_id,
                                               tracks=track_ids[tracks_added:tracks_added + 100])
            tracks_added += 100
        if self.verbose:
            print(f"Added {number_of_tracks} tracks to playlist")

    def get_user_scrobbles(self, lastfm_username, max_scrobbles=BIG_NUMBER, min_scrobbles=1,
                           min_artists=BIG_NUMBER, starting_page=1):
        """Fetches the 1000 top artist for the logged in user and filters out those with scrobbles over the target.
        If the result is less than min_artists, the process is repeated for the next 1000 top artists.

        Args:
            scrobble_target (int): Number of scrobbles that should be reached.
            min_artists (int, optional): The minimum number of artist fetched. Defaults to 20.

        Returns:
            {artist: scrobbles}: A dictionary with artist as keys and number of plays needed to reach target as values.
        """
        lastfm_user = advanced_User(lastfm_username, self.pylast_net)
        page_no = starting_page
        ret = {}
        while len(ret.keys()) < min_artists:
            top_artists = lastfm_user.get_top_artists(limit=1000, page=page_no)
            if len(top_artists):  # Failsafe, just in case all artists have been fetched.
                for a in top_artists:
                    if max_scrobbles > int(a.weight):
                        if int(a.weight) >= min_scrobbles:
                            ret.update({a.item.get_name(): int(a.weight)})
                        else:
                            break
                if int(top_artists[-1].weight) < min_scrobbles:
                    break
            else:
                break
            time.sleep(1)
            page_no += 1
        return ret

    def get_own_full_dict(self):
        """Fetches all top artist for the logged in user.

        Returns:
            {artist: scrobbles}: A dictionary with artist as keys and scrobbles as values.
        """
        return self.get_user_scrobbles(lastfm_username=self.my_lastfm_username)

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
        return self.get_user_scrobbles(lastfm_username=self.my_lastfm_username,
                                       max_scrobbles=scrobble_target,
                                       min_artists=min_artists,
                                       starting_page=starting_page)

    def get_opponent_scrobbles(self, opponent_lastfm_username, scrobble_target=30):
        """Fetches the top artists for the specified user that are over or equal to the target.

        Returns:
            {artist: scrobbles}: A dictionary with artist as keys and scrobbles as values.
        """
        return self.get_user_scrobbles(lastfm_username=opponent_lastfm_username,
                                       min_scrobbles=scrobble_target,
                                       starting_page=1)

    def farm_crowns(self):
        """Populates the 'Farming playlist' with enough plays to reach target for each artist.
        The number of songs per artists are also limited to their spotify top tracks.

        Args:
            scrobble_target (int, optional): The target number of scrobbles per artist. Defaults to 30.
            number_of_tracks (int, optional): Number of songs to be added to playlist. Defaults to 500.
        """
        scrobble_target = self.farming_settings['crown_goal']
        number_of_tracks = self.farming_settings['playlist_length']
        starting_page = self.farming_settings['starting_page']
        if self.verbose:
            print("\n## Generating list for farming own crowns ##")
        playlist_id = self.farming_playlist
        top_artists = self.get_own_scrobbles(scrobble_target, starting_page)
        top_artists = [[key, scrobble_target - value] for key, value in top_artists.items() if key not in self.blacklist_artists]
        track_ids = self.get_track_ids(top_artists, number_of_tracks)
        self.empty_playlist(playlist_id)
        self.add_to_playlist(track_ids, playlist_id)
        self.farming_settings['last_run'] = int(time.strftime('%j'))
        return True

    def steal_crowns(self):
        """Populates the 'Stealing playlist' with enough plays to overtake opponents.
        The number of songs per artists are also limited to their spotify top tracks.

        Args:
            scrobble_target (int, optional): Lower scrobble limit of opponent entries to target. Defaults to 30.
            number_of_tracks (int, optional): Number of songs to be added to playlist. Defaults to 500.
        """
        if self.verbose:
            print("\n## Generating list for stealing others crowns ##")
        scrobble_target = self.stealing_settings['crown_goal']
        number_of_tracks = self.stealing_settings['playlist_length']
        my_top_artists = self.get_own_full_dict()
        reuse = self.should_opp_scrobbles_be_reused()
        if reuse:
            if self.verbose:
                print("## Reusing previous opponent scrobbles ##")
            try:
                with open('opponent_scrobbles.json', 'r', encoding='UTF-8') as opp:
                    top_artists = json.load(opp)
            except FileNotFoundError:
                print("No previous opponent scrobbles found, getting new instead.")
                reuse = False
            if not len(top_artists):
                print("Old list empty, getting new instead.")
                reuse = False
        if not reuse:
            if self.verbose:
                print("## Downloading opponent scrobbles ##")
            top_artists = self.get_opponent_scrobbles(self.opponent_list[0], scrobble_target)
            for opponent in self.opponent_list[1:]:
                opponent_dict = self.get_opponent_scrobbles(opponent, scrobble_target)
                for artist, scrobbles in opponent_dict.items():
                    top_artists.update({artist: max(scrobbles, top_artists.get(artist, 0))})
            with open('opponent_scrobbles.json', 'w', encoding='UTF-8') as opp:
                json.dump(top_artists, opp)

        top_artists_list = []
        remove_list = []
        for artist, scrobbles in top_artists.items():
            if scrobbles >= scrobble_target:
                scrobbles -= my_top_artists.get(artist, 0)
                if 0 <= scrobbles <= scrobble_target * 2:
                    if artist not in self.blacklist_artists:
                        top_artists_list.append([artist, scrobbles + 1])
                else:
                    remove_list.append(artist)

        # 0 <= scrobbles - my_scrobbles <= scrobble_target
        # skips those where you already have the crown and skips those where you 'might as well' listen to a new artist.
        #
        # An alternative would be
        # 0 <= scrobbles - my_scrobbles <= scrobble_target * 2
        # If we consider that stealing is better than "starting a new artist".

        top_artists_list.sort(key=lambda x: x[1])
        track_ids = self.get_track_ids(top_artists_list, number_of_tracks)
        self.empty_playlist(self.stealing_playlist)
        self.add_to_playlist(track_ids, self.stealing_playlist)
        if len(remove_list):
            for artist in remove_list:
                top_artists.pop(artist)
            with open('opponent_scrobbles.json', 'w', encoding='UTF-8') as opp:
                json.dump(top_artists, opp)
        if not reuse:
            self.stealing_settings['last_opponent_save'] = int(time.strftime('%j'))
            self.stealing_settings['saved_opponent_goal'] = self.stealing_settings['crown_goal']
        self.stealing_settings['last_run'] = int(time.strftime('%j'))
        return True

    def clean_string(self, input_string):
        string_to_clean = input_string.lower()
        if len(string_to_clean) > 4:
            if string_to_clean[0:4] == 'the ':
                string_to_clean = string_to_clean[4:]
        while True:
            for i in range(len(string_to_clean)):
                if string_to_clean[i] == '&':
                    string_to_clean = string_to_clean[:i] + "and" + string_to_clean[i + 1:]
                    break
            else:
                break
        return ''.join(e for e in string_to_clean if e.isalnum())

    def get_artist_top_tracks(self, artist):
        track_ids = []
        try:
            search_results = self.search_artist(artist[0])
            for i in range(len(search_results["artists"]["items"])):
                if self.clean_string(search_results["artists"]["items"][i]['name']) == self.clean_string(artist[0]):
                    tracks = self.spot.artist_top_tracks(search_results["artists"]["items"][i]["uri"])
                    no_tracks = len(tracks["tracks"])
                    while len(track_ids) < min(artist[1], no_tracks):
                        try:
                            track = tracks["tracks"].pop(0)
                            if self.clean_string(track['artists'][0]['name']) == self.clean_string(artist[0]):
                                track_ids.append(track["uri"])
                        except IndexError:
                            # Popped all tracks
                            return track_ids
                    return track_ids
            else:
                return None
        except (IndexError, TypeError):
            return None

    def search_artist(self, artist_name, max_retries=1):
        search_results = None
        for i in range(max_retries):
            try:
                return self.spot.search(q=artist_name, limit=50, type='artist')
            except KeyboardInterrupt:
                raise KeyboardInterrupt
            except:
                pass
        return search_results

    def get_track_ids(self, top_artists, max_entries=500):
        """Generates a list of spotify track ids from input artist and needed number of plays.

        Args:
            top_artists ([ [str, int] ]): An (preferrably) ordered list of pairs of artist names and number of plays.
            max_entries (int, optional): Number of tracks to add to playlist. Defaults to 500.

        Returns:
            [str]: A list of spotify track ids. No longer than max_entries.
        """
        track_ids = [[], [], [], [], [], [], [], [], [], []]
        tracks_added = 0
        for artist in top_artists:
            temp_tracks = self.get_artist_top_tracks(artist)
            if temp_tracks is None and '&' in artist[0]:                          # Replace '&'
                temp_tracks = self.get_artist_top_tracks([artist[0].replace('&', 'and'), artist[1]])
                if temp_tracks is None and artist[0][:4].lower() == "the ":       # Replace '&', remove 'the '
                    temp_tracks = self.get_artist_top_tracks([artist[0][4:], artist[1]])
                elif temp_tracks is None and artist[0][:4].lower() != "the ":     # Replace '&', add 'the'
                    temp_tracks = self.get_artist_top_tracks(["the " + artist[0], artist[1]])
            if temp_tracks is None and 'and ' in artist[0]:                     # Replace 'and '
                temp_tracks = self.get_artist_top_tracks([artist[0].replace('and ', '& '), artist[1]])
                if temp_tracks is None and artist[0][:4].lower() == "the ":       # Replace 'and ', remove 'the '
                    temp_tracks = self.get_artist_top_tracks([artist[0][4:], artist[1]])
                elif temp_tracks is None and artist[0][:4].lower() != "the ":     # Replace 'and ', add 'the'
                    temp_tracks = self.get_artist_top_tracks(["the " + artist[0], artist[1]])
            if temp_tracks is None:
                if artist[0][:4].lower() == "the ":                                 # Remove 'the '
                    temp_tracks = self.get_artist_top_tracks([artist[0][4:], artist[1]])
                elif artist[0][:4].lower() != "the ":                                 # Add 'the '
                    temp_tracks = self.get_artist_top_tracks(["the " + artist[0], artist[1]])
            if temp_tracks is None:
                temp_tracks = self.get_artist_top_tracks([artist[0].lower(), artist[1]])
            if temp_tracks is None:
                temp_tracks = self.get_artist_top_tracks([artist[0].upper(), artist[1]])
            if self.verbose and temp_tracks is not None:
                art_print_string = artist[0] + ":"
                if len(artist[0]) < 32:
                    art_print_string = " " * (8 - (len(artist[0]) + 1) % 8) + art_print_string
                while len(art_print_string) < 32:
                    art_print_string = " " * 8 + art_print_string
                print(art_print_string + f" {len(temp_tracks)} of {artist[1]}")
            if temp_tracks is None:
                if self.verbose:
                    print(f"Failed for {artist[0]}.")
                self.fail_list.update({artist[0]: max(artist[1], self.fail_list.get(artist[1], 0))})
            elif len(temp_tracks) == 0:
                if self.verbose:
                    print(f"Found no songs for {artist[0]}.")
                self.no_songs_list.update({artist[0]: max(artist[1], self.no_songs_list.get(artist[1], 0))})
            else:
                if tracks_added + len(temp_tracks) > max_entries:
                    temp_tracks = temp_tracks[:max_entries - tracks_added]
                    track_ids[len(temp_tracks) - 1].extend(temp_tracks)
                    tracks_added += len(temp_tracks)
                    break
                else:
                    track_ids[len(temp_tracks) - 1].extend(temp_tracks)
                    tracks_added += len(temp_tracks)
        return_track_ids = []
        for mini_list in track_ids:
            return_track_ids.extend(mini_list)
        return return_track_ids

    def make_logs(self):
        with open('log.yaml', 'w') as yaml_file:
            dumpfile = {}
            dumpfile = {'failed_artist': self.fail_list, 'no_songs': self.no_songs_list}
            yaml.dump(dumpfile, yaml_file)

    def save_settings(self):
        with open('config.yaml', 'w') as yaml_file:
            dumpfile = {'general_settings': self.general_settings,
                        'farming_settings': self.farming_settings,
                        'stealing_settings': self.stealing_settings}
            yaml.dump(dumpfile, yaml_file)

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


if __name__ == "__main__":
    with open('config.yaml', 'r') as file:
        settings = yaml.safe_load(file)
    pg = Playlist_Generator(settings)
    if settings['farming_settings']['active']:
        pg.farm_crowns()
    if settings['stealing_settings']['active']:
        pg.steal_crowns()
    pg.make_logs()
    pg.save_settings()
