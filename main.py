import json
from discord.ext import tasks
import discord
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials
import os
from datetime import datetime
from datetime import timedelta

version = 0.1


def get_playlists():
    playlists = sp.user_playlists('31f34fv4orjls6i7vyc5dtr6ldoe')
    return playlists


# "2FjwKUf69Fi67jED87dIMN" main playlist id
def get_playlist_tracks(playlist_id):
    """
    get tracks in a playlist
    returned format = {
                            track_id: [added_at, added_by_id, track_name]
                    }
    """
    info = {}
    results = sp.playlist_items(playlist_id)
    tracks = results['items']

    # with open("temp.json", 'w') as f:
    #     json.dump(results, f, indent=4)

    while results['next']:
        results = sp.next(results)
        tracks.extend(results['items'])

    # with open("temp2.json", 'w') as f: # debug
    #     json.dump(tracks, f, indent=4) # debug
    # print(f"track2len= ", len(tracks)) # debug

    for track in tracks:
        added_at = track["added_at"]
        datetime_added_at = datetime.strptime(added_at, "%Y-%m-%dT%H:%M:%SZ")
        time_adjusted = datetime_added_at + timedelta(hours=5)
        time_adjusted_str = datetime.strftime(time_adjusted, "%Y-%m-%d %H:%M:%S")
        added_by_id = collabs[track["added_by"]["id"]]
        try:
            track_id = track["track"]["id"]
        except Exception as e:
            string = f"{datetime.now}: e\n"
            with open("logs.txt", 'a') as f:
                f.write(string)
        track_name = track["track"]["name"]
        info.update(
            {
                track_id: [time_adjusted_str, added_by_id, track_name]
            }
        )

    return info


def diff_string(playlist_a: dict, playlist_b: dict, char: str) -> str:
    """Compares playlist_a to playlist_b and if track in playlist_a is not in
    playlist_b it is appended to string"""
    string = ""

    for track_id, track in playlist_a.items():
        try:
            playlist_b[track_id]
        except KeyError:
            added_at, added_by_id, track_name = track[0], track[1], track[2]
            string += f"{char}{track_name} - Added by {added_by_id} at {added_at}\n"

    return string


def diff_string_plus_minus(playlist_a: dict, playlist_b: dict) -> str:
    """compares playlist_a and playlist_b returns diff string"""
    string = ""
    string += diff_string(playlist_a, playlist_b, "++")
    string += diff_string(playlist_b, playlist_a, "--")

    return string


async def monitor(message):
    global MONITOR, MONITOR_NUM

    content = message.content
    args = content.split(" ")
    if len(args) != 2:
        await message.channel.send(f"```Number of arguments should be 2.```")
        return

    try:
        num = int(args[1])
    except ValueError:
        await message.channel.send(f"```Please enter an integer for arg2```")
        return

    playlists = get_playlists()
    items = playlists["items"]

    try:
        playlist = items[num]
    except IndexError:
        await message.channel.send(f"```Index out of bounds```")
        return
    
    
    MONITOR_NUM = num
    name = playlist["name"]

    if MONITOR:
        await message.channel.send(f"```Already monitoring {name}```")
        return

    MONITOR = True

    await message.channel.send(f"```Monitoring {name}```")


async def stop(message):
    global MONITOR, MONITOR_NUM
    if not MONITOR:
        await message.channel.send(f"```Monitoring already paused```")
        return

    MONITOR_NUM = 0
    MONITOR = False

    await message.channel.send(f"```Pausing Monitoring```")


async def list_playlists(message):
    playlists = get_playlists()
    string = ""
    total = playlists["total"]
    items = playlists["items"]
    if items == 0:
        return "No playlists"

    string += f"Number of playlists: {total}\n"

    for index, i in enumerate(items):
        name = i["name"]
        count = i["tracks"]["total"]
        playlist_id = i["id"]
        string += f"{index}: {name} - songs: {count}\n"
    string += "\nSelect index to monitor or diff playlist.'"

    await message.channel.send(f"```{string}```")


