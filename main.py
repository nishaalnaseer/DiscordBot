import json
from discord.ext import tasks
import discord
import spotipy
import asyncio
import time
from threading import Thread
from urllib.parse import urlparse
from requests import get as http_get

from guild import Guild
import spotify

version = 0.2


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


def load_savefile_to_hm():
    """load saved guild data to memory"""
    while True:
        if not save_file:
            with open("guilds.json", 'r') as f:
                servers = json.load(f)
            break

        time.sleep(2)

    for server_id, server in servers.items():
        guild = Guild(server_id)
        guild.initialised = server["initialised"]
        guild.background_task_channel = server["background_task_channel"]
        guild.spotify_playlist = server["spotify_playlist"]
        guild.steam_market_watchdog = server["steam_market_watchdog"]
        guild.steam_market_watchdog_limit = server["steam_market_watchdog_limit"]
        guild.users = server["users"]

        guilds.update({server_id: guild})
        guild.init_tracks(spotify)


async def send_channel(channel, string):
    await channel.send(f"```{string}```")


def save_hm_to_file():
    """
    this is the file that saves guild data in dict to disk and it is running at all times on a
    different thread. when bool save_file is true contents in dict is saved to disk
    """
    global save_file

    while True:
        if save_file:
            save_hm = {}

            for guild_id in guilds:
                guild = guilds[guild_id]

                save_hm.update(
                    {
                        guild_id: {
                            "server_id": guild.server_id,
                            "initialised": guild.initialised,
                            "background_task_channel": guild.background_task_channel,
                            "spotify_playlist": guild.spotify_playlist,
                            "steam_market_watchdog": guild.steam_market_watchdog,
                            "steam_market_watchdog_limit": guild.steam_market_watchdog_limit,
                            "users": guild.users
                        }
                    }
                )

            with open("guilds.json", 'w') as f:
                json.dump(save_hm, f, indent=4)

            save_file = False

        time.sleep(2)


async def message_event_loop(server_id, message):
    """a function to detect if a the user has replied within a given time
    this is used while thee bot is in conversation with a user"""
    start = time.time()
    guild = guilds[server_id]
    guild.at_task_message = ""

    while True:
        if time.time() - start > 30:
            return True

        if guild.at_task_message != "":
            if guild.at_task_message.channel.id == message.channel.id \
                    and guild.at_task_message.author.id == message.author.id:
                guild.message_received = True
            else:
                guild.message_received = False
                guild.at_task_message = ""
                await asyncio.sleep(1)
                continue

        await asyncio.sleep(1)
        if guild.message_received:
            guild.message_received = False
            return False


async def ask_spotify_playlist(server_id, message):
    """conversation where the bot asks for the spotify playlist url, verifies it and saves it to disk"""
    global save_file
    guild = guilds[server_id]
    guild.at_task = True
    guild.at_task_message = ""
    await send_channel(message.channel, "Please enter your spotify playlist link and make sure its not "
                                        "private.\nPlease respond in 30 seconds.")
    timed_out = await message_event_loop(server_id, message)

    if timed_out:
        guild.at_task = False
        await send_channel(message.channel, "Operation aborted")
        return

    url = guild.at_task_message.content
    try:
        parsed = urlparse(url)
        path = parsed.path
        playlist_id = path[10:]
        name = spotify.sp.playlist(playlist_id="2FjwKUf69Fi67jED87dIMN")["name"]
        playlist = spotify.get_playlist_tracks(playlist_id)
    except spotipy.exceptions.SpotifyException as e:
        await send_channel(message.channel, "Incorrect playlist url")
        guild.at_task = False
        return
    except Exception:
        await send_channel(message.channel, "If you have entered the correct url contact bot admin, else enter the "
                                            "correct url")
        guild.at_task = False
        return

    string = f"Is this your playlist?\nPlaylist Name: {name}\n"
    if len(playlist) == 0:
        string += "There are no items in your playlist"
    else:
        i = 0
        for track_id in playlist:
            track = playlist[track_id]
            added_at, added_by_id, track_name = track[0], track[1], track[2]
            string += f"{i}. {track_name} - Added by {added_by_id} at {added_at}\n"

            i += 1
            if i == 5:
                break

    string += "Are you sure you want to continue with this playlist? '//yes'"
    try:
        await send_channel(message.channel, string)
    except discord.errors.HTTPException as e:
        print(string)
        print(e)

    timed_out = await message_event_loop(server_id, message)
    if timed_out:
        guild.at_task = False
        await send_channel(message.channel, "Operation aborted due to time out.")
        return

    if str(guild.at_task_message.content) == "//yes":
        guild.spotify_playlist = playlist_id
        save_file = True
        await send_channel(message.channel, "Your preferences have been saved!")
    else:
        await send_channel(message.channel, "Operation aborted!")

    guild.at_task = False
    return


