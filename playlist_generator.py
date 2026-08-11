import bisect
import json
import pylast as pl
import time
import yaml
import pyperclip

from _library.advanced_pylast import advanced_pylast_User as pl_User
from _library.file_handler import (get_config, get_blacklist,
                                   get_opponent_list,
                                   get_saved_artists, save_artist_info,
                                   get_failed_artists, get_no_song_artists,
                                   save_failed_artists as save_failed_artists_to_file,
                                   save_no_song_artists as save_no_song_artists_to_file,
                                   get_lastfm_credentials, save_lastfm_credentials,
                                   get_service_credentials, save_service_credentials,
                                   migrate_legacy_auth_json, write_yaml,
                                   append_string_to_txt,
                                   get_own_scrobbles_cache, save_own_scrobbles_cache)
from _library.music_services import get_music_service_class
from _library.errors import GenreError, ArtistNotFoundError, NoSongsFoundError, SearchError

BIG_NUMBER = 1000000  # Maybe replace this with numpy.inf or something...

# Friendlier prompt text for credential keys asked for interactively. Keys not
# listed here (e.g. a future service's own extra keys) just use the raw key name.
_CREDENTIAL_PROMPT_HINTS = {
    'FARMING_PLAYLIST_ID': 'Farming playlist id (must be public)',
    'STEALING_PLAYLIST_ID': 'Stealing playlist id (must be public)',
    'CLIENT_ID': 'client id',
    'CLIENT_SECRET': 'client secret',
}