async def diff(message, save=True):
    content = message.content

    args = content.split(" ")
    if len(args) != 2:
        await message.channel.send(f"```Number of arguments should be 2.```")
        return

    try:
        num = int(args[1])
    except ValueError:
        await message.channel.send(f"```Please enter an integer for arg2```")
        return

    playlists = get_playlists()
    items = playlists["items"]

    try:
        playlist = items[num]
    except IndexError:
        await message.channel.send(f"```Index out of bounds```")
        return

    playlist_id = playlist["id"]
    name = playlist["name"]
    tracks = get_playlist_tracks(playlist_id)

    string = "Showing the diff file, compared to the previously saved playlist.\n"
    string += f"Playlist name: {name}, id: {playlist_id}\n\n"

    with open("saved_playlists.json", 'r') as f:
        saved_playlists = json.load(f)

    try:
        saved_tracks = saved_playlists[playlist_id]
    except KeyError:
        saved_tracks = {}

    temp_string = diff_string_plus_minus(tracks, saved_tracks)
    if temp_string == "":
        string += "No diff\n"
    string += temp_string

    if save:
        saved_playlists.update({playlist_id: tracks})
        with open("saved_playlists.json", 'w') as f:
            json.dump(saved_playlists, f, indent=4)

        await message.channel.send(f"```{string}```")


async def help_func(message):
    string = "Hello, enter /help for this prompt. '/list' to list playlists and afterwards you can use f'/diff " \
             "index_from_list' to get the diff of current playlist and its previously saved file, use '/monitor " \
             "index_from_list' to monitor for changes in playlist."

    await message.channel.send(f"```{string}```")


class MyClient(discord.Client):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        playlists = get_playlists()["items"]
        playlist_id = playlists[MONITOR_NUM]["id"]
        self.tracks = get_playlist_tracks(playlist_id)
        self.saved_num = MONITOR_NUM


        @self.event
        async def on_message(message):
            # Make sure bot doesn't get stuck in an infinite loop
            if message.author == client.user or message.channel.id != 1043577355328835584:
                return

            # Get data about the user
            username = str(message.author)
            user_message = str(message.content)
            channel = str(message.channel)

            print(f"{username} said {user_message} on {channel}")

            arguments = user_message.split(" ")
            try:
                function = functions[arguments[0]]
                await function(message)
            except KeyError:
                # await message.channel.send("hi there")
                pass

            # send_clients(f"{username} said {user_message} on {channel}")
            # await send_message(message, user_message)

        # an attribute we can access from our task
        self.counter = 0

    async def setup_hook(self) -> None:
        # start the task to run in the background
        self.my_background_task.start()

    async def on_ready(self):
        print(f'Logged in as {self.user} (ID: {self.user.id})')
        print('------')

    @tasks.loop(seconds=15)  # task runs every 15 seconds
    async def my_background_task(self):
        channel = self.get_channel(1043577355328835584)  # channel ID goes here

        playlists = get_playlists()["items"]
        playlist = playlists[MONITOR_NUM]
        playlist_id = playlist["id"]
        name = playlist["name"]
        tracks = get_playlist_tracks(playlist_id)

        if MONITOR:
            if self.saved_num != MONITOR_NUM:
                self.saved_num = MONITOR_NUM
                self.tracks = tracks
                return
            else:
                # string = "Detected a change in a playlist.\n"
                # string += f"Playlist name: {name}, id: {playlist_id}\n\n"
                temp_string = diff_string_plus_minus(tracks, self.tracks)
                if temp_string != "":
                    self.tracks = tracks
                    await channel.send(f"```{temp_string}```")

    @my_background_task.before_loop
    async def before_my_task(self):
        await self.wait_until_ready()  # wait until the bot logs in


if __name__ == '__main__':
    os.environ["SPOTIPY_CLIENT_ID"] = "fb294266f2a7483e8c3b40e8dc952ff5"
    os.environ["SPOTIPY_CLIENT_SECRET"] = "f51dc791afc04dd18211ad776e8b500d"

    auth_manager = SpotifyClientCredentials()
    sp = spotipy.Spotify(auth_manager=auth_manager)

    with open("users.json", 'r') as f:
        collabs = json.load(f)

    MONITOR = False
    MONITORED = []
    MONITOR_NUM = 0
    with open("config.json", 'r') as f:
        config = json.load(f)

    wait_duration = config["monitoring"]

    functions = {
        "/monitor": monitor,
        "/list": list_playlists,
        "/diff": diff,
        "/stop": stop,
        "/help": help_func
    }

    client = MyClient(intents=discord.Intents.all())
    client.run(config["token"])
