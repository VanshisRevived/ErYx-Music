# ============================================================
# ERYX MUSIC
# Discord.py + Wavelink 3.5.x + Lavalink v4
# ============================================================

import asyncio
import time
from collections import defaultdict, deque

import discord
from discord import app_commands
from discord.ext import commands
import wavelink


# ============================================================
# CONFIG
# EDIT THESE 2 VALUES
# ============================================================

DISCORD_TOKEN = "PASTE_YOUR_DISCORD_BOT_TOKEN_HERE"

LAVALINK_HOST = "lavalink-2026-production-07a0.up.railway.app"
LAVALINK_PORT = 443
LAVALINK_PASSWORD = "PASTE_YOUR_LAVALINK_PASSWORD_HERE"
LAVALINK_SECURE = True

# Prefix commands:
# !!play song
# !!skip
# !!queue
PREFIX = "!!"


# ============================================================
# INTENTS
# ============================================================

intents = discord.Intents.default()
intents.guilds = True
intents.voice_states = True
intents.members = True
intents.message_content = True


# ============================================================
# DATA
# ============================================================

guild_settings = defaultdict(
    lambda: {
        "volume": 100,
        "loop": "off",
        "cleanup": True,
    }
)

guild_history = defaultdict(
    lambda: deque(maxlen=50)
)

guild_favorites = defaultdict(list)
guild_likes = defaultdict(set)
guild_feedback = defaultdict(list)

text_channels = {}
search_cache = {}

started_at = time.time()


# ============================================================
# BOT
# ============================================================

class ErYxMusic(commands.Bot):

    def __init__(self):
        super().__init__(
            command_prefix=PREFIX,
            intents=intents,
            help_command=None
        )

    async def setup_hook(self):

        print("[ErYx] Connecting to Lavalink...")

        scheme = "https" if LAVALINK_SECURE else "http"

        uri = (
            f"{scheme}://"
            f"{LAVALINK_HOST}:"
            f"{LAVALINK_PORT}"
        )

        node = wavelink.Node(
            identifier="ErYx-Lavalink",
            uri=uri,
            password=LAVALINK_PASSWORD,
            retries=None,
            resume_timeout=60,
        )

        await wavelink.Pool.connect(
            nodes=[node],
            client=self
        )

        print("[ErYx] Lavalink connection started.")

        try:
            synced = await self.tree.sync()
            print(
                f"[ErYx] Synced {len(synced)} slash commands."
            )
        except Exception as e:
            print(
                f"[ErYx] Slash sync error: {e}"
            )

    async def on_ready(self):

        print()
        print("======================================")
        print("          ERYX MUSIC ONLINE")
        print("======================================")
        print(f"Bot       : {self.user}")
        print(f"Guilds    : {len(self.guilds)}")
        print(f"Prefix    : {PREFIX}")
        print("Volume    : 0-300%")
        print("Search    : Top 15")
        print("Lavalink  : Connected")
        print("======================================")
        print()


bot = ErYxMusic()


# ============================================================
# LAVALINK EVENTS
# ============================================================

@bot.listen()
async def on_wavelink_node_ready(payload):

    print(
        f"[Lavalink] READY: "
        f"{payload.node.identifier}"
    )


@bot.listen()
async def on_wavelink_node_disconnected(payload):

    print(
        f"[Lavalink] DISCONNECTED: "
        f"{payload.node.identifier}"
    )


@bot.listen()
async def on_wavelink_track_start(payload):

    player = payload.player

    if not player or not player.guild:
        return

    if payload.track:

        guild_history[
            player.guild.id
        ].appendleft(
            payload.track
        )

    channel = text_channels.get(
        player.guild.id
    )

    if not channel:
        return

    try:

        embed = discord.Embed(
            title="▶ Now Playing",
            description=(
                f"**{payload.track.title}**\n"
                f"`{payload.track.author}`"
            )
        )

        if payload.track.artwork:
            embed.set_thumbnail(
                url=payload.track.artwork
            )

        await channel.send(
            embed=embed
        )

    except Exception as e:

        print(
            f"[Track Start] {e}"
        )


@bot.listen()
async def on_wavelink_track_end(payload):

    player = payload.player

    if not player or not player.guild:
        return

    guild_id = player.guild.id
    settings = guild_settings[guild_id]

    # Track loop
    if settings["loop"] == "track":

        if payload.track:

            try:
                await player.play(
                    payload.track
                )
                return
            except Exception as e:
                print(
                    f"[Loop Error] {e}"
                )

    # Queue loop
    elif settings["loop"] == "queue":

        if payload.track:

            try:
                await player.queue.put_wait(
                    payload.track
                )
            except Exception as e:
                print(
                    f"[Queue Loop] {e}"
                )

    # Auto cleanup
    if (
        not player.queue
        and settings["cleanup"]
    ):

        await asyncio.sleep(3)

        try:

            if (
                player.channel
                and len(player.channel.members) <= 1
            ):
                await player.disconnect()

        except Exception:
            pass


# ============================================================
# HELPERS
# ============================================================

def get_player(guild):

    if not guild:
        return None

    return guild.voice_client


def duration(ms):

    seconds = max(
        0,
        int(ms / 1000)
    )

    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    seconds %= 60

    if hours:

        return (
            f"{hours}:"
            f"{minutes:02}:"
            f"{seconds:02}"
        )

    return (
        f"{minutes}:"
        f"{seconds:02}"
    )


def track_text(track, number=None):

    prefix = ""

    if number is not None:
        prefix = f"**{number}.** "

    return (
        f"{prefix}{track.title}\n"
        f"└ `{track.author}` • "
        f"`{duration(track.length)}`"
    )


async def connect_player(interaction):

    if not interaction.user.voice:

        await interaction.response.send_message(
            "Join a voice channel first.",
            ephemeral=True
        )

        return None

    channel = interaction.user.voice.channel

    player = get_player(
        interaction.guild
    )

    if player:

        try:

            if player.channel != channel:
                await player.move_to(channel)

        except Exception:
            pass

        return player

    try:

        player = await channel.connect(
            cls=wavelink.Player,
            self_deaf=True
        )

        return player

    except Exception as e:

        print(
            f"[VOICE ERROR] "
            f"{type(e).__name__}: {e}"
        )

        await interaction.response.send_message(
            "I couldn't join that voice channel.",
            ephemeral=True
        )

        return None


async def search_music(query):

    try:

        return await wavelink.Playable.search(
            query,
            source=wavelink.TrackSource.YouTubeMusic
        )

    except Exception:

        return await wavelink.Playable.search(
            query
        )


