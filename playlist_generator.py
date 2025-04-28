import json
import pylast
import spotipy
import time


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
        time.sleep(2)

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
            time.sleep(2)

    def get_own_dict(self):
        """Fetches all top artist for the logged in user.

        Returns:
            {artist: scrobbles}: A dictionary with artist as keys and scrobbles as values.
        """
        lastfm_user = advanced_User(self.my_lastfm_username, self.pylast_net)
        page_no = 1
        ret = {}
        while True:
            top_artists = lastfm_user.get_top_artists(limit=1000, page=page_no)
            if len(top_artists):
                for a in top_artists:
                    ret.update({a.item.get_name(): int(a.weight)})
            else:
                break
            time.sleep(1)
            page_no += 1
        return ret

    def get_plays_needed(self, scrobble_target, min_artists=100):
        """Fetches the 1000 top artist for the logged in user and filters out those with scrobbles over the target.
        If the result is less than min_artists, the process is repeated for the next 1000 top artists.

        Args:
            scrobble_target (int): Number of scrobbles that should be reached.
            min_artists (int, optional): The minimum number of artist fetched. Defaults to 20.

        Returns:
            {artist: scrobbles}: A dictionary with artist as keys and number of plays needed to reach target as values.
        """
        lastfm_user = advanced_User(self.my_lastfm_username, self.pylast_net)
        ret = {}
        page_no = 1
        while len(ret.keys()) < max(min_artists, len(self.blacklist_artists) + 1):
            top_artists = lastfm_user.get_top_artists(limit=1000, page=page_no)
            if len(top_artists):  # Failsafe, just in case all artists have been fetched.
                for a in top_artists:
                    if int(a.weight) < scrobble_target:
                        ret.update({a.item.get_name(): scrobble_target - int(a.weight)})
            else:
                break
            time.sleep(1)
            page_no += 1
        return ret

    def get_opponent_dict(self, opponent_lastfm_username, scrobble_target=30):
        """Fetches the top artist for the specified user that are over or equal to the target.

        Returns:
            {artist: scrobbles}: A dictionary with artist as keys and scrobbles as values.
        """
        lastfm_user = advanced_User(opponent_lastfm_username, self.pylast_net)
        ret = {}
        page_no = 1
        while True:
            top_artists = lastfm_user.get_top_artists(limit=1000, page=page_no)
            if len(top_artists):  # Failsafe, just in case all artists have been fetched.
                for a in top_artists:
                    if int(a.weight) >= scrobble_target:
                        ret.update({a.item.get_name(): int(a.weight)})
                    else:
                        return ret
            else:
                return ret
            time.sleep(1)
            page_no += 1

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
        top_artists = self.get_plays_needed(scrobble_target)
        top_artists = [[key, value] for key, value in top_artists.items() if key not in self.blacklist_artists]
        track_ids = self.get_track_ids(top_artists, number_of_tracks)
        self.clean_playlist(playlist_id)
        self.add_to_playlist(track_ids, playlist_id)

    def steal_crowns(self, scrobble_target=30, number_of_tracks=500):
        """Populates the 'Stealing playlist' with enough plays to overtake opponents.
        The number of songs per artists are also limited to their spotify top tracks.

        Args:
            scrobble_target (int, optional): Lower scrobble limit of opponent entries to target. Defaults to 30.
            number_of_tracks (int, optional): Number of songs to be added to playlist. Defaults to 500.
        """
        my_top_artists = self.get_own_dict()
        top_artists = self.get_opponent_dict(self.opponent_list[0], scrobble_target)

        for opponent in self.opponent_list[1:]:
            opponent_dict = self.get_opponent_dict(opponent, scrobble_target)
            for artist, scrobbles in opponent_dict.items():
                top_artists.update({artist: max(scrobbles, top_artists.get(artist, 0))})

        top_artists_list = []
        for artist, scrobbles in top_artists.items():
            scrobbles -= my_top_artists.get(artist, 0)
            if 0 <= scrobbles <= scrobble_target * 2:
                if artist not in self.blacklist_artists:
                    top_artists_list.append([artist, scrobbles + 1])
        top_artists_list.sort(key=lambda x: x[1])

        # 0 <= scrobbles - my_scrobbles skips those where you already have the crown
        # scrobbles - my_scrobbles <= scrobble_target * 2 skips those where you 'might as well' listen to a new artist,
        # or increase those you have like 1 scrobble on. Adjust if list empty I guess.
        # Generally, keeping the list as small as possible makes the sorting faster.

        track_ids = self.get_track_ids(top_artists_list, number_of_tracks)
        self.clean_playlist(self.stealing_playlist)
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
            try:
                search_results = self.spot.search(q=f"\"{artist[0]}\"", limit=10, type='artist')
                for i in range(len(search_results["artists"]["items"])):
                    if search_results["artists"]["items"][i]['name'] == artist[0]:
                        # This check lowers the risk of adding the wrong artist
                        tracks = self.spot.artist_top_tracks(search_results["artists"]["items"][0]["uri"])
                        no_tracks = len(tracks["tracks"])
                        track_counter = 0
                        while track_counter < min(artist[1], no_tracks):
                            try:
                                track = tracks["tracks"].pop(0)
                                if track['artists'][0]['name'] == artist[0]:
                                    # This check tries to ensure that artist is main artist of track
                                    track_ids.append(track["uri"])
                                    track_counter += 1
                            except IndexError:
                                # Popped all tracks
                                break
                        print(artist)
                        if len(track_ids) >= max_entries:
                            return track_ids[:max_entries]
                        time.sleep(1)
                        break
            except IndexError:
                # No search results
                print(f"Error for {artist[0]}")
        return track_ids


if __name__ == "__main__":
    # If error prone, consider adding more time.Sleep where applicable. Or increasing existing timers.
    scrobble_target = 30  # This is the default bot setting using .fmbot. If your Discord hub is different, change it.
    pg = Playlist_Generator()
    print("## Generating list for farming own crowns ##")
    pg.generate_list_to_increase_own_plays(scrobble_target, 1000)
    print("\n## Generating list for stealing others crowns ##")
    pg.steal_crowns(30, 1000)