class Playlist_Generator:
    def __init__(self, settings):
        self.general_settings = settings['general_settings']
        self.farming_settings = settings['farming_settings']
        self.stealing_settings = settings['stealing_settings']
        self.verbose = self.general_settings['verbose']
        self.genres = self.general_settings['genres']
        self.genre_source = self.general_settings['genre_source']
        self.popular = self.general_settings['popular']
        self.music_service_name = self.general_settings['music_service']
        self.service_sleep_time = self.general_settings['sleep_time_music_service']
        self.Lastfm_sleep_time = self.general_settings['sleep_time_Lastfm']
        self.own_scrobbles_cache_hours = self.general_settings['own_scrobbles_cache_hours']
        # In-memory cache for get_own_full_dict/get_own_scrobbles - see
        # _load_fresh_own_scrobbles_cache. Populated on first use by whichever of the
        # two is called first, regardless of whether farm_crowns or steal_crowns runs
        # first, so a single process never crawls its own last.fm library twice.
        self._own_scrobbles_full = None
        self.instance_fail_list, self.instance_no_songs = {}, {}
        self.skipped_genres = {}
        self.saved_artists = get_saved_artists(self.music_service_name)
        self.failed_artists = get_failed_artists(self.music_service_name)
        self.no_song_artists = get_no_song_artists(self.music_service_name)
        self.remove_list = []

        # Splits a pre-multi-service auth.json into auth_lastfm.json/auth_<service>.json
        # the first time this runs after upgrading. No-op if auth.json doesn't exist.
        migrate_legacy_auth_json()

        service_class = get_music_service_class(self.music_service_name)
        required_keys = service_class.required_credential_keys()

        lastfm_credentials = get_lastfm_credentials()
        service_credentials = get_service_credentials(self.music_service_name)

        if lastfm_credentials is None or service_credentials is None:
            missing = []
            if lastfm_credentials is None:
                missing.append("last.fm")
            if service_credentials is None:
                missing.append(self.music_service_name)
            self.add_to_error_log(f"No credentials found for: {', '.join(missing)}.", True)
            print("If you generate credential files your details will be saved in plain text.")
            print("It is possible to run the script without saving your credentials,")
            print("but they will still be in active memory.")
            print("I do not feel confident to say whether or not credentials cannot be extracted from memory.")
            print("I have no interest to construct a workaround for that at this point in time.")
            print("Use at own risk.")
            while True:
                generate_flag = input("Generate credential file(s)? Otherwise credentials will not be stored. (y/n): ")
                if generate_flag in ['Y', 'y']:
                    print("\nCredentials will be saved.\n")
                    break
                elif generate_flag in ['N', 'n']:
                    print("\nCredentials will NOT be saved.\n")
                    break
            if lastfm_credentials is None:
                lastfm_credentials = {'LASTFM_API_KEY': input("last.fm API key: "),
                                      'LASTFM_API_SECRET': input("last.fm API secret: "),
                                      'LASTFM_USERNAME': input("last.fm API username: "),
                                      'LASTFM_PASSWORD': input("last.fm API password: ")}
                if generate_flag in ['Y', 'y']:
                    save_lastfm_credentials(lastfm_credentials)
            if service_credentials is None:
                service_credentials = {
                    key: input(f"{self.music_service_name} {_CREDENTIAL_PROMPT_HINTS.get(key, key)}: ")
                    for key in required_keys
                }
                if generate_flag in ['Y', 'y']:
                    save_service_credentials(self.music_service_name, service_credentials)

        self.my_Lastfm_username = lastfm_credentials['LASTFM_USERNAME']
        self.pl_net = pl.LastFMNetwork(api_key=lastfm_credentials['LASTFM_API_KEY'],
                                       api_secret=lastfm_credentials['LASTFM_API_SECRET'],
                                       username=self.my_Lastfm_username,
                                       password_hash=pl.md5(lastfm_credentials['LASTFM_PASSWORD']))

        self.farming_playlist = service_credentials['FARMING_PLAYLIST_ID']
        self.stealing_playlist = service_credentials['STEALING_PLAYLIST_ID']
        self.service = service_class(service_credentials,
                                     sleep_time=self.service_sleep_time,
                                     verbose=self.verbose,
                                     error_logger=self.add_to_error_log)

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
            """First index in `group` (sorted by descending .weight) whose weight is
            under `limit` - the boundary between the 'weight >= limit' and
            'weight < limit' runs. O(log n) via bisect and never reads out of range,
            unlike the hand-rolled step search this replaces (which could stall
            forever once its fixed jump schedule rounded down to a zero-length step
            before finding the boundary - reproducibly common for
            find_last_entry_over_limit below, rarer but still possible here).
            """
            return bisect.bisect_right(group, -limit, key=lambda a: -int(a.weight))

        def find_last_entry_over_limit(group, limit):
            """Last index in `group` (sorted by descending .weight) whose weight is
            still >= limit - one before the same boundary found by
            find_first_entry_under_limit.
            """
            return bisect.bisect_right(group, -limit, key=lambda a: -int(a.weight)) - 1

        Lastfm_user = pl_User(Lastfm_username, self.pl_net)
        page_no = starting_page
        ret = {}
        # while len(ret.keys()) < min_artists:
        while True:
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
                            # find_last_entry_over_limit returns the last INCLUSIVE index
                            # over the limit, but the slice below needs an exclusive end -
                            # +1 here keeps that artist in the result instead of dropping it.
                            top_index = find_last_entry_over_limit(top_artists, min_scrobbles) + 1
                            ret.update({a.item.get_name(): int(a.weight) for a in top_artists[bottom_index:top_index]})
                            break
                else:
                    break
        return ret

    def _load_fresh_own_scrobbles_cache(self):
        """Returns the full {artist: scrobbles} snapshot for this account if one is
        already in memory (populated earlier this run) or on disk and still younger
        than general_settings.own_scrobbles_cache_hours, else None.

        Deliberately read-only: it never fetches from last.fm itself, so it can be
        used opportunistically by get_own_scrobbles without forcing a full crawl
        when nothing fresh is available yet.
        """
        if self._own_scrobbles_full is not None:
            return self._own_scrobbles_full
        cached = get_own_scrobbles_cache()
        if cached is None:
            return None
        age_hours = (time.time() - cached['timestamp']) / 3600
        if age_hours >= self.own_scrobbles_cache_hours:
            return None
        self._own_scrobbles_full = cached['data']
        return self._own_scrobbles_full

    def get_own_full_dict(self):
        """Fetches all top artist for the logged in user.

        Reuses a cached snapshot (own_scrobbles_cache.json, from this or an earlier
        run) if it's younger than general_settings.own_scrobbles_cache_hours, instead
        of re-crawling all of last.fm - get_own_scrobbles reads the same cache, so
        whichever of the two runs first in a given process does the one full fetch
        and the other reuses it for free.

        Returns:
            {artist: scrobbles}: A dictionary with artist as keys and scrobbles as values.
        """
        cached = self._load_fresh_own_scrobbles_cache()
        if cached is not None:
            return cached
        data = self.get_user_scrobbles(Lastfm_username=self.my_Lastfm_username)
        self._own_scrobbles_full = data
        save_own_scrobbles_cache(int(time.time()), data)
        return data

    def get_own_scrobbles(self, scrobble_target, min_artists=1000, starting_page=1):
        """Fetches the 1000 top artist for the logged in user and filters out those with scrobbles over the target.
        If the result is less than min_artists, the process is repeated for the next 1000 top artists.

        If a fresh full-library snapshot is already available (see get_own_full_dict),
        it's filtered locally instead of hitting last.fm again; otherwise this falls
        back to its own bounded fetch exactly as before.

        Args:
            scrobble_target (int): Number of scrobbles that should be reached.
            min_artists (int, optional): The minimum number of artist fetched. Defaults to 20.
            starting_page (int, optional): The first relevant result page from lastfm. Defaults to 1.

        Returns:
            {artist: scrobbles}: A dictionary with artist as keys and number of plays needed to reach target as values.
        """
        cached = self._load_fresh_own_scrobbles_cache()
        if cached is not None:
            return {artist: plays for artist, plays in cached.items() if plays < scrobble_target}
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

    def get_lastfm_artist_genres(self, artist_name, limit=10):
        """Fetches an artist's top user-submitted tags from last.fm, used as a genre substitute.

        Args:
            artist_name (str): The artist to look up.
            limit (int, optional): Max number of tags to fetch. Defaults to 10.

        Returns:
            [str]: A list of tag names. Empty if last.fm has none, or the artist was not found.
        """
        try:
            top_tags = pl.Artist(artist_name, self.pl_net).get_top_tags(limit=limit)
            time.sleep(self.Lastfm_sleep_time)
        except pl.WSError as e:
            self.add_to_error_log(f"last.fm tag lookup failed for {artist_name}:", True)
            self.add_to_error_log(e, True)
            return []
        return [tag.item.get_name() for tag in top_tags]
    # End LastFM stuff

    # Playlist stuff
    def _get_skip_artists(self):
        """Returns the set of artist names that should never be added to a playlist:
        the user's blacklist, plus artists already known (from a previous run) to
        fail search or have no matching songs on the active music service.

        A set rather than a list so `artist not in skip_artists` (farm_crowns) is
        O(1) instead of an O(n) scan per artist.
        """
        return set(self.blacklist_artists) | self.failed_artists.keys() | self.no_song_artists.keys()

    def farm_crowns(self):
        """Populates the 'Farming playlist' with enough plays to reach target for each artist.
        The number of songs per artists are also limited to their top tracks on the active music service.

        Args:
            scrobble_target (int, optional): The target number of scrobbles per artist. Defaults to 30.
            number_of_tracks (int, optional): Number of songs to be added to playlist. Defaults to 500.
        """
        scrobble_target = self.farming_settings['crown_goal']
        if self.verbose:
            print("\n## Generating list for farming own crowns ##")
        top_artists = self.get_own_scrobbles(scrobble_target, self.farming_settings['starting_page'])
        skip_artists = self._get_skip_artists()
        top_artists = [[key, scrobble_target - value] for key, value in top_artists.items() if key not in skip_artists]
        track_ids = self.get_track_ids(top_artists, self.farming_settings['playlist_length'])
        self.service.empty_playlist(self.farming_playlist)
        self.service.add_to_playlist(track_ids, self.farming_playlist)
        self.farming_settings['last_run'] = int(time.strftime('%j'))
        self.do_exit_stuff()
        return True

    def steal_crowns(self):
        """Populates the 'Stealing playlist' with enough plays to overtake opponents.
        The number of songs per artists are also limited to their top tracks on the active music service.

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
            skip_artists = self._get_skip_artists()
            for artist in skip_artists:
                top_artists.pop(artist, None)
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

        self.service.empty_playlist(self.stealing_playlist)
        self.service.add_to_playlist(track_ids, self.stealing_playlist)
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
    # End Playlist stuff

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

    def get_relevant_artist_genres(self, artist_name, saved_artist):
        """Returns the cached genre/tag list for whichever source general_settings.genre_source
        selects ('Spotify' or 'LastFM'), fetching and caching it first if needed.

        Spotify genres arrive for free with the artist search result, so only the 'genres_spotify'
        placeholder is filled in here if it's genuinely empty. LastFM tags require a dedicated API
        call, made only the first time an artist is looked up under that source.

        Note this always reads/writes 'genres_spotify' regardless of which music_service is active -
        that field is only meaningful when music_service is also 'Spotify', since genre tags come
        along with whichever service's artist search is actually being used.

        Args:
            artist_name (str): The artist's key in self.saved_artists.
            saved_artist (dict): That artist's saved_artists entry.

        Returns:
            [str]: The artist's genres/tags for the configured source. Never empty -
                   '+ NO GENRE +' is used as a placeholder so a lookup isn't repeated.
        """
        genre_key = 'genres_spotify' if self.genre_source == 'Spotify' else 'genres_lastfm'
        if not len(saved_artist[genre_key]):
            if self.genre_source == 'LastFM':
                saved_artist[genre_key] = self.get_lastfm_artist_genres(artist_name)
            if not len(saved_artist[genre_key]):
                saved_artist[genre_key] = ['+ NO GENRE +']
            self.saved_artists.update({artist_name: saved_artist})
        return saved_artist[genre_key]

    def filter_tracks(self, artist_name, tracks):
        artist_name = self.clean_string(artist_name)
        return [track for track in tracks if self.clean_string(track.artist_name) == artist_name]

    def get_artist_track_ids(self, artist):
        try:
            saved_artist = self.saved_artists[artist[0]]
            if self.genre_source is not None and len(self.genres):
                artist_genres = self.get_relevant_artist_genres(artist[0], saved_artist)
                if not self.check_genres(artist_genres):
                    raise GenreError(artist_genres)
            if self.popular:
                if not len(saved_artist['popular']):
                    try:
                        search_name = saved_artist['search_name']
                    except KeyError:
                        search_name = artist[0]
                    tracks = self.filter_tracks(search_name, self.service.get_artist_top_tracks(saved_artist["uri"]))
                    saved_artist['popular'] = [track.id for track in tracks]
                    self.saved_artists.update({artist[0]: saved_artist})
                return saved_artist['popular'][:artist[1]]
            else:
                if not len(saved_artist['full']):
                    try:
                        search_name = saved_artist['search_name']
                    except KeyError:
                        search_name = artist[0]
                    tracks = self.filter_tracks(search_name, self.service.get_artist_all_tracks(saved_artist["uri"]))
                    tracks = {track.name: track for track in tracks}
                    sorted_tracks = sorted(tracks.values(), key=lambda t: t.duration_ms)
                    saved_artist['full'] = [track.id for track in sorted_tracks]
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
                    search_results = self.service.search_artist(search_name)
                    for result in search_results:
                        if self.clean_string(result.name) == self.clean_string(search_name):
                            artist_dict = {'full': [],
                                           'popular': [],
                                           'uri': result.id,
                                           'genres_spotify': result.genres,
                                           'genres_lastfm': [],
                                           'date': int(time.strftime('%j')),
                                           'search_name': search_name}
                            self.saved_artists.update({artist[0]: artist_dict})
                            if self.genre_source is not None and len(self.genres):
                                artist_genres = self.get_relevant_artist_genres(artist[0], artist_dict)
                                if not self.check_genres(artist_genres):
                                    raise GenreError(artist_genres)
                            if self.popular:
                                tracks = self.filter_tracks(search_name, self.service.get_artist_top_tracks(artist_dict['uri']))
                                track_ids = [track.id for track in tracks]
                                artist_dict['popular'] = track_ids
                            else:
                                tracks = self.filter_tracks(search_name, self.service.get_artist_all_tracks(artist_dict['uri']))
                                tracks = {track.name: track for track in tracks}
                                sorted_tracks = sorted(tracks.values(), key=lambda t: t.duration_ms)
                                track_ids = [track.id for track in sorted_tracks]
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
        """Generates a list of track ids from input artist and needed number of plays.

        Args:
            top_artists ([ [str, int] ]): An (preferrably) ordered list of pairs of artist names and number of plays.
            max_entries (int, optional): Number of tracks to add to playlist. Defaults to 500.

        Returns:
            [str]: A list of track ids for the active music service. No longer than max_entries.
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
                        art_print_string += f" {len(temp_tracks)} of {artist[1]}"
                        if len(temp_tracks) < 10:
                            art_print_string += " "
                        if artist[1] < 10:
                            art_print_string += " "
                        art_print_string += f"\t({tracks_added + len(temp_tracks)}/{max_entries})"
                        print(art_print_string)
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
        return save_artist_info(self.saved_artists, self.music_service_name)

    # File stuff
    def save_failed_artists(self):
        return save_failed_artists_to_file(self.failed_artists, self.music_service_name)

    def save_no_song_artists(self):
        return save_no_song_artists_to_file(self.no_song_artists, self.music_service_name)

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