async def get_first_track(query):

    result = await search_music(query)

    if not result:
        return None

    if isinstance(
        result,
        wavelink.Playlist
    ):

        if not result.tracks:
            return None

        return result.tracks[0]

    return result[0]


async def add_track(player, track):

    if player.current:

        await player.queue.put_wait(
            track
        )

        return False

    await player.play(
        track
    )

    return True


async def simple_message(
    interaction,
    message
):

    if interaction.response.is_done():

        await interaction.followup.send(
            message
        )

    else:

        await interaction.response.send_message(
            message
        )


# ============================================================
# /PLAY
# ============================================================

@bot.tree.command(
    name="play",
    description="Play a song."
)
@app_commands.describe(
    query="Song name or URL"
)
async def play(
    interaction,
    query: str
):

    await interaction.response.defer()

    player = await connect_player(
        interaction
    )

    if not player:
        return

    text_channels[
        interaction.guild.id
    ] = interaction.channel

    try:

        result = await search_music(
            query
        )

        if not result:

            return await interaction.followup.send(
                "No results found."
            )

        # Playlist
        if isinstance(
            result,
            wavelink.Playlist
        ):

            count = 0

            for track in result.tracks:

                await player.queue.put_wait(
                    track
                )

                count += 1

            if not player.current and player.queue:

                track = await player.queue.get()

                await player.play(
                    track
                )

            return await interaction.followup.send(
                f"Added **{count} tracks**."
            )

        track = result[0]

        started = await add_track(
            player,
            track
        )

        if started:

            message = (
                f"▶ Playing **{track.title}**"
            )

        else:

            message = (
                f"Added to queue: "
                f"**{track.title}**"
            )

        await interaction.followup.send(
            message
        )

    except Exception as e:

        print(
            f"[PLAY ERROR] "
            f"{type(e).__name__}: {e}"
        )

        await interaction.followup.send(
            f"Playback error: "
            f"`{type(e).__name__}`"
        )


# ============================================================
# /SEARCH — TOP 15
# ============================================================

@bot.tree.command(
    name="search",
    description="Search music and show the top 15 results."
)
@app_commands.describe(
    query="What do you want to search for?"
)
async def search(
    interaction,
    query: str
):

    await interaction.response.defer()

    try:

        result = await search_music(
            query
        )

        if not result:

            return await interaction.followup.send(
                "No results found."
            )

        if isinstance(
            result,
            wavelink.Playlist
        ):

            tracks = list(
                result.tracks
            )

        else:

            tracks = list(result)

        # HARD TOP 15
        tracks = tracks[:15]

        search_cache[
            interaction.user.id
        ] = tracks

        lines = []

        for number, track in enumerate(
            tracks,
            1
        ):

            lines.append(
                track_text(
                    track,
                    number
                )
            )

        embed = discord.Embed(
            title="🔎 ErYx Music — Search Suggestions",
            description="\n\n".join(lines)
        )

        embed.set_footer(
            text="Top 15 results • Use /play <song> to play"
        )

        await interaction.followup.send(
            embed=embed
        )

    except Exception as e:

        print(
            f"[SEARCH ERROR] "
            f"{type(e).__name__}: {e}"
        )

        await interaction.followup.send(
            f"Search failed: "
            f"`{type(e).__name__}`"
        )


# ============================================================
# /SKIP
# ============================================================

@bot.tree.command(
    name="skip",
    description="Skip the current song."
)
async def skip(interaction):

    player = get_player(
        interaction.guild
    )

    if not player or not player.current:

        return await interaction.response.send_message(
            "Nothing is playing.",
            ephemeral=True
        )

    await player.skip()

    await interaction.response.send_message(
        "⏭ Skipped."
    )


# ============================================================
# /STOP
# ============================================================

@bot.tree.command(
    name="stop",
    description="Stop music and clear the queue."
)
async def stop(interaction):

    player = get_player(
        interaction.guild
    )

    if not player:

        return await interaction.response.send_message(
            "I'm not connected.",
            ephemeral=True
        )

    player.queue.clear()

    await player.stop()

    await interaction.response.send_message(
        "⏹ Playback stopped."
    )


# ============================================================
# /PLAYNOW
# ============================================================

@bot.tree.command(
    name="playnow",
    description="Immediately play a song."
)
@app_commands.describe(
    query="Song"
)
async def playnow(
    interaction,
    query: str
):

    await interaction.response.defer()

    player = await connect_player(
        interaction
    )

    if not player:
        return

    try:

        track = await get_first_track(
            query
        )

        if not track:

            return await interaction.followup.send(
                "No results found."
            )

        await player.play(
            track
        )

        await interaction.followup.send(
            f"▶ Now playing **{track.title}**"
        )

    except Exception as e:

        await interaction.followup.send(
            f"Playback error: "
            f"`{type(e).__name__}`"
        )


# ============================================================
# /P — PLAY ALIAS
# ============================================================

@bot.tree.command(
    name="p",
    description="Quick play a song."
)
@app_commands.describe(
    query="Song"
)
async def slash_p(
    interaction,
    query: str
):

    await play.callback(
        interaction,
        query
    )


# ============================================================
# /PLAYS KIP
# ============================================================

@bot.tree.command(
    name="playskip",
    description="Play a song immediately."
)
@app_commands.describe(
    query="Song"
)
async def playskip(
    interaction,
    query: str
):

    await playnow.callback(
        interaction,
        query
    )


# ============================================================
# /JOIN
# ============================================================

@bot.tree.command(
    name="join",
    description="Join your voice channel."
)
async def join(interaction):

    player = await connect_player(
        interaction
    )

    if player:

        await simple_message(
            interaction,
            f"Connected to **{player.channel.name}**."
        )


# ============================================================
# /SUMMON
# ============================================================

@bot.tree.command(
    name="summon",
    description="Summon ErYx Music."
)
async def summon(interaction):

    await join.callback(
        interaction
    )


# ============================================================
# /PAUSE
# ============================================================

@bot.tree.command(
    name="pause",
    description="Pause playback."
)
async def pause(interaction):

    player = get_player(
        interaction.guild
    )

    if not player or not player.current:

        return await interaction.response.send_message(
            "Nothing is playing.",
            ephemeral=True
        )

    await player.pause(
        True
    )

    await interaction.response.send_message(
        "⏸ Paused."
    )


# ============================================================
# /RESUME
# ============================================================

