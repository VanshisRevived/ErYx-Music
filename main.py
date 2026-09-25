import asyncio
import os
from collections import deque

import discord
from discord import app_commands
from discord.ext import commands
import wavelink


# ============================================================
# CONFIG
# ============================================================

DISCORD_TOKEN = "YOUR_DISCORD_BOT_TOKEN"

LAVALINK_HOST = "lavalink-2026-production-07a0.up.railway.app"
LAVALINK_PORT = 443
LAVALINK_PASSWORD = "YOUR_LAVALINK_PASSWORD"
LAVALINK_SECURE = True

PREFIX = "!!"
MAX_VOLUME = 300


# ============================================================
# INTENTS
# ============================================================

intents = discord.Intents.default()
intents.guilds = True
intents.members = True
intents.voice_states = True
intents.message_content = True


# ============================================================
# MUSIC BOT
# ============================================================

class ErYxMusic(commands.Bot):

    def __init__(self):
        super().__init__(
            command_prefix=PREFIX,
            intents=intents,
            help_command=None
        )

        self.history = {}
        self.search_cache = {}
        self.favorites = {}
        self.loops = {}
        self.effects = {}
        self.start_times = {}

    async def setup_hook(self):

        print("[ErYx] Connecting to Lavalink...")

        try:
            uri = (
                f"https://{LAVALINK_HOST}:{LAVALINK_PORT}"
                if LAVALINK_SECURE
                else f"http://{LAVALINK_HOST}:{LAVALINK_PORT}"
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

            print("[ErYx] Lavalink connected.")

        except Exception as e:
            print(f"[ErYx] Lavalink connection error: {type(e).__name__}: {e}")

        await self.tree.sync()
        print("[ErYx] Slash commands synced.")

    async def on_ready(self):
        print("================================")
        print(f"ErYx Music online")
        print(f"Bot: {self.user}")
        print(f"Guilds: {len(self.guilds)}")
        print("================================")

        await self.change_presence(
            activity=discord.Activity(
                type=discord.ActivityType.listening,
                name="/play | ErYx Music"
            )
        )


bot = ErYxMusic()


# ============================================================
# HELPERS
# ============================================================

def get_player(guild: discord.Guild):
    return guild.voice_client


async def ensure_voice(interaction: discord.Interaction):

    if not interaction.guild:
        return None

    user_channel = getattr(interaction.user.voice, "channel", None)

    if not user_channel:
        await interaction.followup.send(
            "❌ You need to be in a voice channel.",
            ephemeral=True
        )
        return None

    player = interaction.guild.voice_client

    if player:
        if player.channel != user_channel:
            try:
                await player.move_to(user_channel)
            except Exception:
                pass

        return player

    try:
        player = await user_channel.connect(cls=wavelink.Player)
        return player

    except Exception as e:
        await interaction.followup.send(
            f"❌ Couldn't join the voice channel.\n`{type(e).__name__}: {e}`",
            ephemeral=True
        )
        return None


async def search_track(query: str):

    try:
        tracks = await wavelink.Playable.search(
            query,
            source=wavelink.TrackSource.YouTubeMusic
        )

        if tracks:
            return tracks

    except Exception as e:
        print(f"[Search] YouTube Music error: {e}")

    try:
        tracks = await wavelink.Playable.search(query)

        if tracks:
            return tracks

    except Exception as e:
        print(f"[Search] fallback error: {e}")

    return []


async def play_track(
    interaction: discord.Interaction,
    query: str,
    force: bool = False
):

    await interaction.response.defer()

    player = await ensure_voice(interaction)

    if not player:
        return

    tracks = await search_track(query)

    if not tracks:
        await interaction.followup.send(
            "❌ No results found."
        )
        return

    track = tracks[0]

    if not force and player.playing:
        player.queue.put(track)

        await interaction.followup.send(
            f"➕ Added to queue: **{track.title}**"
        )
        return

    try:
        await player.play(track)

        player.queue.mode = wavelink.QueueMode.normal

        await interaction.followup.send(
            f"▶️ Now playing: **{track.title}**"
        )

    except Exception as e:
        print(f"[Play] Error: {type(e).__name__}: {e}")

        await interaction.followup.send(
            f"❌ Playback error: `{type(e).__name__}: {e}`"
        )


def add_history(guild_id: int, track):

    if guild_id not in bot.history:
        bot.history[guild_id] = deque(maxlen=50)

    bot.history[guild_id].appendleft(track)


# ============================================================
# WAVELINK EVENTS
# ============================================================

@bot.listen()
async def on_wavelink_track_start(payload):

    player = payload.player
    track = payload.track

    if not player.guild:
        return

    guild_id = player.guild.id

    print(
        f"[Music] {player.guild.name}: "
        f"Playing {track.title}"
    )

    bot.start_times[guild_id] = asyncio.get_event_loop().time()

    try:
        await player.guild.change_voice_state(
            channel=player.channel,
            self_deaf=True
        )
    except Exception:
        pass


@bot.listen()
async def on_wavelink_track_end(payload):

    player = payload.player
    track = payload.track

    if not player.guild:
        return

    guild_id = player.guild.id

    add_history(guild_id, track)

    loop_mode = bot.loops.get(guild_id, "off")

    if loop_mode == "track":

        try:
            await player.play(track)
            return
        except Exception as e:
            print(f"[Loop] {e}")

    if loop_mode == "queue":
        try:
            player.queue.put(track)
        except Exception:
            pass


@bot.listen()
async def on_wavelink_track_exception(payload):

    print(
        f"[Lavalink] Track exception: "
        f"{type(payload.exception).__name__}: "
        f"{payload.exception}"
    )


@bot.listen()
async def on_wavelink_track_stuck(payload):

    print(
        f"[Lavalink] Track stuck: "
        f"{payload.track.title}"
    )


# ============================================================
# /PLAY
# ============================================================

@bot.tree.command(name="play", description="Play a song")
@app_commands.describe(query="Song name or URL")
async def play(
    interaction: discord.Interaction,
    query: str
):
    await play_track(interaction, query)


# ============================================================
# /P
# ============================================================

@bot.tree.command(name="p", description="Play a song")
@app_commands.describe(query="Song name or URL")
async def p(
    interaction: discord.Interaction,
    query: str
):
    await play_track(interaction, query)


# ============================================================
# /PLAYNOW
# ============================================================

@bot.tree.command(name="playnow", description="Immediately play a song")
@app_commands.describe(query="Song name or URL")
async def playnow(
    interaction: discord.Interaction,
    query: str
):
    await play_track(interaction, query, True)


# ============================================================
# /PLAYSКIP
# ============================================================

@bot.tree.command(name="playskip", description="Play a song immediately")
@app_commands.describe(query="Song name or URL")
async def playskip(
    interaction: discord.Interaction,
    query: str
):
    await play_track(interaction, query, True)


# ============================================================
# /PLAYTOP
# ============================================================

@bot.tree.command(name="playtop", description="Add a song to the front")
@app_commands.describe(query="Song name or URL")
async def playtop(
    interaction: discord.Interaction,
    query: str
):

    await interaction.response.defer()

    player = await ensure_voice(interaction)

    if not player:
        return

    tracks = await search_track(query)

    if not tracks:
        await interaction.followup.send("❌ No results found.")
        return

    track = tracks[0]

    try:
        player.queue.put_at(0, track)

        await interaction.followup.send(
            f"⬆️ Added to top: **{track.title}**"
        )

    except Exception as e:
        await interaction.followup.send(
            f"❌ Could not add track: `{e}`"
        )


# ============================================================
# /SEARCH
# ============================================================

@bot.tree.command(name="search", description="Search for music")
@app_commands.describe(query="What do you want to search?")
async def search(
    interaction: discord.Interaction,
    query: str
):

    await interaction.response.defer()

    tracks = await search_track(query)

    if not tracks:
        await interaction.followup.send(
            "❌ Nothing found."
        )
        return

    tracks = tracks[:15]

    bot.search_cache[interaction.user.id] = tracks

    embed = discord.Embed(
        title="🔎 ErYx Music Search",
        description=f"Results for **{query}**",
        color=discord.Color.blurple()
    )

    for i, track in enumerate(tracks, 1):

        duration = getattr(track, "length", 0)

        if duration:
            seconds = duration // 1000
            minutes = seconds // 60
            seconds %= 60
            time = f"{minutes}:{seconds:02d}"
        else:
            time = "LIVE"

        embed.add_field(
            name=f"{i}. {track.title[:80]}",
            value=f"`{time}`",
            inline=False
        )

    await interaction.followup.send(embed=embed)


# ============================================================
# /SKIP
# ============================================================

@bot.tree.command(name="skip", description="Skip current song")
async def skip(interaction: discord.Interaction):

    await interaction.response.defer()

    player = get_player(interaction.guild)

    if not player:
        await interaction.followup.send("❌ I'm not in a voice channel.")
        return

    if not player.playing:
        await interaction.followup.send("❌ Nothing is playing.")
        return

    await player.skip()

    await interaction.followup.send("⏭️ Skipped.")


# ============================================================
# SKIP ALIASES
# ============================================================

@bot.tree.command(name="fskip", description="Force skip")
async def fskip(interaction: discord.Interaction):
    await skip(interaction)


@bot.tree.command(name="forceskip", description="Force skip")
async def forceskip(interaction: discord.Interaction):
    await skip(interaction)


@bot.tree.command(name="fs", description="Force skip")
async def fs(interaction: discord.Interaction):
    await skip(interaction)


@bot.tree.command(name="pskip", description="Skip current song")
async def pskip(interaction: discord.Interaction):
    await skip(interaction)


@bot.tree.command(name="vs", description="Skip current song")
async def vs(interaction: discord.Interaction):
    await skip(interaction)


# ============================================================
# /STOP
# ============================================================

@bot.tree.command(name="stop", description="Stop music and clear queue")
async def stop(interaction: discord.Interaction):

    await interaction.response.defer()

    player = get_player(interaction.guild)

    if not player:
        await interaction.followup.send("❌ Not connected.")
        return

    try:
        player.queue.clear()
    except Exception:
        pass

    try:
        await player.stop()
    except Exception:
        pass

    await interaction.followup.send("⏹️ Stopped.")


# ============================================================
# /PAUSE
# ============================================================

@bot.tree.command(name="pause", description="Pause music")
async def pause(interaction: discord.Interaction):

    player = get_player(interaction.guild)

    if not player:
        await interaction.response.send_message(
            "❌ Not connected."
        )
        return

    await player.pause(True)

    await interaction.response.send_message(
        "⏸️ Paused."
    )


# ============================================================
# /RESUME
# ============================================================

@bot.tree.command(name="resume", description="Resume music")
async def resume(interaction: discord.Interaction):

    player = get_player(interaction.guild)

    if not player:
        await interaction.response.send_message(
            "❌ Not connected."
        )
        return

    await player.pause(False)

    await interaction.response.send_message(
        "▶️ Resumed."
    )


# ============================================================
# /VOLUME
# ============================================================

@bot.tree.command(name="volume", description="Set volume")
@app_commands.describe(volume="0-300")
@app_commands.Range[int, 0, 300]
async def volume(
    interaction: discord.Interaction,
    volume: int
):

    player = get_player(interaction.guild)

    if not player:
        await interaction.response.send_message(
            "❌ Not connected."
        )
        return

    volume = max(0, min(volume, MAX_VOLUME))

    await player.set_volume(volume)

    await interaction.response.send_message(
        f"🔊 Volume set to **{volume}%**."
    )


@bot.tree.command(name="vol", description="Set volume")
@app_commands.describe(volume="0-300")
@app_commands.Range[int, 0, 300]
async def vol(
    interaction: discord.Interaction,
    volume: int
):
    await volume_command(interaction, volume)


async def volume_command(interaction, volume):

    player = get_player(interaction.guild)

    if not player:
        await interaction.response.send_message(
            "❌ Not connected."
        )
        return

    volume = max(0, min(volume, MAX_VOLUME))

    await player.set_volume(volume)

    await interaction.response.send_message(
        f"🔊 Volume: **{volume}%**"
    )


# ============================================================
# /QUEUE
# ============================================================

@bot.tree.command(name="queue", description="Show queue")
async def queue(interaction: discord.Interaction):

    player = get_player(interaction.guild)

    if not player:
        await interaction.response.send_message(
            "❌ Not connected."
        )
        return

    embed = discord.Embed(
        title="🎵 ErYx Queue",
        color=discord.Color.blurple()
    )

    current = player.current

    if current:
        embed.add_field(
            name="Now Playing",
            value=f"▶️ **{current.title}**",
            inline=False
        )

    if not player.queue:
        embed.add_field(
            name="Queue",
            value="Queue is empty.",
            inline=False
        )

    else:

        items = list(player.queue)[:20]

        text = ""

        for i, track in enumerate(items, 1):
            text += f"`{i}.` {track.title[:70]}\n"

        embed.add_field(
            name=f"Up Next ({len(player.queue)})",
            value=text,
            inline=False
        )

    await interaction.response.send_message(
        embed=embed
    )


@bot.tree.command(name="q", description="Show queue")
async def q(interaction: discord.Interaction):
    await queue(interaction)


# ============================================================
# /NOWPLAYING
# ============================================================

@bot.tree.command(
    name="nowplaying",
    description="Show current song"
)
async def nowplaying(interaction: discord.Interaction):

    player = get_player(interaction.guild)

    if not player or not player.current:
        await interaction.response.send_message(
            "❌ Nothing is playing."
        )
        return

    track = player.current

    embed = discord.Embed(
        title="🎵 Now Playing",
        description=f"**{track.title}**",
        color=discord.Color.blurple()
    )

    if getattr(track, "author", None):
        embed.add_field(
            name="Artist",
            value=track.author,
            inline=True
        )

    if getattr(track, "length", None):
        seconds = track.length // 1000
        mins = seconds // 60
        secs = seconds % 60

        embed.add_field(
            name="Duration",
            value=f"{mins}:{secs:02d}",
            inline=True
        )

    await interaction.response.send_message(
        embed=embed
    )


@bot.tree.command(name="np", description="Now playing")
async def np(interaction: discord.Interaction):
    await nowplaying(interaction)


@bot.tree.command(name="pn", description="Now playing")
async def pn(interaction: discord.Interaction):
    await nowplaying(interaction)


# ============================================================
# /LOOP
# ============================================================

@bot.tree.command(name="loop", description="Set loop mode")
@app_commands.describe(mode="off, track or queue")
@app_commands.choices(
    mode=[
        app_commands.Choice(name="Off", value="off"),
        app_commands.Choice(name="Track", value="track"),
        app_commands.Choice(name="Queue", value="queue"),
    ]
)
async def loop(
    interaction: discord.Interaction,
    mode: app_commands.Choice[str]
):

    bot.loops[interaction.guild.id] = mode.value

    await interaction.response.send_message(
        f"🔁 Loop mode: **{mode.value}**"
    )


@bot.tree.command(name="repeat", description="Set repeat mode")
@app_commands.describe(mode="off, track or queue")
async def repeat(
    interaction: discord.Interaction,
    mode: str
):

    mode = mode.lower()

    if mode not in ("off", "track", "queue"):
        await interaction.response.send_message(
            "❌ Use `off`, `track`, or `queue`."
        )
        return

    bot.loops[interaction.guild.id] = mode

    await interaction.response.send_message(
        f"🔁 Repeat: **{mode}**"
    )


@bot.tree.command(name="loopq", description="Toggle queue loop")
async def loopq(interaction: discord.Interaction):

    guild_id = interaction.guild.id

    current = bot.loops.get(guild_id, "off")

    new = "off" if current == "queue" else "queue"

    bot.loops[guild_id] = new

    await interaction.response.send_message(
        f"🔁 Queue loop: **{new}**"
    )


@bot.tree.command(name="loopqueue", description="Toggle queue loop")
async def loopqueue(interaction: discord.Interaction):
    await loopq(interaction)


@bot.tree.command(name="queueloop", description="Toggle queue loop")
async def queueloop(interaction: discord.Interaction):
    await loopq(interaction)


@bot.tree.command(name="qloop", description="Toggle queue loop")
async def qloop(interaction: discord.Interaction):
    await loopq(interaction)


# ============================================================
# /SHUFFLE
# ============================================================

@bot.tree.command(name="shuffle", description="Shuffle queue")
async def shuffle(interaction: discord.Interaction):

    player = get_player(interaction.guild)

    if not player:
        await interaction.response.send_message(
            "❌ Not connected."
        )
        return

    try:
        player.queue.shuffle()
        await interaction.response.send_message(
            "🔀 Queue shuffled."
        )

    except Exception as e:
        await interaction.response.send_message(
            f"❌ Shuffle failed: `{e}`"
        )


# ============================================================
# /CLEAR
# ============================================================

@bot.tree.command(name="clear", description="Clear queue")
async def clear(interaction: discord.Interaction):

    player = get_player(interaction.guild)

    if not player:
        await interaction.response.send_message(
            "❌ Not connected."
        )
        return

    player.queue.clear()

    await interaction.response.send_message(
        "🗑️ Queue cleared."
    )


@bot.tree.command(name="c", description="Clear queue")
async def c(interaction: discord.Interaction):
    await clear(interaction)


# ============================================================
# /REMOVE
# ============================================================

@bot.tree.command(name="remove", description="Remove a queue item")
@app_commands.describe(position="Queue position")
async def remove(
    interaction: discord.Interaction,
    position: int
):

    player = get_player(interaction.guild)

    if not player:
        await interaction.response.send_message(
            "❌ Not connected."
        )
        return

    items = list(player.queue)

    if position < 1 or position > len(items):
        await interaction.response.send_message(
            "❌ Invalid queue position."
        )
        return

    track = items[position - 1]

    try:
        player.queue.remove(track)
    except Exception:
        await interaction.response.send_message(
            "❌ Could not remove track."
        )
        return

    await interaction.response.send_message(
        f"🗑️ Removed **{track.title}**"
    )


@bot.tree.command(name="rm", description="Remove queue item")
@app_commands.describe(position="Queue position")
async def rm(
    interaction: discord.Interaction,
    position: int
):
    await remove(interaction, position)


# ============================================================
# /MOVE
# ============================================================

@bot.tree.command(name="move", description="Move a queue item")
@app_commands.describe(
    from_position="Current position",
    to_position="New position"
)
async def move(
    interaction: discord.Interaction,
    from_position: int,
    to_position: int
):

    player = get_player(interaction.guild)

    if not player:
        await interaction.response.send_message(
            "❌ Not connected."
        )
        return

    items = list(player.queue)

    if (
        from_position < 1
        or from_position > len(items)
        or to_position < 1
        or to_position > len(items)
    ):
        await interaction.response.send_message(
            "❌ Invalid position."
        )
        return

    track = items.pop(from_position - 1)
    items.insert(to_position - 1, track)

    player.queue.clear()

    for item in items:
        player.queue.put(item)

    await interaction.response.send_message(
        f"↔️ Moved **{track.title}**."
    )


# ============================================================
# /SKIPTO
# ============================================================

@bot.tree.command(name="skipto", description="Skip to queue position")
@app_commands.describe(position="Queue position")
async def skipto(
    interaction: discord.Interaction,
    position: int
):

    player = get_player(interaction.guild)

    if not player:
        await interaction.response.send_message(
            "❌ Not connected."
        )
        return

    items = list(player.queue)

    if position < 1 or position > len(items):
        await interaction.response.send_message(
            "❌ Invalid position."
        )
        return

    target = items[position - 1]

    player.queue.clear()

    for item in items[position:]:
        player.queue.put(item)

    await player.play(target)

    await interaction.response.send_message(
        f"⏭️ Skipped to **{target.title}**"
    )


# ============================================================
# /SEEK
# ============================================================

@bot.tree.command(name="seek", description="Seek in the current song")
@app_commands.describe(seconds="Position in seconds")
async def seek(
    interaction: discord.Interaction,
    seconds: int
):

    player = get_player(interaction.guild)

    if not player or not player.current:
        await interaction.response.send_message(
            "❌ Nothing is playing."
        )
        return

    if seconds < 0:
        await interaction.response.send_message(
            "❌ Seconds cannot be negative."
        )
        return

    try:
        await player.seek(seconds * 1000)

        await interaction.response.send_message(
            f"⏩ Seeked to **{seconds}s**."
        )

    except Exception as e:
        await interaction.response.send_message(
            f"❌ Seek failed: `{e}`"
        )


# ============================================================
# /FORWARD
# ============================================================

@bot.tree.command(name="forward", description="Forward 10 seconds")
async def forward(interaction: discord.Interaction):

    player = get_player(interaction.guild)

    if not player:
        await interaction.response.send_message(
            "❌ Nothing is playing."
        )
        return

    position = getattr(player, "position", 0)

    await player.seek(position + 10000)

    await interaction.response.send_message(
        "⏩ Forwarded 10 seconds."
    )


@bot.tree.command(name="fwd", description="Forward 10 seconds")
async def fwd(interaction: discord.Interaction):
    await forward(interaction)


# ============================================================
# /REWIND
# ============================================================

@bot.tree.command(name="rewind", description="Rewind 10 seconds")
async def rewind(interaction: discord.Interaction):

    player = get_player(interaction.guild)

    if not player:
        await interaction.response.send_message(
            "❌ Nothing is playing."
        )
        return

    position = getattr(player, "position", 0)

    await player.seek(max(0, position - 10000))

    await interaction.response.send_message(
        "⏪ Rewound 10 seconds."
    )


@bot.tree.command(name="rwd", description="Rewind 10 seconds")
async def rwd(interaction: discord.Interaction):
    await rewind(interaction)


# ============================================================
# /REPLAY
# ============================================================

@bot.tree.command(name="replay", description="Replay current song")
async def replay(interaction: discord.Interaction):

    player = get_player(interaction.guild)

    if not player or not player.current:
        await interaction.response.send_message(
            "❌ Nothing is playing."
        )
        return

    track = player.current

    await player.play(track, replace=True)

    await interaction.response.send_message(
        f"🔄 Replaying **{track.title}**"
    )


# ============================================================
# /JOIN
# ============================================================

@bot.tree.command(name="join", description="Join your voice channel")
async def join(interaction: discord.Interaction):

    await interaction.response.defer()

    player = await ensure_voice(interaction)

    if player:
        await interaction.followup.send(
            f"🔊 Joined **{player.channel.name}**."
        )


@bot.tree.command(name="summon", description="Join your voice channel")
async def summon(interaction: discord.Interaction):
    await join(interaction)


# ============================================================
# /LEAVE
# ============================================================

@bot.tree.command(name="leave", description="Leave voice channel")
async def leave(interaction: discord.Interaction):

    player = get_player(interaction.guild)

    if not player:
        await interaction.response.send_message(
            "❌ I'm not in a voice channel."
        )
        return

    await player.disconnect()

    await interaction.response.send_message(
        "👋 Disconnected."
    )


@bot.tree.command(name="disconnect", description="Disconnect from voice")
async def disconnect(interaction: discord.Interaction):
    await leave(interaction)


@bot.tree.command(name="fuckoff", description="Disconnect")
async def fuckoff(interaction: discord.Interaction):
    await leave(interaction)


@bot.tree.command(name="leavecleanup", description="Disconnect and clear queue")
async def leavecleanup(interaction: discord.Interaction):
    await leave(interaction)


# ============================================================
# /HISTORY
# ============================================================

@bot.tree.command(name="history", description="Show recently played songs")
async def history(interaction: discord.Interaction):

    tracks = bot.history.get(interaction.guild.id, [])

    if not tracks:
        await interaction.response.send_message(
            "📜 No history yet."
        )
        return

    text = ""

    for i, track in enumerate(list(tracks)[:15], 1):
        text += f"`{i}.` {track.title[:80]}\n"

    embed = discord.Embed(
        title="📜 Music History",
        description=text,
        color=discord.Color.blurple()
    )

    await interaction.response.send_message(
        embed=embed
    )


@bot.tree.command(name="hist", description="Show history")
async def hist(interaction: discord.Interaction):
    await history(interaction)


@bot.tree.command(name="recent", description="Show recently played songs")
async def recent(interaction: discord.Interaction):
    await history(interaction)


# ============================================================
# /FAVORITES
# ============================================================

@bot.tree.command(name="favorites", description="Show your favorites")
async def favorites(interaction: discord.Interaction):

    songs = bot.favorites.get(interaction.user.id, [])

    if not songs:
        await interaction.response.send_message(
            "❤️ You don't have any favorites saved yet."
        )
        return

    text = "\n".join(
        f"`{i}.` {song[:90]}"
        for i, song in enumerate(songs[:20], 1)
    )

    await interaction.response.send_message(
        f"❤️ **Your Favorites**\n{text}"
    )


@bot.tree.command(name="liked", description="Show liked songs")
async def liked(interaction: discord.Interaction):
    await favorites(interaction)


@bot.tree.command(name="likes", description="Show liked songs")
async def likes(interaction: discord.Interaction):
    await favorites(interaction)


# ============================================================
# /LIKE
# ============================================================

@bot.tree.command(name="like", description="Save current song")
async def like(interaction: discord.Interaction):

    player = get_player(interaction.guild)

    if not player or not player.current:
        await interaction.response.send_message(
            "❌ Nothing is playing."
        )
        return

    track = player.current

    songs = bot.favorites.setdefault(
        interaction.user.id,
        []
    )

    if track.title not in songs:
        songs.append(track.title)

    await interaction.response.send_message(
        f"❤️ Saved **{track.title}**"
    )


@bot.tree.command(name="heart", description="Like current song")
async def heart(interaction: discord.Interaction):
    await like(interaction)


@bot.tree.command(name="love", description="Like current song")
async def love(interaction: discord.Interaction):
    await like(interaction)


# ============================================================
# /VOTESKIP
# ============================================================

@bot.tree.command(name="voteskip", description="Skip current song")
async def voteskip(interaction: discord.Interaction):

    await interaction.response.send_message(
        "🗳️ Vote received. Skipping."
    )

    player = get_player(interaction.guild)

    if player and player.playing:
        await player.skip()


# ============================================================
# /REMOVEDUPES
# ============================================================

@bot.tree.command(
    name="removedupes",
    description="Remove duplicate songs"
)
async def removedupes(interaction: discord.Interaction):

    player = get_player(interaction.guild)

    if not player:
        await interaction.response.send_message(
            "❌ Not connected."
        )
        return

    items = list(player.queue)

    seen = set()
    unique = []

    for track in items:

        key = track.title.lower()

        if key not in seen:
            seen.add(key)
            unique.append(track)

    removed = len(items) - len(unique)

    player.queue.clear()

    for track in unique:
        player.queue.put(track)

    await interaction.response.send_message(
        f"🧹 Removed **{removed}** duplicates."
    )


# ============================================================
# /PING
# ============================================================

@bot.tree.command(name="ping", description="Check bot latency")
async def ping(interaction: discord.Interaction):

    latency = round(bot.latency * 1000)

    await interaction.response.send_message(
        f"🏓 `{latency}ms`"
    )


# ============================================================
# /SERVERPROFILE
# ============================================================

@bot.tree.command(
    name="serverprofile",
    description="Show server music profile"
)
async def serverprofile(interaction: discord.Interaction):

    guild = interaction.guild
    player = get_player(guild)

    embed = discord.Embed(
        title=f"🎵 {guild.name}",
        color=discord.Color.blurple()
    )

    embed.add_field(
        name="Members",
        value=str(guild.member_count),
        inline=True
    )

    embed.add_field(
        name="Voice",
        value=(
            player.channel.name
            if player and player.channel
            else "Not connected"
        ),
        inline=True
    )

    embed.add_field(
        name="Loop",
        value=bot.loops.get(guild.id, "off"),
        inline=True
    )

    await interaction.response.send_message(
        embed=embed
    )


# ============================================================
# /SETTINGS
# ============================================================

@bot.tree.command(
    name="settings",
    description="Show music settings"
)
async def settings(interaction: discord.Interaction):

    player = get_player(interaction.guild)

    volume_value = getattr(player, "volume", 100) if player else 100

    await interaction.response.send_message(
        f"⚙️ **ErYx Music Settings**\n"
        f"Volume: **{volume_value}%**\n"
        f"Loop: **{bot.loops.get(interaction.guild.id, 'off')}**\n"
        f"Prefix: `{PREFIX}`"
    )


@bot.tree.command(name="setting", description="Show settings")
async def setting(interaction: discord.Interaction):
    await settings(interaction)


# ============================================================
# /CONTROL
# ============================================================

@bot.tree.command(
    name="control",
    description="Show music controls"
)
async def control(interaction: discord.Interaction):

    await interaction.response.send_message(
        "🎛️ **ErYx Music Controls**\n\n"
        "`/play` — Play\n"
        "`/skip` — Skip\n"
        "`/pause` — Pause\n"
        "`/resume` — Resume\n"
        "`/stop` — Stop\n"
        "`/queue` — Queue\n"
        "`/volume` — Volume\n"
        "`/loop` — Loop"
    )


@bot.tree.command(name="controls", description="Show controls")
async def controls(interaction: discord.Interaction):
    await control(interaction)


@bot.tree.command(name="ctrl", description="Show controls")
async def ctrl(interaction: discord.Interaction):
    await control(interaction)


@bot.tree.command(name="ct", description="Show controls")
async def ct(interaction: discord.Interaction):
    await control(interaction)


# ============================================================
# /ALIASES
# ============================================================

@bot.tree.command(
    name="aliases",
    description="Show command aliases"
)
async def aliases(interaction: discord.Interaction):

    await interaction.response.send_message(
        "**ErYx Music Aliases**\n\n"
        "`/p` → `/play`\n"
        "`/pn` → `/playnow`\n"
        "`/pskip` → `/skip`\n"
        "`/fskip` → `/skip`\n"
        "`/fs` → `/skip`\n"
        "`/vol` → `/volume`\n"
        "`/q` → `/queue`\n"
        "`/np` → `/nowplaying`\n"
        "`/hist` → `/history`\n"
        "`/rm` → `/remove`\n"
        "`/fwd` → `/forward`\n"
        "`/rwd` → `/rewind`"
    )


# ============================================================
# /EFFECTS
# ============================================================

@bot.tree.command(
    name="effects",
    description="Show available audio effects"
)
async def effects(interaction: discord.Interaction):

    await interaction.response.send_message(
        "🎚️ **Available Effects**\n\n"
        "`nightcore`\n"
        "`slow`\n"
        "`deep`\n"
        "`chipmunk`\n"
        "`vaporwave`\n"
        "`karaoke`\n"
        "`tremolo`\n"
        "`vibrato`\n"
        "`distortion`\n"
        "`bassboost`\n"
        "`lowpass`\n"
        "`reset`"
    )


# ============================================================
# /DRM
# ============================================================

@bot.tree.command(
    name="drm",
    description="Show playback compatibility"
)
async def drm(interaction: discord.Interaction):

    await interaction.response.send_message(
        "ℹ️ Playback is handled through Lavalink. "
        "Some tracks may be unavailable depending on the source."
    )


# ============================================================
# /PREMIUM
# ============================================================

@bot.tree.command(
    name="premium",
    description="Show premium status"
)
async def premium(interaction: discord.Interaction):

    await interaction.response.send_message(
        "⭐ ErYx Music premium features are currently unavailable."
    )


# ============================================================
# /CHANGELOG
# ============================================================

@bot.tree.command(
    name="changelog",
    description="Show latest bot changes"
)
async def changelog(interaction: discord.Interaction):

    await interaction.response.send_message(
        "📋 **ErYx Music Changelog**\n\n"
        "• Wavelink playback\n"
        "• Lavalink support\n"
        "• 300% volume limit\n"
        "• Queue controls\n"
        "• Search\n"
        "• History\n"
        "• Favorites\n"
        "• Loop modes\n"
        "• Prefix commands"
    )


# ============================================================
# /FEEDBACK
# ============================================================

@bot.tree.command(
    name="feedback",
    description="Send feedback"
)
@app_commands.describe(message="Your feedback")
async def feedback(
    interaction: discord.Interaction,
    message: str
):

    print(
        f"[Feedback] "
        f"{interaction.user} ({interaction.user.id}): "
        f"{message}"
    )

    await interaction.response.send_message(
        "✅ Feedback received. Thanks."
    )


# ============================================================
# PREFIX COMMANDS
# ============================================================

@bot.command(name="play")
async def prefix_play(
    ctx: commands.Context,
    *,
    query: str
):
    await play_track_prefix(ctx, query)


async def play_track_prefix(ctx, query):

    player = ctx.guild.voice_client

    if not player:

        channel = getattr(ctx.author.voice, "channel", None)

        if not channel:
            await ctx.send(
                "❌ Join a voice channel first."
            )
            return

        player = await channel.connect(
            cls=wavelink.Player
        )

    tracks = await search_track(query)

    if not tracks:
        await ctx.send("❌ No results found.")
        return

    track = tracks[0]

    if player.playing:
        player.queue.put(track)

        await ctx.send(
            f"➕ **{track.title}** added to queue."
        )

    else:

        await player.play(track)

        await ctx.send(
            f"▶️ Playing **{track.title}**"
        )


@bot.command(name="skip")
async def prefix_skip(ctx):
    player = ctx.guild.voice_client

    if player and player.playing:
        await player.skip()
        await ctx.send("⏭️ Skipped.")
    else:
        await ctx.send("❌ Nothing is playing.")


@bot.command(name="stop")
async def prefix_stop(ctx):
    player = ctx.guild.voice_client

    if not player:
        await ctx.send("❌ Not connected.")
        return

    player.queue.clear()

    try:
        await player.stop()
    except Exception:
        pass

    await ctx.send("⏹️ Stopped.")


@bot.command(name="pause")
async def prefix_pause(ctx):

    player = ctx.guild.voice_client

    if not player:
        await ctx.send("❌ Not connected.")
        return

    await player.pause(True)

    await ctx.send("⏸️ Paused.")


@bot.command(name="resume")
async def prefix_resume(ctx):

    player = ctx.guild.voice_client

    if not player:
        await ctx.send("❌ Not connected.")
        return

    await player.pause(False)

    await ctx.send("▶️ Resumed.")


@bot.command(name="queue")
async def prefix_queue(ctx):

    player = ctx.guild.voice_client

    if not player:
        await ctx.send("❌ Not connected.")
        return

    if not player.queue:
        await ctx.send("📭 Queue is empty.")
        return

    text = ""

    for i, track in enumerate(list(player.queue)[:20], 1):
        text += f"`{i}.` {track.title[:80]}\n"

    await ctx.send(
        f"🎵 **Queue**\n{text}"
    )


@bot.command(name="vol")
async def prefix_volume(
    ctx,
    volume: int
):

    player = ctx.guild.voice_client

    if not player:
        await ctx.send("❌ Not connected.")
        return

    volume = max(0, min(volume, MAX_VOLUME))

    await player.set_volume(volume)

    await ctx.send(
        f"🔊 Volume: **{volume}%**"
    )


@bot.command(name="help")
async def prefix_help(ctx):

    await ctx.send(
        "**ErYx Music**\n\n"
        "`!!play <song>`\n"
        "`!!skip`\n"
        "`!!stop`\n"
        "`!!pause`\n"
        "`!!resume`\n"
        "`!!queue`\n"
        "`!!vol <0-300>`\n\n"
        "Slash commands are also available."
    )


# ============================================================
# QUICK "P SONG"
# ============================================================

@bot.listen()
async def eryx_quick_play(message: discord.Message):

    if message.author.bot:
        return

    if not message.content.lower().startswith("p "):
        return

    query = message.content[2:].strip()

    if not query:
        return

    await play_track_prefix(
        message.channel,
        query
    )


# ============================================================
# GENERAL MESSAGE PROCESSING
# ============================================================

@bot.event
async def on_message(message):

    if message.author.bot:
        return

    await bot.process_commands(message)


# ============================================================
# START
# ============================================================

if __name__ == "__main__":

    if (
        not DISCORD_TOKEN
        or DISCORD_TOKEN == "YOUR_DISCORD_BOT_TOKEN"
    ):
        print("ERROR: Put your Discord bot token in main.py")
        raise SystemExit(1)

    if (
        not LAVALINK_PASSWORD
        or LAVALINK_PASSWORD == "YOUR_LAVALINK_PASSWORD"
    ):
        print("ERROR: Put your Lavalink password in main.py")
        raise SystemExit(1)

    print("[ErYx] Starting ErYx Music...")

    bot.run(DISCORD_TOKEN)