async def init(message):
    """conversation between the bot and a user where the bot asks to confirm if current dicord
    channel is the channel for background tasks, this is where steam watchdog and spotify monitor
     function will reply to"""
    global guilds, save_file
    server_id = str(message.guild.id)
    guild = guilds[server_id]
    guild.at_task = True

    guild.at_task_message = ""
    guild.message_received = False

    await send_channel(message.channel, "Do you wish to use this channel for background tasks? ('//yes')\nPlease "
                                        "respond in 30 seconds.")

    timed_out = await message_event_loop(server_id, message)

    if timed_out:
        guild.at_task = False
        await send_channel(message.channel, "Operation aborted")
        return

    if str(guild.at_task_message.content).lower() == "//yes":
        guild.at_task_message = ""
        guild.initialised = True
        guild.background_task_channel = message.channel.id
        guild.at_task = True

        save_file = True

        await send_channel(message.channel, "Your preferences have been saved!\nDo you also wish to add spotify "
                                            "playlist for monitoring? '//yes'")

        timed_out = await message_event_loop(server_id, message)
        if timed_out:
            guild.at_task = False
            await send_channel(message.channel, "Operation aborted")
            return

        if str(guild.at_task_message.content).lower() == "//yes":
            await ask_spotify_playlist(server_id, message)
    else:
        await send_channel(message.channel, "Operation aborted!")

    guild.at_task = False


async def admin_interface(message):
    """this is hardcoded for a single user
    here admin can add servers for them to be able to access the bots features
    """
    content = str(message.content)
    global guilds, save_file

    args = content.split(" ")
    try:
        args0 = args[0]
        args1 = args[1]
        if args0 == "//add_server":
            server_id = args1

            guild = Guild(server_id)
            guilds.update({server_id: guild})

            save_file = True

            await send_channel(message.channel, "Your changes have been saved")

        elif args0 == "//remove_server":
            server_id = args1

            with open("guilds.json", 'r') as f:
                servers = json.load(f)

            servers.pop(server_id)
            with open("guilds.json", 'w') as f:
                json.dump(servers, f, indent=4)

            guilds.pop(server_id)
            await send_channel(message.channel, "Your changes have been saved")

        elif args0 == "//change_steam_limit":
            await set_watchdog_limit(message)

        elif args0 == "//help":
            string = "//add_server {server_id}\n//remove_server {server_id}\n//change_steam_limit {new_limit}"
            await send_channel(message.channel, string)
            return

    except Exception as e:
        await send_channel(message.channel, e)


async def diff(server_id, message):
    """send the difference between saved track and current playlist"""
    guild = guilds[server_id]

    raw_playlist = spotify.get_playlist_tracks(guild.spotify_playlist, guild.users)
    playlist_name = spotify.sp.playlist(guild.spotify_playlist)["name"]

    string = f"Playlist: {playlist_name}\n\n"
    temp_string = diff_string_plus_minus(raw_playlist, guild.saved_tracks)

    if len(temp_string) == 0:
        string += "No changes"
    else:
        string += temp_string
        guild.saved_tracks = raw_playlist

    await send_channel(message.channel, string)


def get_api_url(appid, hash_name):
    """turns a steam app_id an item hash_name into a url that returns a json obj"""
    url = f"https://steamcommunity.com/market/priceoverview/?appid={appid}" \
          f"&market_hash_name={hash_name}&currency=1"
    return url