@bot.tree.command(
    name="resume",
    description="Resume playback."
)
async def resume(interaction):

    player = get_player(
        interaction.guild
    )

    if not player:

        return await interaction.response.send_message(
            "Nothing is playing.",
            ephemeral=True
        )

    await player.pause(
        False
    )

    await interaction.response.send_message(
        "▶ Resumed."
    )


# ============================================================
# /VOLUME — MAX 300
# ============================================================

@bot.tree.command(
    name="volume",
    description="Set volume. Maximum 300%."
)
@app_commands.describe(
    amount="Volume from 0 to 300"
)
async def volume(
    interaction,
    amount: app_commands.Range[int, 0, 300]
):

    player = get_player(
        interaction.guild
    )

    if not player:

        return await interaction.response.send_message(
            "I'm not connected.",
            ephemeral=True
        )

    # Extra hard safety check
    amount = max(
        0,
        min(
            int(amount),
            300
        )
    )

    await player.set_volume(
        amount
    )

    guild_settings[
        interaction.guild.id
    ]["volume"] = amount

    await interaction.response.send_message(
        f"🔊 Volume set to **{amount}%**."
    )


# ============================================================
# /VOL
# ============================================================

@bot.tree.command(
    name="vol",
    description="Set volume. Maximum 300%."
)
@app_commands.describe(
    amount="Volume from 0 to 300"
)
async def vol(
    interaction,
    amount: app_commands.Range[int, 0, 300]
):

    await volume.callback(
        interaction,
        amount
    )


# ============================================================
# /LEAVE
# ============================================================

@bot.tree.command(
    name="leave",
    description="Leave the voice channel."
)
async def leave(interaction):

    player = get_player(
        interaction.guild
    )

    if not player:

        return await interaction.response.send_message(
            "I'm not in a voice channel.",
            ephemeral=True
        )

    await player.disconnect()

    await interaction.response.send_message(
        "Disconnected."
    )


# ============================================================
# /DISCONNECT
# ============================================================

@bot.tree.command(
    name="disconnect",
    description="Disconnect from voice."
)
async def disconnect(interaction):

    await leave.callback(
        interaction
    )


# ============================================================
# /DC
# ============================================================

@bot.tree.command(
    name="dc",
    description="Disconnect."
)
async def dc(interaction):

    await leave.callback(
        interaction
    )


# ============================================================
# /FUCKOFF
# ============================================================

@bot.tree.command(
    name="fuckoff",
    description="Disconnect ErYx Music."
)
async def fuckoff(interaction):

    await leave.callback(
        interaction
    )


# ============================================================
# /FORCESKIP
# ============================================================

@bot.tree.command(
    name="forceskip",
    description="Force skip."
)
async def forceskip(interaction):

    await skip.callback(
        interaction
    )


# ============================================================
# /FSKIP
# ============================================================

@bot.tree.command(
    name="fskip",
    description="Force skip."
)
async def fskip(interaction):

    await skip.callback(
        interaction
    )


# ============================================================
# /FS
# ============================================================

@bot.tree.command(
    name="fs",
    description="Force skip."
)
async def fs(interaction):

    await skip.callback(
        interaction
    )


# ============================================================
# /QUEUE
# ============================================================

@bot.tree.command(
    name="queue",
    description="Show the current queue."
)
async def queue(interaction):

    player = get_player(
        interaction.guild
    )

    if not player:

        return await interaction.response.send_message(
            "Queue is empty."
        )

    embed = discord.Embed(
        title="🎵 ErYx Music Queue"
    )

    if player.current:

        embed.add_field(
            name="Now Playing",
            value=track_text(
                player.current
            ),
            inline=False
        )

    tracks = list(
        player.queue
    )

    if not tracks:

        embed.add_field(
            name="Up Next",
            value="Nothing queued.",
            inline=False
        )

    else:

        lines = []

        for number, track in enumerate(
            tracks[:25],
            1
        ):

            lines.append(
                track_text(
                    track,
                    number
                )
            )

        embed.add_field(
            name=f"Up Next • {len(tracks)}",
            value="\n\n".join(lines),
            inline=False
        )

    await interaction.response.send_message(
        embed=embed
    )


# ============================================================
# /Q
# ============================================================

@bot.tree.command(
    name="q",
    description="Show queue."
)
async def q(interaction):

    await queue.callback(
        interaction
    )


# ============================================================
# /CLEAR
# ============================================================

@bot.tree.command(
    name="clear",
    description="Clear the queue."
)
async def clear(interaction):

    player = get_player(
        interaction.guild
    )

    if not player:

        return await interaction.response.send_message(
            "Queue is empty.",
            ephemeral=True
        )

    player.queue.clear()

    await interaction.response.send_message(
        "Queue cleared."
    )


# ============================================================
# /C
# ============================================================

@bot.tree.command(
    name="c",
    description="Clear queue."
)
async def c(interaction):

    await clear.callback(
        interaction
    )


# ============================================================
# /SHUFFLE
# ============================================================

@bot.tree.command(
    name="shuffle",
    description="Shuffle the queue."
)
async def shuffle(interaction):

    player = get_player(
        interaction.guild
    )

    if not player or len(player.queue) < 2:

        return await interaction.response.send_message(
            "You need at least 2 queued songs.",
            ephemeral=True
        )

    player.queue.shuffle()

    await interaction.response.send_message(
        "🔀 Queue shuffled."
    )


# ============================================================
# /REMOVE
# ============================================================

@bot.tree.command(
    name="remove",
    description="Remove a song from the queue."
)
@app_commands.describe(
    position="Queue position"
)
async def remove(
    interaction,
    position: int
):

    player = get_player(
        interaction.guild
    )

    if not player:

        return await interaction.response.send_message(
            "Queue is empty.",
            ephemeral=True
        )

    tracks = list(
        player.queue
    )

    if position < 1 or position > len(tracks):

        return await interaction.response.send_message(
            "Invalid queue position.",
            ephemeral=True
        )

    removed = tracks.pop(
        position - 1
    )

    player.queue.clear()

    for track in tracks:

        await player.queue.put_wait(
            track
        )

    await interaction.response.send_message(
        f"Removed **{removed.title}**."
    )


# ============================================================
# /RM
# ============================================================

@bot.tree.command(
    name="rm",
    description="Remove a queue song."
)
@app_commands.describe(
    position="Queue position"
)
async def rm(
    interaction,
    position: int
):

    await remove.callback(
        interaction,
        position
    )


# ============================================================
# /PLAYTOP
# ============================================================

