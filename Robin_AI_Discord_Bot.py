import discord
from discord.ext import commands
import yt_dlp as youtube_dl
import asyncio
import random
import time
import os
import wikipediaapi
from flask import Flask

app = Flask(__name__)
MUSIC_FOLDER = os.path.join(app.root_path, 'music-playing')

intents = discord.Intents.default()
intents.message_content = True  # Enable this if you need message content intent
intents.guilds = True
intents.voice_states = True  # Needed for voice channel join/leave
intents.members = True  # Enable this if you need server members intent

bot = commands.Bot(command_prefix='--', intents=intents)
song_queue = dict()
wikipedia = wikipediaapi.Wikipedia('Robin_AI_Discord_Bot (https://github.com/Aravestia/Robin_AI_Discord_Bot) discord.py/2.3.2', 'en')
    
# Delete all files past a certain age to clear space
def delete_all_files(directory, keyword):
    print(f"deleting from: {directory}")
    file_age_before_delete = 10 # in seconds
    
    for root, dirs, files in os.walk(directory):
        for file in files:
            if keyword in file and os.path.getctime(os.path.join(root, file)) < time.time() - file_age_before_delete:
                file_path = os.path.join(root, file)
                    
                try:
                    os.remove(file_path)
                    print(f"File deleted: {file_path}")
                except:
                    print(f"File in use, cannot delete: {file_path}")
                    
            if len(os.listdir(directory)) == 0:
                os.rmdir(directory)
                print(f'Directory {directory} deleted.')
  