async def update_steam(server_id, message):
    """conversation between useer and bot where the user adds or updates item in steam watch dog"""
    global save_file

    guild = guilds[server_id]
    guild.at_task = True

    while True:
        # url validation
        await send_channel(message.channel, "Please enter a valid steam market URL below!")
        timed_out = await message_event_loop(server_id, message)

        if timed_out:
            guild.at_task = False
            await send_channel(message.channel, "Operation aborted due to timeout!")
            return

        url = str(guild.at_task_message.content)

        url_parsed = urlparse(url)
        urlpath = url_parsed.path
        if url_parsed.netloc != "steamcommunity.com" and urlpath[:17] != "/market/listings/":
            await send_channel(message.channel, "Invalid URL!")
            continue
        url_content = urlpath.split("/")
        app_id = int(url_content[-2])
        hash_name = url_content[-1]

        api_url = get_api_url(app_id, hash_name)
        response = http_get(api_url)

        if response.status_code != 200:
            await send_channel(message.channel, f"Invalid  URL! Reason: {response.reason}")
            continue
        break

    current_item_details = response.json()
    current_price_str: str = current_item_details["median_price"]
    current_price: float = float(current_price_str.replace("$", ""))

    while True:
        # limit validation
        await send_channel(message.channel, f"Enter a limit for when you want to be informed of")
        timed_out = await message_event_loop(server_id, message)

        if timed_out:
            guild.at_task = False
            await send_channel(message.channel, "Operation aborted due to timeout!")
            return

        try:
            limit: float = float(guild.at_task_message.content)
        except ValueError:
            await send_channel(message.channel, f"Please enter a valid float")
            continue
        break

    while True:
        # getting the boolean operator sign
        await send_channel(message.channel, f"When you want to be informed, do you want the limit to me lower or "
                                            f"greater than the current price? Current median price = "
                                            f"{current_price_str} ('g'/'l') Enter 'e' to exit")
        timed_out = await message_event_loop(server_id, message)

        if timed_out:
            guild.at_task = False
            await send_channel(message.channel, "Operation aborted due to timeout!")
            return

        comparison_type = str(guild.at_task_message.content).lower()
        if comparison_type == "e":
            guild.at_task = False
            await send_channel(message.channel, "Operation aborted!")
            return

        if comparison_type != "g" and comparison_type != "l":
            await send_channel(message.channel, "Invalid selection")
            continue

        if comparison_type == "g" and limit < current_price:
            await send_channel(message.channel, "Are you sure? Current median price already exceeds your limit. ("
                                                "'y')")

            timed_out = await message_event_loop(server_id, message)

            if timed_out:
                guild.at_task = False
                await send_channel(message.channel, "Operation aborted due to timeout!")
                return

            if str(guild.at_task_message.content) != "y":
                continue

        elif comparison_type == "l" and limit > current_price:
            await send_channel(message.channel, "Are you sure? Your limit already exceeds the current median price. ("
                                                "'y')")

            timed_out = await message_event_loop(server_id, message)

            if timed_out:
                guild.at_task = False
                await send_channel(message.channel, "Operation aborted due to timeout!")
                return

            if str(guild.at_task_message.content) != "y":
                continue

        break

    if comparison_type == "l":
        sign = ">"
    elif comparison_type == "g":
        sign = "<"
    else:
        await send_channel(message.channel, "Unexpected error")
        guild.at_task = False
        return

    string = f"So you want to be informed of when {limit} {sign} current_median_price\nEnter 'y' if you want these " \
             f"instructions to be recorded!"

    await send_channel(message.channel, string)

    timed_out = await message_event_loop(server_id, message)

    if timed_out:
        guild.at_task = False
        await send_channel(message.channel, "Operation aborted due to timeout!")
        return

    if str(guild.at_task_message.content) != "y":
        guild.at_task = False
        await send_channel(message.channel, "Operation aborted!")
        return

    try:
        guild.steam_market_watchdog[url]
    except KeyError:
        if len(guild.steam_market_watchdog) > guild.steam_market_watchdog_limit:
            await send_channel(message.channel, "No more items can be added to WatchDog as the watch limit has been "
                                                "reached!")
            guild.at_task = False
            return

    guild.steam_market_watchdog.update({
        url: [app_id, limit, hash_name, sign]
    })
    save_file = True
    await send_channel(message.channel, "Your changes have been saved!")

    guild.at_task = False
    return