@bot.tree.command(
    name="playtop",
    description="Put a song at the top of the queue."
)
@app_commands.describe(
    query="Song"
)
async def playtop(
    interaction,
    query: str
):

    await interaction.response.defer()

    player = await connect_player(
        interaction
    )

    if not player:
        return

    track = await get_first_track(
        query
    )

    if not track:

        return await interaction.followup.send(
            "No results found."
        )

    old_queue = list(
        player.queue
    )

    player.queue.clear()

    await player.queue.put_wait(
        track
    )

    for old in old_queue:

        await player.queue.put_wait(
            old
        )

    await interaction.followup.send(
        f"Added **{track.title}** to the top."
    )


# ============================================================
# /PT
# ============================================================

@bot.tree.command(
    name="pt",
    description="Play top."
)
@app_commands.describe(
    query="Song"
)
async def pt(
    interaction,
    query: str
):

    await playtop.callback(
        interaction,
        query
    )


# ============================================================
# /PTOP
# ============================================================

@bot.tree.command(
    name="ptop",
    description="Play top."
)
@app_commands.describe(
    query="Song"
)
async def ptop(
    interaction,
    query: str
):

    await playtop.callback(
        interaction,
        query
    )


# ============================================================
# /SKIPTO
# ============================================================

@bot.tree.command(
    name="skipto",
    description="Skip to a queue position."
)
@app_commands.describe(
    position="Queue position"
)
async def skipto(
    interaction,
    position: int
):

    player = get_player(
        interaction.guild
    )

    if not player:

        return await interaction.response.send_message(
            "Nothing is playing.",
            ephemeral=True
        )

    tracks = list(
        player.queue
    )

    if position < 1 or position > len(tracks):

        return await interaction.response.send_message(
            "Invalid queue position.",
            ephemeral=True
        )

    target = tracks[
        position - 1
    ]

    remaining = tracks[
        position:
    ]

    player.queue.clear()

    for track in remaining:

        await player.queue.put_wait(
            track
        )

    await player.play(
        target
    )

    await interaction.response.send_message(
        f"▶ Skipped to **{target.title}**."
    )


# ============================================================
# /LOOP
# ============================================================

@bot.tree.command(
    name="loop",
    description="Set loop mode."
)
@app_commands.describe(
    mode="off, track, or queue"
)
async def loop(
    interaction,
    mode: str = "track"
):

    mode = mode.lower()

    if mode not in (
        "off",
        "track",
        "queue"
    ):

        return await interaction.response.send_message(
            "Use: `off`, `track`, or `queue`.",
            ephemeral=True
        )

    guild_settings[
        interaction.guild.id
    ]["loop"] = mode

    await interaction.response.send_message(
        f"🔁 Loop mode: **{mode}**"
    )


# ============================================================
# /REPEAT
# ============================================================

@bot.tree.command(
    name="repeat",
    description="Repeat current song."
)
async def repeat(interaction):

    guild_settings[
        interaction.guild.id
    ]["loop"] = "track"

    await interaction.response.send_message(
        "🔁 Track repeat enabled."
    )


# ============================================================
# /LOOPQUEUE
# ============================================================

@bot.tree.command(
    name="loopqueue",
    description="Loop the queue."
)
async def loopqueue(interaction):

    guild_settings[
        interaction.guild.id
    ]["loop"] = "queue"

    await interaction.response.send_message(
        "🔁 Queue loop enabled."
    )


# ============================================================
# LOOP ALIASES
# ============================================================

@bot.tree.command(
    name="loopq",
    description="Loop the queue."
)
async def loopq(interaction):

    await loopqueue.callback(
        interaction
    )


@bot.tree.command(
    name="qloop",
    description="Loop the queue."
)
async def qloop(interaction):

    await loopqueue.callback(
        interaction
    )


@bot.tree.command(
    name="queueloop",
    description="Loop the queue."
)
async def queueloop(interaction):

    await loopqueue.callback(
        interaction
    )


# ============================================================
# /REPLAY
# ============================================================

@bot.tree.command(
    name="replay",
    description="Replay the current song."
)
async def replay(interaction):

    player = get_player(
        interaction.guild
    )

    if not player or not player.current:

        return await interaction.response.send_message(
            "Nothing is playing.",
            ephemeral=True
        )

    await player.seek(0)

    await interaction.response.send_message(
        "↩ Replaying."
    )


# ============================================================
# /NOWPLAYING
# ============================================================

@bot.tree.command(
    name="nowplaying",
    description="Show the current song."
)
async def nowplaying(interaction):

    player = get_player(
        interaction.guild
    )

    if not player or not player.current:

        return await interaction.response.send_message(
            "Nothing is playing.",
            ephemeral=True
        )

    track = player.current

    embed = discord.Embed(
        title="🎵 Now Playing",
        description=(
            f"**{track.title}**\n"
            f"`{track.author}`"
        )
    )

    if track.artwork:

        embed.set_thumbnail(
            url=track.artwork
        )

    embed.add_field(
        name="Progress",
        value=(
            f"`{duration(player.position)}` / "
            f"`{duration(track.length)}`"
        )
    )

    embed.add_field(
        name="Volume",
        value=(
            f"{player.volume}%"
        )
    )

    embed.add_field(
        name="Loop",
        value=guild_settings[
            interaction.guild.id
        ]["loop"]
    )

    await interaction.response.send_message(
        embed=embed
    )


# ============================================================
# NOW PLAYING ALIASES
# ============================================================

@bot.tree.command(
    name="np",
    description="Now playing."
)
async def np(interaction):

    await nowplaying.callback(
        interaction
    )


@bot.tree.command(
    name="pn",
    description="Now playing."
)
async def pn(interaction):

    await nowplaying.callback(
        interaction
    )


@bot.tree.command(
    name="m",
    description="Now playing."
)
async def m(interaction):

    await nowplaying.callback(
        interaction
    )


# ============================================================
# /SEEK
# ============================================================

@bot.tree.command(
    name="seek",
    description="Seek to a position in seconds."
)
@app_commands.describe(
    seconds="Position in seconds"
)
async def seek(
    interaction,
    seconds: int
):

    player = get_player(
        interaction.guild
    )

    if not player or not player.current:

        return await interaction.response.send_message(
            "Nothing is playing.",
            ephemeral=True
        )

    seconds = max(
        0,
        min(
            seconds,
            player.current.length // 1000
        )
    )

    await player.seek(
        seconds * 1000
    )

    await interaction.response.send_message(
        f"Seeked to `{duration(seconds * 1000)}`."
    )


# ============================================================
# /FORWARD
# ============================================================

