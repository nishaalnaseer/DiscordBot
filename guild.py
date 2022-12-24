class Guild():
    def __init__(self, server_id):
        """an object to hold all the data in of a discord server/guild"""
        self.server_id: str = server_id
        self.initialised = False  # if this guild has initialised or not
        self.background_task_channel: int = 0  # channel for watchdog and spotify monitoring
        self.spotify_playlist: str = ""  # playlist id
        self.steam_market_watchdog: dict = {}  # steam listings, format below

        # {
        #     "https://steamcommunity.com/market/listings/570/Blades%20of%20Voth%20Domosh": # listing url
        #     [
        #         570, # app_id
        #         15.0, # limit
        #         "Blades%20of%20Voth%20Domosh", # hash-name
        #         ">" # if 15 > current_price:
        #     ],
        # }

        self.steam_market_watchdog_limit: int = 50  # a limit on listings
        self.at_task = False  # if a bot is talking to a user in guild
        self.at_task_message = ""  # the contents of which the user replies with
        self.message_received = False  # if the user replied
        self.saved_tracks = []  # saved tracks, used for diff function
        self.temp_saved_tracks = None  # saved tracks, used for monitoring function

        self.users = {
            # a dict of spotify user_id as key and alias as value, helps with identify who added which track
            # format
            #   {
            #       sppotify_user_id: str : alias: str
            #   }
        }

    def init_tracks(self, spotify):
        self.saved_tracks = spotify.get_playlist_tracks(self.spotify_playlist, self.users)
