import discord
from discord.ext import commands
import yt_dlp as youtube_dl
import asyncio
import random
import time
import os
import wikipediaapi
from flask import Flask
import numpy as np
from hmmlearn import hmm
import re

app = Flask(__name__)
MUSIC_FOLDER = os.path.join(app.root_path, 'music-playing')
LYRICS_FILE_PATH = os.path.join(app.root_path, 'training-lyrics', 'training-lyrics.txt')

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
    try:
        global song_queue
        guild = ctx.message.guild.id
        msg = "Songs in queue: \n"
        
        if guild not in song_queue:
            msg = "No songs in queue."
        else:
            if len(song_queue[guild]) == 0:
                msg = "No songs in queue."
            else:
                for i in range(len(song_queue[guild])):
                    msg = msg + f"**{i + 1}** - {song_queue[guild][i]} \n"
            
        await ctx.send(msg)
    except Exception as e:
        await ctx.send(f"Sorry, there is an error with my program: **{e}**")
        print(f"showqueue Error: {e}")

@bot.command(name='stop', help='stops song and clears song queue')
async def stop(ctx):
    try:
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
    except Exception as e:
        await ctx.send(f"Sorry, there is an error with my program: **{e}**")
        print(f"stop Error: {e}")
        
@bot.command(name='skip', help='skips the current song')
async def skip(ctx):
    try:
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
    except Exception as e:
        await ctx.send(f"Sorry, there is an error with my program: **{e}**")
        print(f"skip Error: {e}")

@bot.command(name='pause', help='pauses song')
async def pause(ctx):
    try:
        voice_client = ctx.message.guild.voice_client
        if voice_client.is_playing():
            voice_client.pause()
            await ctx.send("Got it, I'll pause singing.")
        else:
            await ctx.send("I'm not singing anything at the moment...")
    except Exception as e:
        await ctx.send(f"Sorry, there is an error with my program: **{e}**")
        print(f"pause Error: {e}")

@bot.command(name='resume', help='resumes song')
async def resume(ctx):
    try:
        voice_client = ctx.message.guild.voice_client
        if voice_client.is_paused():
            voice_client.resume()
            await ctx.send("Got it, I'll resume singing.")
        else:
            await ctx.send("I'm not singing anything at the moment...")
    except Exception as e:
        await ctx.send(f"Sorry, there is an error with my program: **{e}**")
        print(f"resume Error: {e}")

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
    try:
        if fname:
            await ctx.send(f"hi, {fname}!")
        else:
            await ctx.send(f"hi, {ctx.message.author.name}!")
    except Exception as e:
        await ctx.send(f"Sorry, there is an error with my program: **{e}**")
        print(f"hi Error: {e}")
    
@bot.command(name='roll', help='rolls a die')
async def roll(ctx):
    try:
        r = random.randint(1, 6)
        await ctx.send(f"**Aventurine:** *How about a game? Nothing fancy, just a game of dice🎲 to gauge today's luck.*")
        time.sleep(1)
        await ctx.send(f"{ctx.message.author.name}'s roll: **{r}**")
    except Exception as e:
        await ctx.send(f"Sorry, there is an error with my program: **{e}**")
        print(f"roll Error: {e}")
        
@bot.command(name='8ball', help='asks magic 8 ball a question')
async def magic_8ball(ctx, *, qn: str = None):
    try:
        if qn:
            r = random.randint(0, 19)
            await ctx.send(f"*{magic_8ball_list[r]}*")
        else:
            await ctx.send(f"*The magic 8 ball is waiting eagerly...*")
    except Exception as e:
        await ctx.send(f"Sorry, there is an error with my program: **{e}**")
        print(f"8ball Error: {e}")
        
@bot.command(name='wiki', help='consults wikipedia')
async def wiki(ctx, *search_query):
    try:
        page = wikipedia.page("_".join(search_query))
        
        await ctx.send("**Dan Heng:** *I'll take a look in the archives📖.*")
        if page.exists():
            await ctx.send(f"{page.summary[0:1000]}... \n\n**Dan Heng:** *Let me know if you need any more help.*")
        else:
            await ctx.send("**Dan Heng:** *Sorry, I could not find any info on that topic...*")

    except Exception as e:
        await ctx.send(f"Sorry, there is an error with my program: **{e}**")
        print(f"wiki Error: {e}")