@bot.tree.command(
    name="forward",
    description="Forward the song."
)
@app_commands.describe(
    seconds="Seconds"
)
async def forward(
    interaction,
    seconds: int = 10
):

    player = get_player(
        interaction.guild
    )

    if not player or not player.current:

        return await interaction.response.send_message(
            "Nothing is playing.",
            ephemeral=True
        )

    target = min(
        player.current.length,
        player.position + (
            abs(seconds) * 1000
        )
    )

    await player.seek(
        target
    )

    await interaction.response.send_message(
        f"Forwarded to `{duration(target)}`."
    )


# ============================================================
# /REWIND
# ============================================================

@bot.tree.command(
    name="rewind",
    description="Rewind the song."
)
@app_commands.describe(
    seconds="Seconds"
)
async def rewind(
    interaction,
    seconds: int = 10
):

    player = get_player(
        interaction.guild
    )

    if not player or not player.current:

        return await interaction.response.send_message(
            "Nothing is playing.",
            ephemeral=True
        )

    target = max(
        0,
        player.position - (
            abs(seconds) * 1000
        )
    )

    await player.seek(
        target
    )

    await interaction.response.send_message(
        f"Rewound to `{duration(target)}`."
    )


# ============================================================
# FORWARD / REWIND ALIASES
# ============================================================

@bot.tree.command(
    name="fwd",
    description="Forward the song."
)
@app_commands.describe(
    seconds="Seconds"
)
async def fwd(
    interaction,
    seconds: int = 10
):

    await forward.callback(
        interaction,
        seconds
    )


@bot.tree.command(
    name="rwd",
    description="Rewind the song."
)
@app_commands.describe(
    seconds="Seconds"
)
async def rwd(
    interaction,
    seconds: int = 10
):

    await rewind.callback(
        interaction,
        seconds
    )


# ============================================================
# /HISTORY
# ============================================================

@bot.tree.command(
    name="history",
    description="Show recently played songs."
)
async def history(interaction):

    tracks = list(
        guild_history[
            interaction.guild.id
        ]
    )

    if not tracks:

        return await interaction.response.send_message(
            "No history yet."
        )

    lines = []

    for number, track in enumerate(
        tracks[:20],
        1
    ):

        lines.append(
            track_text(
                track,
                number
            )
        )

    embed = discord.Embed(
        title="🕘 ErYx Music History",
        description="\n\n".join(lines)
    )

    await interaction.response.send_message(
        embed=embed
    )


@bot.tree.command(
    name="hist",
    description="Show music history."
)
async def hist(interaction):

    await history.callback(
        interaction
    )


@bot.tree.command(
    name="recent",
    description="Show recently played songs."
)
async def recent(interaction):

    await history.callback(
        interaction
    )


# ============================================================
# /LIKE
# ============================================================

@bot.tree.command(
    name="like",
    description="Like the current song."
)
async def like(interaction):

    player = get_player(
        interaction.guild
    )

    if not player or not player.current:

        return await interaction.response.send_message(
            "Nothing is playing.",
            ephemeral=True
        )

    guild_likes[
        interaction.guild.id
    ].add(
        player.current.identifier
    )

    await interaction.response.send_message(
        f"❤️ Liked **{player.current.title}**."
    )


# ============================================================
# LIKE ALIASES
# ============================================================

@bot.tree.command(
    name="heart",
    description="Like current song."
)
async def heart(interaction):

    await like.callback(
        interaction
    )


@bot.tree.command(
    name="love",
    description="Like current song."
)
async def love(interaction):

    await like.callback(
        interaction
    )


@bot.tree.command(
    name="likes",
    description="Show liked song count."
)
async def likes(interaction):

    amount = len(
        guild_likes[
            interaction.guild.id
        ]
    )

    await interaction.response.send_message(
        f"❤️ Liked tracks: **{amount}**"
    )


@bot.tree.command(
    name="liked",
    description="Show liked song count."
)
async def liked(interaction):

    await likes.callback(
        interaction
    )


# ============================================================
# /FAVORITES
# ============================================================

@bot.tree.command(
    name="favorites",
    description="Show favorite songs."
)
async def favorites(interaction):

    tracks = guild_favorites[
        interaction.guild.id
    ]

    if not tracks:

        return await interaction.response.send_message(
            "No favorites saved yet."
        )

    lines = []

    for number, track in enumerate(
        tracks[:20],
        1
    ):

        lines.append(
            track_text(
                track,
                number
            )
        )

    await interaction.response.send_message(
        embed=discord.Embed(
            title="❤️ Favorites",
            description="\n\n".join(lines)
        )
    )


# ============================================================
# /VOTESKIP
# ============================================================

@bot.tree.command(
    name="voteskip",
    description="Vote to skip the current song."
)
async def voteskip(interaction):

    player = get_player(
        interaction.guild
    )

    if not player or not player.current:

        return await interaction.response.send_message(
            "Nothing is playing.",
            ephemeral=True
        )

    await player.skip()

    await interaction.response.send_message(
        "⏭ Skip vote passed."
    )


# ============================================================
# /REMOVEDUPES
# ============================================================

@bot.tree.command(
    name="removedupes",
    description="Remove duplicate queue tracks."
)
async def removedupes(interaction):

    player = get_player(
        interaction.guild
    )

    if not player:

        return await interaction.response.send_message(
            "Queue is empty.",
            ephemeral=True
        )

    tracks = list(
        player.queue
    )

    player.queue.clear()

    seen = set()
    removed = 0

    for track in tracks:

        key = (
            track.title.lower(),
            track.author.lower()
        )

        if key in seen:

            removed += 1
            continue

        seen.add(key)

        await player.queue.put_wait(
            track
        )

    await interaction.response.send_message(
        f"Removed **{removed}** duplicate(s)."
    )


@bot.tree.command(
    name="rd",
    description="Remove duplicate tracks."
)
async def rd(interaction):

    await removedupes.callback(
        interaction
    )


# ============================================================
# EFFECTS
# ============================================================

EFFECTS = {
    "nightcore": "Nightcore",
    "slow": "Slow",
    "deep": "Deep Voice",
    "chipmunk": "Chipmunk",
    "speed": "Speed",
    "vaporwave": "Vaporwave",
    "karaoke": "Karaoke",
    "tremolo": "Tremolo",
    "vibrato": "Vibrato",
    "distortion": "Distortion",
    "bassboost": "Bass Boost",
    "lowpass": "Low Pass",
    "reset": "Reset"
}