# Configuration for yt-dlp
ytdl_format_options = {
    'format': 'bestaudio/best',
    'outtmpl': os.path.join(MUSIC_FOLDER, "youtube-%(id)s-%(title)s.%(ext)s"),
    'restrictfilenames': True,
    'noplaylist': True,
    'nocheckcertificate': True,
    'ignoreerrors': True,
    'logtostderr': False,
    'quiet': True,
    'no_warnings': True,
    'default_search': 'auto',
    'source_address': '0.0.0.0',  # Bind to ipv4 since ipv6 addresses cause issues sometimes
    'playlistend': 10,
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
    async def ytdl_search(cls, search, guild, *, loop=None, stream=False):
        search_query = search
        
        guild_music_folder = os.path.join(MUSIC_FOLDER, str(guild))
        if not os.path.isdir(guild_music_folder):
            os.mkdir(guild_music_folder)
            print(f"Directory created: {guild_music_folder}.")
        
        if "https://" not in search:
            search_query = f"ytsearch{1}:{search}"
        
        loop = loop or asyncio.get_event_loop()
        data = await loop.run_in_executor(None, lambda: ytdl.extract_info(search_query, download=not stream))
        
        if 'entries' in data:
            # If it is playlist, append to queue
            if len(data['entries']) > 1:
                for i in range(len(data['entries'])):
                    if i > 0:
                        song_queue[guild].append(data['entries'][i].get('title'))
                        print(data['entries'][i].get('title'))

            # Take first item from a playlist or search query
            data = data['entries'][0]
                     
        filename = data['url'] if stream else ytdl.prepare_filename(data)
        # Move file to the guild's music folder
        os.replace(filename, os.path.join(guild_music_folder, os.path.basename(filename)))
        filename = os.path.join(guild_music_folder, os.path.basename(filename))
        print(f"File created: {filename}")
        
        return cls(discord.FFmpegPCMAudio(filename, **ffmpeg_options), data=data)

@bot.event
async def on_ready():
    print(f'Logged in as {bot.user}')
                
@bot.event
async def on_voice_state_update(member, before, after):
    try:
        global song_queue
        
        if before is not None:
            guild_music_folder = os.path.join(MUSIC_FOLDER, str(before.channel.guild.id))
        else:
            guild_music_folder = os.path.join(MUSIC_FOLDER, str(after.channel.guild.id))
        
        # If voice state updated by a user (non-bot)
        if not member.bot:
            print("A user joined or left vc")
            voice_client = discord.utils.get(bot.voice_clients, guild=member.guild)
            
            if voice_client and voice_client.channel == before.channel:
                # If bot is alone in channel
                if len(before.channel.members) == 1:

                    if before.channel.guild.id in song_queue:
                        song_queue[before.channel.guild.id].clear()
                        
                    if before.channel.guild.voice_client.is_playing():
                        voice_client.stop()

                    if guild_music_folder is not None:
                        await asyncio.sleep(2)
                        delete_all_files(guild_music_folder, 'youtube-')
                    await before.channel.guild.voice_client.disconnect()   
                    print(f"Bot has left the channel. Queue: {song_queue}")
    except Exception as e:
        print(f"on_voice_state_update Error: {e}")
        
# Join & Leave voice channel
@bot.command(name='join', help='joins the voice channel')
async def join(ctx, channel: str = None):
    try:
        vc = discord.utils.get(ctx.guild.voice_channels, name=channel)
        
        if vc is None:
            if channel is not None:
                await ctx.send("I can't find that voice channel, I'll follow you instead!")
            
            if not ctx.message.author.voice:
                await ctx.send("You are not connected to a voice channel, I can't follow you there!")
                return
            else:
                vc = ctx.message.author.voice.channel
                await vc.connect()
        else:
            if ctx.voice_client is not None:
                await ctx.voice_client.move_to(vc)
            else:
                await vc.connect()
                
        await ctx.send("Welcome to Penacony! Use '--help' to see what I can do! Have fun!")
        print(f"Connected to channel: {vc}")
    except Exception as e:
        await ctx.send(f"Sorry, there is an error with my program: **{e}**")
        print(f"join Error: {e}")

@bot.command(name='leave', help='leaves the voice channel')
async def leave(ctx):
    try:
        global song_queue
        guild_music_folder = os.path.join(MUSIC_FOLDER, str(ctx.channel.guild.id))
        
        if ctx.message.guild.voice_client.is_playing():
            await stop(ctx)
        await ctx.voice_client.disconnect()
        await ctx.send("Thank you for attending my concert, have a wonderful night~ 💕")
        
        await asyncio.sleep(2)
        delete_all_files(guild_music_folder, 'youtube-')
    except Exception as e:
        await ctx.send(f"Sorry, there is an error with my program: **{e}**")
        print(f"leave Error: {e}")

# Music Commands     
@bot.command(name='play', help='plays song or adds song to queue')
async def play(ctx, *search_query):
    try:
        global song_queue
        guild = ctx.message.guild.id
        
        try:
            await ctx.message.author.voice.channel.connect()
        except AttributeError:
            await ctx.send("You are not connected to a voice channel, I can't follow you there!")
            return
        except discord.ClientException:
            print("Bot is connected to channel.")
        
        if guild:
            if guild not in song_queue:
                song_queue.update({guild : []})

            print(f"song queue: {song_queue}")
            
            search = " ".join(search_query)
            song_queue[guild].append(search)
            voice_client = ctx.message.guild.voice_client

            if not voice_client.is_playing():
                # Loop through the entire queue to search & play each song
                while len(song_queue[guild]) > 0:
                    async with ctx.typing():
                        done_event = asyncio.Event()

                        def after_playback(error):
                            if error:
                                print(f'Player error: {error}')
                            done_event.set()

                        current_song = song_queue[guild][0]
                        song_queue[guild].pop(0)
                        
                        await ctx.send(f"*Robin is preparing to sing~*") 
                        player = await YTDLSource.ytdl_search(current_song, guild, loop=bot.loop)
                        await ctx.send(f"Okay, I'm about to sing: **{player.title}**")
                        voice_client.play(player, after=after_playback)
                        
                        await done_event.wait()
                        
                # If queue is empty after current song has finished playing
                if len(song_queue[guild]) == 0:
                    await ctx.send("*Robin has finished singing*")
                    song_queue.pop(guild)
                    print(f"queue: {song_queue}")
            else:
                await ctx.send(f"I'll add this song request to the queue! **Current Queue: {len(song_queue[guild])}**")
    except Exception as e:
        await ctx.send(f"Sorry, there is an error with my program: **{e}**")
        print(f"play Error: {e}")
        
@bot.command(name='queue', help='add song to queue')
async def queue(ctx, *search_query):
    try:
        await play(ctx, *search_query)
    except Exception as e:
        await ctx.send(f"Sorry, there is an error with my program: **{e}**")
        print(f"queue Error: {e}")

@bot.command(name='showqueue', help='check queue status')
async def showqueue(ctx):
    global song_queue
    guild = ctx.message.guild.id
    msg = "Songs in queue: \n"
    
    if len(song_queue[guild]) == 0:
        msg = "No songs in queue."
    
    for i in range(len(song_queue[guild])):
        msg = msg + f"**{i + 1}** - {song_queue[guild][i]} \n"
        
    await ctx.send(msg)

@bot.command(name='stop', help='stops song and clears song queue')
async def stop(ctx):
    global song_queue
    guild = ctx.message.guild.id

    voice_client = ctx.message.guild.voice_client
    if voice_client.is_paused():
        voice_client.resume()
    
    if voice_client.is_playing():
        await ctx.send("Sure, I'll stop singing.")
        song_queue[guild].clear()
        voice_client.stop()
    else:
        await ctx.send("I'm not singing anything at the moment...")
        
@bot.command(name='skip', help='skips the current song')
async def skip(ctx):
    global song_queue
    guild = ctx.message.guild.id
    voice_client = ctx.message.guild.voice_client
    if voice_client.is_playing():
        
        if len(song_queue[guild]) < 1:
            await ctx.send("Sure, I'll stop singing.")
        else:
            await ctx.send("All right, I'll switch to the next song.")
        voice_client.stop()
    else:
        await ctx.send("I'm not singing anything at the moment...") 

@bot.command(name='pause', help='pauses song')
async def pause(ctx):
    voice_client = ctx.message.guild.voice_client
    if voice_client.is_playing():
        voice_client.pause()
        await ctx.send("Got it, I'll pause singing.")
    else:
        await ctx.send("I'm not singing anything at the moment...")

@bot.command(name='resume', help='resumes song')
async def resume(ctx):
    voice_client = ctx.message.guild.voice_client
    if voice_client.is_paused():
        voice_client.resume()
        await ctx.send("Got it, I'll resume singing.")
    else:
        await ctx.send("I'm not singing anything at the moment...")

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

@bot.command(name='hi', help='says hi to your friend!')
async def hi(ctx, *, fname: str = None):
    if fname == None:
        await ctx.send(f"hi, {ctx.message.author.name}!")
    else:
        await ctx.send(f"hi, {fname}!")
    
@bot.command(name='roll', help='rolls a die')
async def roll(ctx):
    r = random.randint(1, 6)
    await ctx.send(f"**Aventurine:** *How about a game? Nothing fancy, just a game of dice🎲 to gauge today's luck.*")
    time.sleep(1)
    await ctx.send(f"{ctx.message.author.name}'s roll: **{r}**")
    
@bot.command(name='8ball', help='asks magic 8 ball a question')
async def magic_8ball(ctx, *, qn: str = None):
    if qn is not None:
        r = random.randint(0, 19)
        await ctx.send(f"*{magic_8ball_list[r]}*")
    else:
        await ctx.send(f"*The magic 8 ball is waiting eagerly...*")
        
@bot.command(name='wiki', help='consults wikipedia')
async def wiki(ctx, *search_query):
    page = wikipedia.page("_".join(search_query))
    
    await ctx.send("**Dan Heng:** *I'll take a look in the archives📖.*")
    try:
        if page.exists():
            await ctx.send(f"{page.summary[0:1000]}... \n\n**Dan Heng:** *Let me know if you need any more help.*")
        else:
            await ctx.send("**Dan Heng:** *Sorry, I could not find any info on that topic...*")
    except Exception as e:
        await ctx.send(f"Sorry, there is an error with my program: **{e}**")
        print(f"Error: {e}")  
  
# Debug commands

'''    
@bot.command(name='~debug_show_all_queue')
async def debug_show_all_queue(ctx):
    global song_queue
    await ctx.send(song_queue)
'''
    
@bot.command(name='~debug_get_guild_id')
async def debug_get_guild_id(ctx):
    await ctx.send(f"Your server's id: {ctx.message.guild.id}")
    
TOKEN = os.getenv('ROBIN_AI_DISCORD_TOKEN')
if TOKEN: 
    bot.run(TOKEN)
else:
    print("Error: TOKEN not found. Make sure env is ROBIN_AI_DISCORD_TOKEN")