n_components_ = 1  # Number of hidden states
n_mix_ = 10
model = hmm.GMMHMM(n_components=n_components_, n_mix=n_mix_, n_iter=1000, tol=1e-2)
       
@bot.command(name='write-lyrics', help='AI Generated lyrics')
async def write_lyrics(ctx):
    try:
        global model
        await ctx.send("*Robin is coming up with lyrics...*")
        
        def tokenize_and_tag(file_path):
            # Regular expression pattern to include punctuation as separate tokens
            pattern = r"\s+"

            with open(file_path, 'r', encoding='utf-8') as file:
                lines = file.readlines()

            # Create a list of sentences, each sentence is a list of words and punctuation
            sentences = [re.split(pattern, line.strip()) for line in lines if line.strip()]
            for sentence in sentences:
                sentence = [s.lower() for s in sentence]
            
            # Create a dictionary to map each unique word to a unique number
            word_to_number = {}
            current_number = 1
            
            for sentence in sentences:
                for word in sentence:
                    if word not in word_to_number:
                        word_to_number[word] = current_number
                        current_number += 1
            
            # Replace words with their corresponding numbers
            tagged_sentences = [[word_to_number[word] for word in sentence] for sentence in sentences]
            
            return tagged_sentences, word_to_number
        
        # Get training lyrics
        dialogue_data, word_to_number = tokenize_and_tag(LYRICS_FILE_PATH)

        # Convert to 2D array and concatenate the dialogues (required for hmmlearn)
        lengths = [len(seq) for seq in dialogue_data]
        X = np.concatenate([np.array(seq).reshape(-1, 1) for seq in dialogue_data])

        # Train the model on the dialogue data
        model.fit(X, lengths)
        
        # Generate a sequence from the trained model
        def generate_lyrics(lyrics_length):
            generated_sequence, _ = model.sample(lyrics_length)
            print(generated_sequence.flatten())

            generated_sequence_words = []
            for wordarr in generated_sequence:
                for word in wordarr:
                    w = int(word)
                    if w > 0:
                        while w not in word_to_number.values():
                            w = w - 1
                        
                        generated_sequence_words.append(list(word_to_number.keys())[list(word_to_number.values()).index(w)])

            return re.sub(r'([.!?])\s*(\w)', lambda m: m.group(1) + ' ' + m.group(2).upper(), re.sub(r'\b(i)\b', 'I', re.sub(r'(?<=[a-zA-Z]) (?=[\.,;!?])', '', ' '.join(generated_sequence_words)).capitalize()))
        
        # Send lyrics
        await ctx.send("════*.·:·.✧ ✦ ✧.·:·.*════")
        for i in range(random.randint(4,7)):
            await ctx.send(generate_lyrics(random.randint(3, 12)))
        await ctx.send("════*.·:·.✧ ✦ ✧.·:·.*════")
        
    except Exception as e:
        await ctx.send(f"Sorry, there is an error with my program: **{e}**")
        print(f"write-lyrics Error: {e}")

@bot.command(name='fat', help='yo momma fat jokes')
async def fat(ctx, *, fname: str = None):
    try:
        if fname:
            await ctx.send(f"{fname}, yo momma so FAT, that when she went to the beach, a whale swam up and sang, 'We are family~'")
        else:
            await ctx.send(f"Yo momma so FAT, that when she went to the beach, a whale swam up and sang, 'We are family~'")
    except Exception as e:
        await ctx.send(f"Sorry, there is an error with my program: **{e}**")
        print(f"fat Error: {e}")
  
# Debug commands

'''    
@bot.command(name='~debug_show_all_queue')
async def debug_show_all_queue(ctx):
    global song_queue
    await ctx.send(song_queue)
'''
    
@bot.command(name='~debug_get_guild_id')
async def debug_get_guild_id(ctx):
    try:
        await ctx.send(f"Your server's id: {ctx.message.guild.id}")
    except Exception as e:
        await ctx.send(f"Sorry, there is an error with my program: **{e}**")
        print(f"~debug_get_guild_id Error: {e}")
    
TOKEN = os.getenv('ROBIN_AI_DISCORD_TOKEN')

if __name__ == "__main__":
    if TOKEN: 
        bot.run(TOKEN)
    else:
        print("Error: TOKEN not found. Make sure env is ROBIN_AI_DISCORD_TOKEN")