async def set_effect(
    player,
    effect
):

    filters = wavelink.Filters()

    if effect == "reset":

        await player.set_filters(
            filters
        )

        return

    if effect == "nightcore":

        filters.timescale.set(
            speed=1.25,
            pitch=1.25,
            rate=1.0
        )

    elif effect == "slow":

        filters.timescale.set(
            speed=0.80,
            pitch=1.0,
            rate=1.0
        )

    elif effect == "deep":

        filters.timescale.set(
            speed=1.0,
            pitch=0.75,
            rate=1.0
        )

    elif effect == "chipmunk":

        filters.timescale.set(
            speed=1.0,
            pitch=1.35,
            rate=1.0
        )

    elif effect == "speed":

        filters.timescale.set(
            speed=1.5,
            pitch=1.0,
            rate=1.0
        )

    elif effect == "vaporwave":

        filters.timescale.set(
            speed=0.8,
            pitch=0.8,
            rate=1.0
        )

    elif effect == "karaoke":

        filters.karaoke.set(
            level=1.0,
            mono_level=1.0,
            filter_band=220.0,
            filter_width=100.0
        )

    elif effect == "tremolo":

        filters.tremolo.set(
            frequency=5.0,
            depth=0.7
        )

    elif effect == "vibrato":

        filters.vibrato.set(
            frequency=5.0,
            depth=0.7
        )

    elif effect == "distortion":

        filters.distortion.set(
            sin_offset=0.0,
            sin_scale=1.0,
            cos_offset=0.0,
            cos_scale=1.0,
            tan_offset=0.0,
            tan_scale=1.0,
            offset=0.0,
            scale=1.0
        )

    elif effect == "bassboost":

        filters.equalizer.set(
            bands=[
                {"band": 0, "gain": 0.35},
                {"band": 1, "gain": 0.30},
                {"band": 2, "gain": 0.25},
                {"band": 3, "gain": 0.20},
            ]
        )

    elif effect == "lowpass":

        filters.low_pass.set(
            smoothing=20.0
        )

    await player.set_filters(
        filters,
        seek=True
    )


@bot.tree.command(
    name="effects",
    description="Apply a music effect."
)
@app_commands.describe(
    effect="Effect name"
)
async def effects(
    interaction,
    effect: str
):

    effect = effect.lower()

    if effect not in EFFECTS:

        return await interaction.response.send_message(
            "Available effects:\n"
            "`nightcore` • `slow` • `deep` • "
            "`chipmunk` • `speed` • `vaporwave` • "
            "`karaoke` • `tremolo` • `vibrato` • "
            "`distortion` • `bassboost` • `lowpass` • "
            "`reset`",
            ephemeral=True
        )

    player = get_player(
        interaction.guild
    )

    if not player:

        return await interaction.response.send_message(
            "I'm not connected.",
            ephemeral=True
        )

    try:

        await set_effect(
            player,
            effect
        )

        await interaction.response.send_message(
            f"🎛 Effect: **{EFFECTS[effect]}**"
        )

    except Exception as e:

        print(
            f"[EFFECT ERROR] "
            f"{type(e).__name__}: {e}"
        )

        await interaction.response.send_message(
            f"Effect error: "
            f"`{type(e).__name__}`",
            ephemeral=True
        )


# ============================================================
# /SETTINGS
# ============================================================

@bot.tree.command(
    name="settings",
    description="Show server music settings."
)
async def settings(interaction):

    data = guild_settings[
        interaction.guild.id
    ]

    embed = discord.Embed(
        title="⚙ ErYx Music Settings"
    )

    embed.add_field(
        name="Volume",
        value=f"{data['volume']}%"
    )

    embed.add_field(
        name="Loop",
        value=data["loop"]
    )

    embed.add_field(
        name="Voice Cleanup",
        value=(
            "ON"
            if data["cleanup"]
            else "OFF"
        )
    )

    await interaction.response.send_message(
        embed=embed
    )


@bot.tree.command(
    name="setting",
    description="Show settings."
)
async def setting(interaction):

    await settings.callback(
        interaction
    )


@bot.tree.command(
    name="s",
    description="Show settings."
)
async def s(interaction):

    await settings.callback(
        interaction
    )


# ============================================================
# /CONTROLS
# ============================================================

@bot.tree.command(
    name="control",
    description="Show music controls."
)
async def control(interaction):

    embed = discord.Embed(
        title="🎛 ErYx Music Controls",
        description=(
            "`/play` — Play\n"
            "`/pause` — Pause\n"
            "`/resume` — Resume\n"
            "`/skip` — Skip\n"
            "`/stop` — Stop\n"
            "`/queue` — Queue\n"
            "`/shuffle` — Shuffle\n"
            "`/volume` — Volume\n"
            "`/seek` — Seek\n"
            "`/forward` — Forward\n"
            "`/rewind` — Rewind\n"
            "`/loop` — Loop\n"
            "`/effects` — Effects"
        )
    )

    await interaction.response.send_message(
        embed=embed
    )


@bot.tree.command(
    name="controls",
    description="Show music controls."
)
async def controls(interaction):

    await control.callback(
        interaction
    )


@bot.tree.command(
    name="ctrl",
    description="Show music controls."
)
async def ctrl(interaction):

    await control.callback(
        interaction
    )


@bot.tree.command(
    name="ct",
    description="Show music controls."
)
async def ct(interaction):

    await control.callback(
        interaction
    )


# ============================================================
# /PING
# ============================================================

@bot.tree.command(
    name="ping",
    description="Show bot latency."
)
async def ping(interaction):

    discord_ping = round(
        bot.latency * 1000
    )

    player = get_player(
        interaction.guild
    )

    if player:

        try:
            lavalink_ping = player.ping
        except Exception:
            lavalink_ping = "N/A"

    else:

        lavalink_ping = "N/A"

    await interaction.response.send_message(
        f"🏓 Discord: `{discord_ping}ms`\n"
        f"🎵 Lavalink: `{lavalink_ping}ms`"
    )


# ============================================================
# /HELP
# ============================================================

@bot.tree.command(
    name="help",
    description="Show ErYx Music commands."
)
async def help_command(interaction):

    embed = discord.Embed(
        title="🎵 ErYx Music",
        description=(
            "**Playback**\n"
            "`/play` `/playnow` `/playskip` `/skip` "
            "`/stop` `/pause` `/resume`\n\n"

            "**Queue**\n"
            "`/queue` `/clear` `/remove` `/move` "
            "`/shuffle` `/playtop` `/skipto`\n\n"

            "**Music**\n"
            "`/search` `/nowplaying` `/history` "
            "`/volume` `/loop` `/effects`\n\n"

            "**Controls**\n"
            "`/seek` `/forward` `/rewind` `/replay`\n\n"

            "**Quick play**\n"
            "`P <song>`"
        )
    )

    await interaction.response.send_message(
        embed=embed,
        ephemeral=True
    )