async def set_watchdog_limit(message):
    """admin function where admin can set the limit of watchdog for server"""
    global save_file

    args = str(message.content).split(" ")
    num = int(args[1])
    server_id = args[2]

    guild = guilds[server_id]
    guild.steam_market_watchdog_limit = num

    save_file = True

    await send_channel(message.channel, "Limit changed")


async def remove_steam(server_id, message):
    """removes steam item takes url as an additional argument"""
    global save_file

    guild = guilds[server_id]

    args = message.content.split(" ")
    if len(args) != 2:
        await send_channel(message.channel, "Please enter '//remove_steam_item' followed by items url")
        return

    url = args[1]
    url_parsed = urlparse(url)
    urlpath = url_parsed.path

    if url_parsed.netloc != "steamcommunity.com" and urlpath[:17] != "/market/listings/":
        await send_channel(message.channel, "Please enter a valid URL!")
        return

    url_content = urlpath.split("/")
    app_id = int(url_content[-2])
    hash_name = url_content[-1]

    try:
        guild.steam_market_watchdog[url]
    except KeyError:
        await send_channel(message.channel, "Item not added to steam watchdog!")
        return

    test_url = get_api_url(app_id, hash_name)
    response = http_get(test_url)

    if response.reason != "OK":
        await send_channel(message.channel, "Please enter a valid URL!")
        return

    guild.steam_market_watchdog.pop(url)

    save_file = True

    formatted_name = hash_name.replace("%20", " ")
    await send_channel(message.channel, f"'{formatted_name}' has been removed from steam watchdog")
    return


async def list_watchdog(server_id, message):
    """returns a list of the listings currently in steam watchdog"""
    guild = guilds[server_id]
    string = ""
    for item in guild.steam_market_watchdog:
        item_details = guild.steam_market_watchdog[item]
        app_id = item_details[0]
        limit = item_details[1]
        hash_name = item_details[2]

        url = get_api_url(app_id, hash_name)

        steam_raw_data = http_get(url)
        steam_data = steam_raw_data.json()
        price = steam_data["median_price"]
        hash_name = hash_name.replace("%20", " ")

        string += f"Name: {hash_name} - app_id: {app_id} - limit: {limit} - current median price: {price} - url: {item}\n"

    if string == "":
        await send_channel(message.channel, "Empty list here")
        return None

    await send_channel(message.channel, string)


async def watchdog(client):
    """background function for watch dog, checks if the limit of listings have been reached and if so informs
    through the background channel"""
    for guild_id in guilds:
        guild = guilds[guild_id]
        channel_id = guild.background_task_channel
        channel = client.get_channel(channel_id)

        listings = guild.steam_market_watchdog
        for url in listings:
            details = listings[url]
            app_id = details[0]
            limit = details[1]
            hash_name = details[3]
            sign = details[4]

            api_url = get_api_url(app_id, hash_name)
            current_details = http_get(api_url).json()
            current_price_str = current_details["median_price"]
            current_price: float = float(current_price_str.replace("$", ""))

            conditional = exec(f"{current_price} {sign} {limit}")
            if conditional:
                hash_name_formatted = hash_name.replace("%20", "")
                await send_channel(channel, f"{hash_name_formatted} has reached {current_price_str}")


async def add_user(server_id, message):
    """a conversation where users add user ids to the bot, this helps in showing a known alias when returning
    differences in spotify playlists"""
    global save_file

    guild = guilds[server_id]
    guild.at_task = True
    await send_channel(message.channel, "Enter user_id below")
    timed_out = await message_event_loop(server_id, message)

    if timed_out:
        guild.at_task = False
        await send_channel(message.channel, "Operation aborted due to time out")
        return

    user_id = str(guild.at_task_message.content)

    try:
        # user_id validation
        spotify.sp.user_playlists(user_id)
    except spotipy.exceptions.SpotifyException:
        await send_channel(message.channel, "Invalid user_id")
        guild.at_task = False
        return

    await send_channel(message.channel, "Enter user alias")
    timed_out = await message_event_loop(server_id, message)

    if timed_out:
        guild.at_task = False
        await send_channel(message.channel, "Operation aborted due to time out")
        return

    alias = str(guild.at_task_message.content)
    guild.users.update({user_id: alias})
    save_file = True

    guild.at_task = False
    await send_channel(message.channel, "Your preferences have been saved")
    return


