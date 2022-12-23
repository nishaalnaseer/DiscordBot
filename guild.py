class Guild():
    def __init__(self, server_id):
        self.server_id: str = server_id
        self.initialised = False
        self.background_task_channel: int = 0
        self.spotify_playlist: str = ""
        self.steam_market_watchdog: dict = {}
        self.steam_market_watchdog_limit: int = 50
        self.at_task = False
        self.at_task_message = ""
        self.message_received = False
        self.saved_tracks = []
        self.temp_saved_tracks = None

    def init_tracks(self, spotify):
        self.saved_tracks = spotify.get_playlist_tracks(self.spotify_playlist)
