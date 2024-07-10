import json
import pylast
import spotipy
import time
import calendar
import datetime as dt
from tqdm import tqdm


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
    def __init__(self):
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
            print("No auth.json found.")
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
                    line = f.readline()
                    if not line:
                        break
                    self.opponent_list.append(line.strip())
        except FileNotFoundError:
            print("No opponent_list.txt found. Generating new, empty file.")
            with open('opponent_list.txt', 'x') as f:
                pass

    def clean_playlist(self, playlist_id):
        """Clears a playlist of entries.
        Because of limitations, only a hundred tracks are removed at a time.

        Args:
            playlist_id (str): The id of the playlist to be cleared.
        """
        counter = 0
        while True:
            old_items = self.spot.playlist_items(playlist_id)
            counter += len(old_items["items"])
            if len(old_items["items"]):
                uri_list = []
                for item in old_items["items"]:
                    uri_list.append(item["track"]["uri"])
                self.spot.playlist_remove_all_occurrences_of_items(playlist_id, uri_list)
            else:
                break
        print(f"Removed {counter} tracks from playlist")

    def add_to_playlist(self, track_ids, playlist_id):
        """Adds tracks to a spotify playlist.
        Because of limitations, only a hundred tracks are added at a time.

        Args:
            track_ids ([str]): A list of spotify track ids
            playlist_id (str): A spotify playlist id
        """
        while len(track_ids):  # Maximum of 100 tracks can be added at a time.
            self.spot.user_playlist_add_tracks(user=self.spot.me()['id'],
                                               playlist_id=playlist_id,
                                               tracks=track_ids[:100])
            track_ids = track_ids[100:]

    def get_own_dict(self):
        """Fetches the 1000 top artist for the logged in user.
        1000 is currently a limitation of pylast.

        Returns:
            {artist: scrobbles}: A dictionary with artist as keys and scrobbles as values.
        """
        # lastfm_user = self.pylast_net.get_user(self.my_lastfm_username)
        lastfm_user = advanced_User(self.my_lastfm_username, self.pylast_net)
        top_artists = lastfm_user.get_top_artists(limit=1000, page=1)
        ret = {}
        for a in top_artists:
            ret.update({a.item.get_name(): int(a.weight)})
        return ret

    def get_plays_needed(self, scrobble_target):
        """Fetches the 1000 top artist for the logged in user, filters out those that are over the target.
        1000 is currently a limitation of pylast.

        Args:
            scrobble_target (int): Number of scrobbles that should be reached.

        Returns:
            {artist: scrobbles}: A dictionary with artist as keys and number of plays needed to reach target as values.
        """
        # lastfm_user = self.pylast_net.get_user(self.my_lastfm_username)
        lastfm_user = advanced_User(self.my_lastfm_username, self.pylast_net)
        ret = {}
        page_no = 1
        while not len(ret.keys()):
            top_artists = lastfm_user.get_top_artists(limit=1000, page=page_no)
            for a in top_artists:
                if int(a.weight) < scrobble_target:
                    ret.update({a.item.get_name(): scrobble_target - int(a.weight)})
            page_no += 1
        return ret

    def get_opponent_dict(self, opponent_lastfm_username, scrobble_target=30):
        """Fetches the 1000 top artist for the specified user, filters out those that are under the target.
        1000 is currently a limitation of pylast.

        Returns:
            {artist: scrobbles}: A dictionary with artist as keys and scrobbles as values.
        """
        # lastfm_user = self.pylast_net.get_user(opponent_lastfm_username)
        lastfm_user = advanced_User(opponent_lastfm_username, self.pylast_net)
        top_artists = lastfm_user.get_top_artists(limit=1000)
        ret = {}
        for a in top_artists:
            if int(a.weight) >= scrobble_target:
                ret.update({a.item.get_name(): int(a.weight)})
            else:
                break
        return ret

    def generate_list_to_increase_own_plays(self, scrobble_target=30, number_of_tracks=500):
        """Populates the 'Farming playlist' with enough plays to reach target for each artist.
        The number of songs per artists are also limited to their spotify top tracks.

        Args:
            scrobble_target (int, optional): The target number of scrobbles per artist. Defaults to 30.
            number_of_tracks (int, optional): Number of songs to be added to playlist. Defaults to 500.
        """
        self.generate_list(self.farming_playlist, scrobble_target, number_of_tracks)

    def generate_list(self, playlist_id, scrobble_target=30, number_of_tracks=500):
        """Generates a playlist with enough plays to reach target for each artist.
        The number of songs per artists are also limited to their spotify top tracks.

        Args:
            playlist_id (str): The playlist to populate.
            scrobble_target (int, optional): The target number of scrobbles per artist. Defaults to 30.
            number_of_tracks (int, optional): Number of songs to be added to playlist. Defaults to 500.
        """
        self.clean_playlist(playlist_id)
        top_artists = self.get_plays_needed(scrobble_target)

        for artist in self.blacklist_artists:
            if artist in top_artists:
                top_artists.pop(artist)

        top_artists = [[key, value] for key, value in top_artists.items()]
        track_ids = self.get_track_ids(top_artists, number_of_tracks)
        self.add_to_playlist(track_ids, playlist_id)

    def steal_crowns(self, scrobble_target=30, number_of_tracks=500):
        """Populates the 'Stealing playlist' with enough plays to overtake opponents.
        The number of songs per artists are also limited to their spotify top tracks.

        Args:
            scrobble_target (int, optional): Lower scrobble limit of opponent entries to target. Defaults to 30.
            number_of_tracks (int, optional): Number of songs to be added to playlist. Defaults to 500.
        """

        self.clean_playlist(self.stealing_playlist)

        top_artists = {}
        for opponent in self.opponent_list:
            opponent_dict = self.get_opponent_dict(opponent, scrobble_target)
            for artist in opponent_dict.keys():
                top_artists.update({artist: max(opponent_dict.get(artist), top_artists.get(artist, 0))})

        for artist in self.blacklist_artists:
            if artist in top_artists:
                top_artists.pop(artist)

        my_top_artists = self.get_own_dict()

        for a in top_artists.keys():
            top_artists.update({a: top_artists.get(a) - my_top_artists.get(a, 0)})

        top_artists = [[key, value + 1] for key, value in top_artists.items() if value >= 0]
        top_artists.sort(key=lambda x: x[1])
        track_ids = self.get_track_ids(top_artists, number_of_tracks)
        self.add_to_playlist(track_ids, self.stealing_playlist)

    def get_track_ids(self, top_artists, max_entries=500):
        """Generates a list of spotify track ids from input artist and needed number of plays.

        Args:
            top_artists ([ [str, int] ]): An (preferrably) ordered list of pairs of artist names and number of plays.
            max_entries (int, optional): Number of tracks to add to playlist. Defaults to 500.

        Returns:
            [str]: A list of spotify track ids. No longer than max_entries.
        """
        track_ids = []
        for artist in top_artists:
            print(artist)
            search_results = self.spot.search(q=f"\"{artist[0]}\"", limit=1, type='artist')
            tracks = self.spot.artist_top_tracks(search_results["artists"]["items"][0]["uri"])
            for i in range(min(artist[1], len(tracks["tracks"]))):
                track_ids.append(tracks["tracks"][i]["uri"])
            if len(track_ids) >= max_entries:
                break
        return track_ids[:max_entries]

    def set_settings(self, year, month, day):
        with open('personal_plays_settings.json', 'w', encoding='UTF-8') as stats:
                        settings = {'year': year,
                                    'month': month,
                                    'day': day}
                        json.dump(settings, stats)

    def get_settings(self):
        with open('personal_plays_settings.json', 'r', encoding='UTF-8') as stats:
            settings = json.load(stats)
            start_year = settings['year']
            start_month = settings['month']
            start_day = settings['day']
            return start_year, start_month, start_day

    def get_own_dict2(self):
        starting_year = 2022
        lastfm_user = self.pylast_net.get_user(self.my_lastfm_username)
        try:
            with open('personal_plays.json', 'r', encoding='UTF-8') as stats:
                top_artists = json.load(stats)
                updated_list = self.get_own_dict()
                for artist in updated_list.keys():
                    top_artists.update({artist: updated_list.get(artist)})
        except FileNotFoundError:
            with open('personal_plays.json', 'w', encoding='UTF-8') as stats:
                top_artists = self.get_own_dict()
                json.dump(top_artists, stats)

        try:
            year, month, day = self.get_settings()
        except FileNotFoundError:
            self.set_settings(starting_year, 1, 1)
            year, month, day = self.get_settings()

        while year <= 2024:
            while month <= 12:
                print(f"Start {year}, {month}, {day}")
                break_flag = 0
                while day <= 31:
                    try:
                        start = dt.datetime(year, month, day, 1, 1)
                    except ValueError:
                        break
                    try:
                        end = dt.datetime(year, month, day + 1, 1, 1)
                    except ValueError:
                        try:
                            end = dt.datetime(year, month + 1, 1, 1, 1)
                        except ValueError:
                            end = dt.datetime(year + 1, 1, 1, 1, 1)
                        break_flag = 1
                    utc_start = calendar.timegm(start.utctimetuple())
                    utc_end = calendar.timegm(end.utctimetuple())
                    tracks = lastfm_user.get_recent_tracks(time_from=utc_start, time_to=utc_end, limit=None)  # Pro level would be adaptive by the time this function call takes.
                    time.sleep(1)
                    # tracks = lastfm_user.get_recent_tracks(limit=None)
                    for track in tqdm(tracks):
                        artist = str(track.track.artist)
                        if artist not in top_artists.keys():
                            lastfm_artist = pylast.Artist(artist, self.pylast_net, username=self.my_lastfm_username)
                            plays = lastfm_artist.get_userplaycount()
                            top_artists.update({artist: plays})
                            time.sleep(1)
                    with open('personal_plays.json', 'w', encoding='UTF-8') as stats:
                        json.dump(top_artists, stats)
                    self.set_settings(year, month, day)
                    if break_flag:
                        break
                    day += 1
                month += 1
                day = 1
            year += 1
            month = 1


if __name__ == "__main__":
    pg = Playlist_Generator()
    print("## Generating list for farming own crowns ##")
    pg.generate_list_to_increase_own_plays(30, 100)
    # print("\n## Generating list for stealing others crowns ##")
    # pg.steal_crowns(30, 100)
    # pg.get_own_dict2()