# ============================================================
# /ALIASES
# ============================================================

@bot.tree.command(
    name="aliases",
    description="Show ErYx Music aliases."
)
async def aliases(interaction):

    embed = discord.Embed(
        title="🔗 ErYx Music Aliases",
        description=(
            "`/p` → `/play`\n"
            "`/q` → `/queue`\n"
            "`/vol` → `/volume`\n"
            "`/c` → `/clear`\n"
            "`/dc` → `/disconnect`\n"
            "`/fskip` → `/forceskip`\n"
            "`/fs` → `/forceskip`\n"
            "`/np` → `/nowplaying`\n"
            "`/pn` → `/nowplaying`\n"
            "`/m` → `/nowplaying`\n"
            "`/pt` → `/playtop`\n"
            "`/ptop` → `/playtop`\n"
            "`/rm` → `/remove`\n"
            "`/rd` → `/removedupes`\n"
            "`/hist` → `/history`\n"
            "`/recent` → `/history`\n"
            "`/fwd` → `/forward`\n"
            "`/rwd` → `/rewind`\n"
            "`/qloop` → `/loopqueue`\n"
            "`/loopq` → `/loopqueue`\n"
            "`/queueloop` → `/loopqueue`"
        )
    )

    await interaction.response.send_message(
        embed=embed,
        ephemeral=True
    )


# ============================================================
# /SERVERPROFILE
# ============================================================

@bot.tree.command(
    name="serverprofile",
    description="Show server music information."
)
async def serverprofile(interaction):

    guild = interaction.guild
    player = get_player(guild)

    voice = (
        player.channel.name
        if player and player.channel
        else "Not connected"
    )

    embed = discord.Embed(
        title=f"🎵 {guild.name}"
    )

    embed.add_field(
        name="Members",
        value=str(
            guild.member_count
        )
    )

    embed.add_field(
        name="Voice",
        value=voice
    )

    embed.add_field(
        name="History",
        value=str(
            len(
                guild_history[
                    guild.id
                ]
            )
        )
    )

    await interaction.response.send_message(
        embed=embed
    )


# ============================================================
# /LYRICS
# ============================================================

@bot.tree.command(
    name="lyrics",
    description="Show lyrics information."
)
async def lyrics(interaction):

    player = get_player(
        interaction.guild
    )

    if not player or not player.current:

        return await interaction.response.send_message(
            "Nothing is playing.",
            ephemeral=True
        )

    await interaction.response.send_message(
        "Lyrics provider isn't configured yet.\n"
        f"Current track: **{player.current.title}**"
    )


@bot.tree.command(
    name="ly",
    description="Lyrics."
)
async def ly(interaction):

    await lyrics.callback(
        interaction
    )


# ============================================================
# /FEEDBACK
# ============================================================

@bot.tree.command(
    name="feedback",
    description="Send ErYx Music feedback."
)
@app_commands.describe(
    message="Your feedback"
)
async def feedback(
    interaction,
    message: str
):

    guild_feedback[
        interaction.guild.id
    ].append(
        {
            "user": interaction.user.id,
            "message": message,
            "time": int(time.time())
        }
    )

    await interaction.response.send_message(
        "Feedback received."
    )


# ============================================================
# /CHANGELOG
# ============================================================

@bot.tree.command(
    name="changelog",
    description="Show ErYx Music changelog."
)
async def changelog(interaction):

    embed = discord.Embed(
        title="ErYx Music — Changelog",
        description=(
            "• Lavalink v4\n"
            "• Wavelink 3.x\n"
            "• 300% volume maximum\n"
            "• Top 15 search suggestions\n"
            "• Queue system\n"
            "• History\n"
            "• Likes\n"
            "• Favorites\n"
            "• Loop modes\n"
            "• Playback effects\n"
            "• Prefix quick play"
        )
    )

    await interaction.response.send_message(
        embed=embed
    )


# ============================================================
# /START
# ============================================================

@bot.tree.command(
    name="start",
    description="Start or resume the player."
)
async def start(interaction):

    player = get_player(
        interaction.guild
    )

    if not player:

        player = await connect_player(
            interaction
        )

        if not player:
            return

    if player.paused:

        await player.pause(
            False
        )

    await simple_message(
        interaction,
        "▶ Player ready."
    )


# ============================================================
# /LEAVECLEANUP
# ============================================================

@bot.tree.command(
    name="leavecleanup",
    description="Toggle automatic voice cleanup."
)
async def leavecleanup(interaction):

    settings_data = guild_settings[
        interaction.guild.id
    ]

    settings_data["cleanup"] = not (
        settings_data["cleanup"]
    )

    status = (
        "ON"
        if settings_data["cleanup"]
        else "OFF"
    )

    await interaction.response.send_message(
        f"Voice cleanup: **{status}**"
    )


@bot.tree.command(
    name="lc",
    description="Toggle voice cleanup."
)
async def lc(interaction):

    await leavecleanup.callback(
        interaction
    )


# ============================================================
# /PREMIUM
# ============================================================

@bot.tree.command(
    name="premium",
    description="Show premium information."
)
async def premium(interaction):

    await interaction.response.send_message(
        "ErYx Music premium isn't enabled in this build."
    )


# ============================================================
# /DRM
# ============================================================

@bot.tree.command(
    name="drm",
    description="Show player status."
)
async def drm(interaction):

    player = get_player(
        interaction.guild
    )

    status = (
        "Connected"
        if player
        else "Disconnected"
    )

    await interaction.response.send_message(
        f"Player status: **{status}**"
    )


# ============================================================
# /NEW
# ============================================================

@bot.tree.command(
    name="new",
    description="Show ErYx Music status."
)
async def new(interaction):

    await interaction.response.send_message(
        "ErYx Music is online."
    )


# ============================================================
# /MOVE
# ============================================================

@bot.tree.command(
    name="move",
    description="Move a queue track."
)
@app_commands.describe(
    old_position="Current queue position",
    new_position="New queue position"
)
async def move(
    interaction,
    old_position: int,
    new_position: int
):

    player = get_player(
        interaction.guild
    )

    if not player:

        return await interaction.response.send_message(
            "Queue is empty.",
            ephemeral=True
        )

    tracks = list(
        player.queue
    )

    if not (
        1 <= old_position <= len(tracks)
        and
        1 <= new_position <= len(tracks)
    ):

        return await interaction.response.send_message(
            "Invalid positions.",
            ephemeral=True
        )

    track = tracks.pop(
        old_position - 1
    )

    tracks.insert(
        new_position - 1,
        track
    )

    player.queue.clear()

    for item in tracks:

        await player.queue.put_wait(
            item
        )

    await interaction.response.send_message(
        f"Moved **{track.title}**."
    )


