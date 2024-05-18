import discord
from discord.ext import commands
import yt_dlp as youtube_dl
import asyncio
import random
import time
import os

intents = discord.Intents.default()
intents.message_content = True  # Enable this if you need message content intent
intents.guilds = True
intents.voice_states = True  # Needed for voice channel join/leave
intents.members = True  # Enable this if you need server members intent

bot = commands.Bot(command_prefix='!', intents=intents)
song_queue = []
  
# Configuration for yt-dlp
ytdl_format_options = {
    'format': 'bestaudio/best',
    'outtmpl': '%(extractor)s-%(id)s-%(title)s.%(ext)s',
    'restrictfilenames': True,
    'noplaylist': True,
    'nocheckcertificate': True,
    'ignoreerrors': True,
    'logtostderr': False,
    'quiet': True,
    'no_warnings': True,
    'default_search': 'auto',
    'source_address': '0.0.0.0',  # Bind to ipv4 since ipv6 addresses cause issues sometimes
    'simulate': True,
    'playlistend': 20
}

ffmpeg_options = {
    'options': '-vn'
}

ytdl = youtube_dl.YoutubeDL(ytdl_format_options)
class YTDLSource(discord.PCMVolumeTransformer):
    def __init__(self, source, *, data, volume=0.75):
        super().__init__(source, volume)
        self.data = data
        self.title = data.get('title')
        self.url = data.get('url')

    @classmethod
    async def ytdl_search(cls, search,  *, loop=None, stream=False):
        search_query = search
        if "https://" not in search:
            search_query = f"ytsearch{1}:{search}"
        
        loop = loop or asyncio.get_event_loop()
        data = await loop.run_in_executor(None, lambda: ytdl.extract_info(search_query, download=not stream))
        
        if 'entries' in data:
            # If it is playlist, append to queue
            if len(data['entries']) > 1:
                for i in range(len(data['entries'])):
                    if i > 0:
                        song_queue.append(data['entries'][i].get('title'))
                        print(data['entries'][i].get('title'))

            # Take first item from a playlist or search query
            data = data['entries'][0]
                     
        filename = data['url'] if stream else ytdl.prepare_filename(data)
        return cls(discord.FFmpegPCMAudio(filename, **ffmpeg_options), data=data)

# Join & Leave voice channel
@bot.command(name='join', help='Tells Robin to join the voice channel')
async def join(ctx):
    try:
        if not ctx.message.author.voice:
            await ctx.send("You are not connected to a voice channel, I can't follow you there!")
            return
        else:
            channel = ctx.message.author.voice.channel
            await ctx.send("Welcome to Penacony! What kind of song are you in the mood for now?")
        await channel.connect()
    except Exception as e:
        await ctx.send(f"Sorry, there is an error with my program: **{e}**")

@bot.command(name='leave', help='Make Robin leave the voice channel')
async def leave(ctx):
    try:
        await ctx.voice_client.disconnect()
        await ctx.send(f"The concert is over, goodbye & take care! ^.^")
    except Exception as e:
        await ctx.send(f"Sorry, there is an error with my program: **{e}**")

# Fun commands
magic_8ball_list = [
    "It is certain.",
    "It is decidedly so.",
    "Without a doubt.",
    "Yes, definitely.",
    "You may rely on it.",
    "As I see it, yes.",
    "Most likely.",
    "Outlook good.",
    "Yes.",
    "Signs point to yes.",
    "Reply hazy, try again.",
    "Ask again later.",
    "Better not tell you now.",
    "Cannot predict now.",
    "Concentrate and ask again.",
    "Don't count on it.",
    "My reply is no.",
    "My sources say no.",
    "Outlook not so good.",
    "Very doubtful."
]

@bot.command(name='hi', help='do !hi (name)')
async def hi(ctx, *, name: str = None):
    if name == None:
        await ctx.send(f"hi, {ctx.message.author.name}!")
    else:
        await ctx.send(f"hi, {name}!")
    
