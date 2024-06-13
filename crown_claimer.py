import json
import pylast
import spotipy


def get_pylast_network_object():
    """Creates and returns network object from credentials stored in auth.json

    Returns:
        LastFMNetwork: a network object
    """
    with open('auth.json', 'r', encoding='UTF-8') as auth:
        credentials = json.load(auth)
        API_KEY = credentials['LASTFM_API_KEY']
        API_SECRET = credentials['LASTFM_API_SECRET']
        USERNAME = credentials['LASTFM_USERNAME']
        PASSWORD = pylast.md5(credentials['LASTFM_PASSWORD'])
    return pylast.LastFMNetwork(api_key=API_KEY, api_secret=API_SECRET, username=USERNAME, password_hash=PASSWORD)


def get_spotify_object():
    """Creates and returns a Spotify object from credentials stored in auth.json

    Returns:
        Spotify: a Spotify object
    """
    with open('auth.json', 'r', encoding='UTF-8') as auth:
        credentials = json.load(auth)
        CLIENT_ID = credentials['SPOTIFY_CLIENT_ID']
        CLIENT_SECRET = credentials['SPOTIFY_CLIENT_SECRET']

    scope = "playlist-modify-public"
    return spotipy.Spotify(auth_manager=spotipy.oauth2.SpotifyOAuth(client_id=CLIENT_ID,
                                                                    client_secret=CLIENT_SECRET,
                                                                    redirect_uri="https://localhost:8080",
                                                                    scope=scope))


def get_playlist_id():
    """Fetches and returns a Spotify playlist id stored in auth.json

    Returns:
        str: A Spotify playlist id.
    """
    with open('auth.json', 'r', encoding='UTF-8') as auth:
        credentials = json.load(auth)
        PLAYLIST_ID = credentials['SPOTIFY_PLAYLIST_ID']
    return PLAYLIST_ID


def clean_playlist(spotify_object, playlist_id):
    """Clears a playlist of entries.

    Args:
        spotify_object (Spotify): A spotipy Spotify object
        playlist_id (str): The id of the playlist to be cleared.
    """
    # Note that playlist_items() fetches at most 100 items, that's why the loop is used.
    while True:
        old_items = spotify_object.playlist_items(playlist_id)
        if len(old_items["items"]):
            uri_list = []
            for item in old_items["items"]:
                uri_list.append(item["track"]["uri"])
            print(len(uri_list))
            spotify_object.playlist_remove_all_occurrences_of_items(playlist_id, uri_list)
        else:
            break


def get_top_artists(pylast_network_object, lastfm_username, number_of_artists):
    """Fetches the top artist for a last.fm user

    Args:
        pylast_network_object (LastFMNetwork): a network object
        lastfm_username (str): The name of the user
        number_of_artists (int): Number of artist to fetch

    Returns:
        [ TopItem ]: A list of TopItems
    """
    lastfm_user = pylast_network_object.get_user(lastfm_username)
    return lastfm_user.get_top_artists(limit=number_of_artists)


def get_my_top_artists(pylast_network_object, number_of_artists):
    """Fetches the top artist for the API user

    Args:
        pylast_network_object (LastFMNetwork): a network object
        number_of_artists (int): Number of artist to fetch

    Returns:
        [ TopItem ]: A list of TopItems
    """
    with open('auth.json', 'r', encoding='UTF-8') as auth:
        credentials = json.load(auth)
        USERNAME = credentials['LASTFM_USERNAME']
    return get_top_artists(pylast_network_object, USERNAME, 500)


def farm_own_crowns():
    sp = get_spotify_object()
    playlist_id = get_playlist_id()
    pylast_net = get_pylast_network_object()

    clean_playlist(sp, playlist_id)

    top_artists = get_my_top_artists(pylast_net, 500)

    track_ids = []
    for a in top_artists:
        if int(a.weight) < 30:
            results = sp.search(q=a.item.get_name(), limit=1, type='artist')
            tracks = sp.artist_top_tracks(results["artists"]["items"][0]["uri"])
            for i in range(min(30 - int(a.weight), len(tracks["tracks"]))):
                track_ids.append(tracks["tracks"][i]["uri"])

    while len(track_ids) > 100:
        sp.user_playlist_add_tracks(user=sp.me()['id'], playlist_id=playlist_id, tracks=track_ids[:100])
        track_ids = track_ids[100:]

    sp.user_playlist_add_tracks(user=sp.me()['id'], playlist_id=playlist_id, tracks=track_ids)


if __name__ == "__main__":
    farm_own_crowns()