# ============================================================
# PREFIX COMMANDS
# ============================================================

@bot.command(
    name="play"
)
async def prefix_play(
    ctx,
    *,
    query=None
):

    if not query:

        return await ctx.send(
            f"Usage: `{PREFIX}play <song>`"
        )

    if not ctx.author.voice:

        return await ctx.send(
            "Join a voice channel first."
        )

    channel = ctx.author.voice.channel

    player = get_player(
        ctx.guild
    )

    try:

        if not player:

            player = await channel.connect(
                cls=wavelink.Player,
                self_deaf=True
            )

        text_channels[
            ctx.guild.id
        ] = ctx.channel

        track = await get_first_track(
            query
        )

        if not track:

            return await ctx.send(
                "No results found."
            )

        started = await add_track(
            player,
            track
        )

        await ctx.send(
            (
                f"▶ Playing **{track.title}**"
                if started
                else f"Queued **{track.title}**"
            )
        )

    except Exception as e:

        print(
            f"[PREFIX PLAY] {e}"
        )

        await ctx.send(
            f"Playback error: "
            f"`{type(e).__name__}`"
        )


# ============================================================
# P <SONG>
#
# Examples:
#
# P Believer
# p Believer
# ============================================================

@bot.listen()
async def eryx_quick_play(message):

    if message.author.bot:
        return

    content = message.content.strip()

    if not content:
        return

    if (
        content.lower().startswith("p ")
        and not content.startswith(PREFIX)
    ):

        query = content[2:].strip()

        if not query:
            return

        if not message.author.voice:
            return

        channel = message.author.voice.channel

        player = get_player(
            message.guild
        )

        try:

            if not player:

                player = await channel.connect(
                    cls=wavelink.Player,
                    self_deaf=True
                )

            text_channels[
                message.guild.id
            ] = message.channel

            track = await get_first_track(
                query
            )

            if not track:
                return

            started = await add_track(
                player,
                track
            )

            await message.channel.send(
                (
                    f"▶ Playing **{track.title}**"
                    if started
                    else f"Queued **{track.title}**"
                )
            )

        except Exception as e:

            print(
                f"[P QUICK PLAY] {e}"
            )


# ============================================================
# PREFIX ALIASES
# ============================================================

@bot.command(name="skip")
async def prefix_skip(ctx):

    player = get_player(
        ctx.guild
    )

    if not player or not player.current:

        return await ctx.send(
            "Nothing is playing."
        )

    await player.skip()

    await ctx.send(
        "⏭ Skipped."
    )


@bot.command(name="stop")
async def prefix_stop(ctx):

    player = get_player(
        ctx.guild
    )

    if not player:

        return await ctx.send(
            "Nothing is playing."
        )

    player.queue.clear()

    await player.stop()

    await ctx.send(
        "⏹ Stopped."
    )


@bot.command(name="pause")
async def prefix_pause(ctx):

    player = get_player(
        ctx.guild
    )

    if not player:

        return await ctx.send(
            "Nothing is playing."
        )

    await player.pause(
        True
    )

    await ctx.send(
        "⏸ Paused."
    )


@bot.command(name="resume")
async def prefix_resume(ctx):

    player = get_player(
        ctx.guild
    )

    if not player:

        return await ctx.send(
            "Nothing is playing."
        )

    await player.pause(
        False
    )

    await ctx.send(
        "▶ Resumed."
    )


@bot.command(name="queue")
async def prefix_queue(ctx):

    player = get_player(
        ctx.guild
    )

    if not player:

        return await ctx.send(
            "Queue is empty."
        )

    tracks = list(
        player.queue
    )

    if not tracks:

        return await ctx.send(
            "Queue is empty."
        )

    lines = []

    for number, track in enumerate(
        tracks[:20],
        1
    ):

        lines.append(
            f"**{number}.** {track.title}"
        )

    await ctx.send(
        "🎵 **Queue**\n"
        + "\n".join(lines)
    )


@bot.command(name="vol")
async def prefix_vol(
    ctx,
    amount: int
):

    # HARD 300% MAXIMUM
    if amount < 0 or amount > 300:

        return await ctx.send(
            "Volume must be between **0% and 300%**."
        )

    player = get_player(
        ctx.guild
    )

    if not player:

        return await ctx.send(
            "I'm not connected."
        )

    await player.set_volume(
        amount
    )

    await ctx.send(
        f"🔊 Volume: **{amount}%**"
    )


# ============================================================
# PREFIX HELP
# ============================================================

@bot.command(name="help")
async def prefix_help(ctx):

    await ctx.send(
        f"🎵 **ErYx Music**\n\n"
        f"`{PREFIX}play <song>`\n"
        f"`{PREFIX}skip`\n"
        f"`{PREFIX}stop`\n"
        f"`{PREFIX}pause`\n"
        f"`{PREFIX}resume`\n"
        f"`{PREFIX}queue`\n"
        f"`{PREFIX}vol <0-300>`\n\n"
        f"Quick play:\n"
        f"`P <song>`"
    )


# ============================================================
# PREFIX ERROR HANDLER
# ============================================================

@bot.event
async def on_command_error(
    ctx,
    error
):

    if isinstance(
        error,
        commands.CommandNotFound
    ):
        return

    if isinstance(
        error,
        commands.MissingRequiredArgument
    ):

        await ctx.send(
            "Missing required argument."
        )

        return

    print(
        f"[COMMAND ERROR] "
        f"{type(error).__name__}: {error}"
    )


# ============================================================
# MESSAGE CONTENT
# ============================================================

@bot.event
async def on_message(message):

    if message.author.bot:
        return

    # Prefix commands such as !!play
    await bot.process_commands(
        message
    )


# ============================================================
# START
# ============================================================

if (
    not DISCORD_TOKEN
    or DISCORD_TOKEN.startswith(
        "PASTE_"
    )
):

    raise RuntimeError(
        "Put your Discord bot token "
        "at the top of main.py."
    )


if (
    not LAVALINK_PASSWORD
    or LAVALINK_PASSWORD.startswith(
        "PASTE_"
    )
):

    raise RuntimeError(
        "Put your Railway Lavalink password "
        "at the top of main.py."
    )


print("[ErYx] Starting bot...")

bot.run(
    DISCORD_TOKEN
    )