@bot.command(name='roll', help='roll a dice')
async def roll(ctx):
    r = random.randint(1, 6)
    await ctx.send(f"**Aventurine:** *How about a game? Nothing fancy, just a game of dice🎲 to gauge today's luck.*")
    time.sleep(1)
    await ctx.send(f"{ctx.message.author.name}'s roll: **{r}**")
    
@bot.command(name='8ball', help='ask the magic 8 ball')
async def magic_8ball(ctx, *, qn: str = None):
    if qn is not None:
        r = random.randint(0, 19)
        await ctx.send(f"*{magic_8ball_list[r]}*")
    else:
        await ctx.send(f"*The magic 8 ball is waiting eagerly...*")

# Music Commands     
@bot.command(name='play', help='To play song or add song to queue')
async def play(ctx, *search_query):
    try:
        global song_queue
        
        try:
            await ctx.message.author.voice.channel.connect()
        except AttributeError:
            await ctx.send("You are not connected to a voice channel, I can't follow you there!")
            song_queue.clear()
            return
        except discord.ClientException:
            None
        
        search = " ".join(search_query)
        song_queue.append(search)
        voice_client = ctx.message.guild.voice_client

        if not voice_client.is_playing():
            while len(song_queue) > 0:
                async with ctx.typing():
                    done_event = asyncio.Event()

                    def after_playback(error):
                        if error:
                            print(f'Player error: {error}')
                        done_event.set()

                    current_song = song_queue[0]
                    song_queue.pop(0)
                    
                    await ctx.send(f"*Robin is preparing to sing~*") 
                    player = await YTDLSource.ytdl_search(current_song, loop=bot.loop)
                    await ctx.send(f"Okay, I'm about to sing: **{player.title}**")
                    voice_client.play(player, after=after_playback)
                    
                    await done_event.wait()
                    
            if len(song_queue) == 0:
                await ctx.send("Thank you for attending my concert, have a wonderful night~ 💕")
        else:
            await ctx.send(f"I'll add this song request to the queue! **Current Queue: {len(song_queue)}**")
    except Exception as e:
        await ctx.send(f"Sorry, there is an error with my program: **{e}**")

@bot.command(name='queue', help='Check queue status')
async def queue(ctx):
    global song_queue
    msg = "Songs in queue: \n"
    
    if len(song_queue) == 0:
        msg = "No songs in queue."
    
    for i in range(len(song_queue)):
        msg = msg + f"**{i + 1}** - {song_queue[i]} \n"
        
    await ctx.send(msg)

@bot.command(name='stop', help='Stops the song')
async def stop(ctx):
    global song_queue
    song_queue.clear()
    
    voice_client = ctx.message.guild.voice_client
    if voice_client.is_paused():
        voice_client.resume()
    
    if voice_client.is_playing():
        await ctx.send("Sure, I'll stop singing.")
        voice_client.stop()
    else:
        await ctx.send("I'm not singing anything at the moment...")
        
@bot.command(name='skip', help='Stops the song')
async def skip(ctx):
    voice_client = ctx.message.guild.voice_client
    if voice_client.is_playing():
        
        if len(song_queue) < 1:
            await ctx.send("Sure, I'll stop singing.")
        else:
            await ctx.send("All right, I'll switch to the next song.")
        voice_client.stop()
    else:
        await ctx.send("I'm not singing anything at the moment...") 

@bot.command(name='pause', help='This command pauses the song')
async def pause(ctx):
    voice_client = ctx.message.guild.voice_client
    if voice_client.is_playing():
        voice_client.pause()
        await ctx.send("Got it, I'll pause singing.")
    else:
        await ctx.send("I'm not singing anything at the moment...")

@bot.command(name='resume', help='Resumes the song')
async def resume(ctx):
    voice_client = ctx.message.guild.voice_client
    if voice_client.is_paused():
        voice_client.resume()
        await ctx.send("Got it, I'll resume singing.")
    else:
        await ctx.send("I'm not singing anything at the moment...")

TOKEN = os.getenv('ROBIN_AI_DISCORD_TOKEN')
if TOKEN: 
    bot.run(TOKEN)
else:
    print("Error: TOKEN not found.")