def run_bot(discord_token):
    """main function of dicord.py"""
    client = discord.Client(intents=discord.Intents.all())
    global guilds

    @client.event
    async def on_message(message):
        global guilds
        # Make sure bot doesn't get stuck in an infinite loop

        content = message.content
        author = message.author

        channel = message.channel
        print(f"{author} said {content} on {channel}")

        if client.user == author:
            return

        if message.author.id == 260450479278915585 and message.channel.id == 1053933250143326269:
            await admin_interface(message)
            return

        try:
            server_id = str(message.guild.id)
        except AttributeError:
            return

        try:
            guild = guilds[server_id]
        except KeyError:
            await send_channel(message.channel, f"Server {server_id} not supported, please contact bot devs!")
            return

        if guild.at_task:
            guild.at_task_message = message
            guild.message_received = True
            return

        if content[:2] != "//":
            return

        if not guild.initialised and content != "//init":
            await send_channel(message.channel, f"Please type '//init' and start initialising to set up a channel"
                                                f" for background tasks")
            return

        args = content.split(" ")
        if len(args) == 0:
            return

        arg1 = args[0]
        try:
            if arg1 == "//init":
                await init(message)
            elif arg1 == "//set_playlist":
                await ask_spotify_playlist(server_id, message)
            elif arg1 == "//diff":
                await diff(server_id, message)
            elif arg1 == "//update_steam_item":
                await update_steam(server_id, message)
            elif arg1 == "//remove_steam_item":
                await remove_steam(server_id, message)
            elif arg1 == "//list_watchdog":
                await list_watchdog(server_id, message)
            elif arg1 == "//add_sp_alias":
                await add_user(server_id, message)
            elif arg1 == "//help":
                string = "Functions:\n\t1. //init to setup a background channel for wacthdog and monitoring " \
                         "functions.\n\t2. //set_playlist to setup playlist for monitoring, and if you want you can " \
                         "call diff to show the difference from the last time diff was called.\n\t3. " \
                         "//update_steam_item add an item from steam market, and you will be informed of when that " \
                         "limit is reached\n\t4. //remove_steam_item remove steam market listings\n\t5. " \
                         "//list_watchdog list items in steam watchdog.\n\t6. //add_sp_alias to add an alias to " \
                         "spotify username/id this helps in identify them if they add a track to the " \
                         "playlist.\n\nPlease follow the bots instructions carefully in each step."
                await send_channel(message.channel, string)
                return
        except Exception as e:
            channel = client.get_channel(1053933250143326269)
            await send_channel(channel, f"Exception {e} at server {server_id}")

        return

    @tasks.loop(seconds=15)  # task runs every 15 seconds
    async def my_background_task():
        for guild_id in guilds:
            guild = guilds[guild_id]
            channel = client.get_channel(guild.background_task_channel)

            string = ""
            raw_playlist = spotify.get_playlist_tracks(guild.spotify_playlist, guild.users)

            string += diff_string_plus_minus(raw_playlist, guild.temp_saved_tracks)

            if string == "":
                continue

            guild.temp_saved_tracks = raw_playlist
            await send_channel(channel, string)

    @tasks.loop(seconds=3600)
    async def hourly_task():
        pass

    @my_background_task.before_loop
    @hourly_task.before_loop
    async def before_my_task():
        await client.wait_until_ready()  # wait until the bot logs in

    @client.event
    async def on_ready():
        my_background_task.start()  # start the task to run in the background
        hourly_task.start()

        print(f'Logged in as {client.user}')
        print('------')

    client.run(discord_token)


def main():
    global guilds
    with open("config.json", 'r') as f:
        config = json.load(f)

    thread = Thread(target=save_hm_to_file)
    thread.start()

    dev = config["dev"]
    if dev:
        discord_token = config["discord_token_dev"]
    else:
        discord_token = config["discord_token_prod"]

    load_savefile_to_hm()
    for guild_id in guilds:
        guild = guilds[guild_id]
        raw_playlist = spotify.get_playlist_tracks(guild.spotify_playlist, guild.users)
        guild.temp_saved_tracks = raw_playlist

    run_bot(discord_token)


if __name__ == '__main__':
    guilds = {}
    with open("users.json", 'r') as f:
        collabs = json.load(f)

    save_file = False

    spotify = spotify.Spotify()

    main()
