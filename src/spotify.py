import json
import os
from datetime import datetime, timedelta

import spotipy
from spotipy.oauth2 import SpotifyClientCredentials


class Spotify:
    def __init__(self):
        """an object that deals with spotify, it doesnt need to be here
        really but i thought it may be better for modularity in the future"""
        with open("config.json", 'r') as f:
            config = json.load(f)

        if config["dev"]:
            spotify_client = config["spotify_client_dev"]
            spotify_secret = config["spotify_secret_dev"]
        else:
            spotify_client = config["spotify_client_prod"]
            spotify_secret = config["spotify_secret_prod"]

        os.environ["SPOTIPY_CLIENT_ID"] = spotify_client
        os.environ["SPOTIPY_CLIENT_SECRET"] = spotify_secret

        auth_manager = SpotifyClientCredentials()
        self.sp = spotipy.Spotify(auth_manager=auth_manager)

    def get_playlist_tracks(self, playlist_id, users):
        """
        get tracks in a playlist
        returned format = {
                                track_id: [added_at, added_by_id, track_name]
                        }
        """
        info = {}
        results = self.sp.playlist_items(playlist_id)
        tracks = results['items']

        while results['next']:
            results = self.sp.next(results)
            tracks.extend(results['items'])

        for track in tracks:
            added_at = track["added_at"]
            datetime_added_at = datetime.strptime(added_at, "%Y-%m-%dT%H:%M:%SZ")
            time_adjusted = datetime_added_at + timedelta(hours=5)
            time_adjusted_str = datetime.strftime(time_adjusted, "%Y-%m-%d %H:%M:%S")

            try:
                added_by_name = users[track["added_by"]["id"]]
            except KeyError:
                added_by_name = "Unknown User"

            try:
                track_id = track["track"]["id"]
            except Exception as e:
                string = f"{str(datetime.now())}: {e}\n"
                with open("logs.txt", 'a') as f:
                    f.write(string)
            else:
                track_name = track["track"]["name"]
                info.update(
                    {
                        track_id: [time_adjusted_str, added_by_name, track_name]
                    }
                )

        return info