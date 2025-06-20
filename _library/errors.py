# Error classes
class PlayListError(Exception):
    def __init__(self, message):
        self.message = message
        super().__init__(self.message)


class GenreError(PlayListError):
    def __init__(self, genres):
        self.message = "Artist does not match any genres."
        self.genres = genres
        super().__init__(self.message)


class ArtistNotFoundError(PlayListError):
    def __init__(self, artist):
        self.message = "Artist not found on Spotify."
        self.artist = artist
        super().__init__(self.message)


class NoSongsFoundError(PlayListError):
    def __init__(self, artist):
        self.message = "No songs found matching artist."
        self.artist = artist
        super().__init__(self.message)


class SearchError(PlayListError):
    def __init__(self, artist):
        self.artist = artist
        self.message = f"Could not complete Spotify search for artist: {self.artist}."
        super().__init__(self.message)
