import os
import glob
import argparse
import ffmpeg
import music_tag
from pathlib import Path
from xml.etree import ElementTree as ET
from joblib import Parallel, delayed, wrap_non_picklable_objects
from pathvalidate import sanitize_filename
from mutagen.easyid3 import EasyID3
from retrying import retry
from tqdm import tqdm
from enum import Enum


parser = argparse.ArgumentParser(prog='gst')
parser.add_argument('-i input_folder', dest='input', help='Path to contents folder. This is the folder containing data\\.', required=True)
parser.add_argument('-o output_folder', dest='output', help='Path to output folder. This is where the GST will be.', required=True)
parser.add_argument('-ver game_ver', '--version', dest='version', help='Generate GST for only one version. Leave blank to generate full GST.')
parser.add_argument('-d', '--after', dest='after_date', type=int, help='Only add songs added after this date as YYYYMMDD.', default=None)
parser.add_argument('-b', '--before', dest='before_date', type=int, help='Only add songs added before this date as YYYYMMDD.', default=None)
parser.add_argument('-yt', '--youtube', dest='yt', type=str, help='Save GST as MP4 files for YouTube uploading. Add "noshorts" to force videos to 16:9.',
                    nargs='?', const='', default=None)
parser.add_argument('-vb', '--verbose', dest='verbose', action='store_true', help='Verbose ffmpeg output. \\Disables progress bar')
parser.add_argument('-j jobs', dest='job', type=int, help='Number of jobs/threads active at once (cpu dependent). Defaults to 2.', default=2)
parser.add_argument('-g', '--genre', dest='genre', action='store_true', help='Sorts songs into genre folders within output folder',)
args = parser.parse_args()

in_path = Path(args.input)    
out_path = Path(args.output)
target_version = args.version
after_date = args.after_date
before_date = args.before_date

as_video = args.yt
if args.verbose:
    loglevel = "info"
else:
    loglevel = "quiet"
jobs = args.job

# Exclude these IDs (automation paradise)
excluded_ids = ['1259', '1438']

# For shift-jis/cp932, accented letters need to be corrected.
accent_decode = {
    '驩':'Ø',
    '齲':'♥',
    '齶':'♡',
    '趁':'Ǣ',
    '騫':'á',
    '曦':'à',
    '驫':'ā',
    '齷':'é',
    '曩':'è',
    '䧺':'ê',
    '骭':'ü',
    '隍':'Ü',
    '雋':'Ǜ',
    '鬻':'♃',
    '鬥':'Ã',
    '鬆':'Ý',
    '鬮':'¡',
    '龕':'€',
    '蹙':'ℱ',
    '頽':'ä',
    '黻':'*',
    '疉':'Ö',
    '鑒':'₩',
    '盥':'⚙︎',
    '瀑':'À',
    '蔕':'ῦ',
    '壥':'Є'
}

# Get version name from number, used for album title
version_decode = {
    '1':'BOOTH',
    '2':'INFINITE INFECTION',
    '3':'GRAVITY WARS',
    '4':'HEAVENLY HAVEN',
    '5':'VIVID WAVE',
    '6':'EXCEED GEAR',
    '7':'∇'
}

diff_decode = {
    'm': 'MXM',
    'n': 'NOV',
    'a': 'ADV',
    'e': 'EXH',
    'u': 'ULT'
}

inf_decode = {
    '2': "INF",
    '3': "GRV",
    '4': "HVN",
    '5': "VVD",
    '6': "XCD"
}


#code from Tina-otoge
class Genres(Enum):
    OTHER = 0
    EXIT_TUNES = 1
    FLOOR = 2
    TOUHOU = 4
    VOCALOID = 8
    BEMANI = 16
    ORIGINAL = 32
    POP_ANIME = 64
    HINABITA = 128

# Get the highest difficulty jacket and song available if only one option is available.
def get_jk_song(song_id, folder_name):
    jk_pattern = f'{folder_name}/jk_{song_id.zfill(4)}_?_b.png'
    s3v_pattern = f'{folder_name}/*.s3v'
    jackets = glob.glob(jk_pattern)
    songs = glob.glob(s3v_pattern)
    
    assert len(jackets) >0 and len(songs) > 0, f"Jackets and Songs must be nonempty. {song_id} has an issue."
    song_jackets = []

    if len(songs)>2:
        for song in songs:
            if "_pre" in song or "_fx" in song:
                continue
            try:
                # Verify s3v is dependent on difficulty
                diff = int(song[-6])
                try:
                    open(f'{folder_name}/jk_{song_id.zfill(4)}_{diff}_b.png')
                    song_jackets.append([song, f'{folder_name}/jk_{song_id.zfill(4)}_{diff}_b.png', song[-5]])
                except:
                    song_jackets.append([song, jackets[-1], song[-5]])
            except ValueError: #throws only if s3v is not of the form ..._{int}{diff}.s3v. Use highest diff jackets for songs with this issue.
                song_jackets.append([song, jackets[-1], 'default'])
    else:
        song_jackets.append([songs[0], jackets[-1], 'default'])
    return song_jackets

# Sometimes the code will fail while saving metadata, so retry a few times
@retry(stop_max_attempt_number=3, wait_fixed=1000)
def add_meta(song, jacket, mp3_file):
    (song_id, title, artist, filename, version, inf_ver, bpm, release_date, genre_type) = song
    song_file = EasyID3(mp3_file)
    song_file['title'] = title
    song_file['artist'] = artist
    song_file['albumartist'] = 'Various Artists'
    song_file['tracknumber'] = song_id
    song_file['genre'] =  ", ".join(genre_type)
    song_file['bpm'] = str(bpm)
    song_file.save()
    song_file = music_tag.load_file(mp3_file)
    with open(jacket, 'rb') as jk:
        song_file['artwork'] = jk.read()
    if target_version:
        song_file['album'] = f'SOUND VOLTEX {version_decode.get(version)} GST'
    else:
        song_file['album'] = 'SOUND VOLTEX GST'
        song_file['discnumber'] = version
        song_file['totaldiscs'] = len(version_decode)
        song_file['year'] = f'{release_date}'[:4]
    song_file.save()

def parse_mdb(musicdb):
    with open(musicdb, 'r', encoding='cp932') as mdb:
        root = ET.fromstring(mdb.read())
    
    music = []
    for song in root.findall('music'):
        song_id = song.attrib['id']
        if song_id in excluded_ids:
            continue
        info = song.find('info')
        version = info.find('version').text
        # TODO: ensure that infinites added to new versions with NEW songs are included here
        if target_version and version != target_version:  # If getting one version
            continue
        release_date = int(info.find('distribution_date').text)
        
        if before_date != None:
            if release_date > before_date: 
                continue
        if after_date != None:
            if release_date < after_date:
                continue
        title = info.find('title_name').text
        artist = info.find('artist_name').text
        for text, accent in accent_decode.items():
            title = title.replace(text, accent)
            artist = artist.replace(text, accent)
        filename = info.find('ascii').text
        inf_version = info.find('inf_ver').text # Get infinite version
        
        bpm = int(info.find('bpm_max').text)//100

        genre_value = int(info.find('genre').text)  # Get genre value
        genre_type = []
        
        for genre in Genres:
            if genre.value & genre_value: 
                genre_type.append(genre.name) 
                
        if genre_value == 0:
            genre_type.append('OTHER')

        music.append((song_id, title, artist, filename, version, inf_version, bpm, release_date, genre_type))
    return music

@wrap_non_picklable_objects
def add_song(song, in_path, out_path, args):
    (song_id, title, artist, filename, version, inf_ver, bpm, release_date, genre_type) = song
    sani_title = sanitize_filename(title)
    sani_artist = sanitize_filename(artist)
    folder_name = f'{in_path}/data/music/{song_id.zfill(4)}_{filename}'
    if not os.path.isdir(folder_name):
        return
    song_jackets = get_jk_song(song_id, folder_name)
    for triple in song_jackets:
        s3v_file, jacket, diff = triple
        # For songs where the audio file varies on difficulty, add difficulty abbreviations to file
        if diff=='default':
            diff_abb = ''
        else:
            diff_abb = f' {diff_decode.get(diff)}'
            if not diff_abb:
                diff_abb = f' {inf_decode.get(inf_ver)}'
        song_string = f'{song_id.zfill(4)}{diff_abb}. {sani_artist} - {sani_title}'
        out_strings = []
        if args.genre:
            for genre in genre_type:  # Some songs have multiple genres, so loop through and add to all folders
                out_strings.append(f'{genre}/{song_string}')
        else:
            out_strings.append(song_string)
        for out_string in out_strings:
            if as_video is not None:
                main = ffmpeg.input(s3v_file)
                cover = ffmpeg.input(jacket)
                vf = 'null'
                if as_video == 'noshorts' or as_video == 'noshort':
                    vf = 'scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2,setsar=1'
                (
                    ffmpeg
                    .output(main, cover, f'{out_path}/{out_string}.mp4', acodec='aac', vcodec='libx264', vf=vf, ab='256k', pix_fmt='yuv420p', loglevel=loglevel)
                    .run(overwrite_output=True)
                )
                return
            # Otherwise, audio file
            mp3_file = f'{out_path}/{out_string}.mp3'
            (
                ffmpeg
                .input(s3v_file)
                .output(f'{out_path}/{out_string}.mp3', loglevel=loglevel)
                .run(overwrite_output=True)
            )
            # Add metadata
            try:
                add_meta(song, jacket, mp3_file)
            except:
                print(f'Something went wrong while saving the song metadata for {title}. Continuing...')

if args.genre:
    for genre in Genres:
        try:os.mkdir(f'{out_path}\\{str(genre) [7:] }')
        except:pass
else:
    try:os.mkdir(f'{out_path}')
    except:pass


# If its verbose, disable progress bar
if args.verbose: Parallel(n_jobs=jobs, prefer='threads')(delayed(add_song)(song, in_path, out_path, args) for song in parse_mdb(f'{in_path}/data/others/music_db.xml') )

else: Parallel(n_jobs=jobs, prefer='threads')(delayed(add_song)(song, in_path, out_path, args) for song in tqdm(parse_mdb(f'{in_path}/data/others/music_db.xml') ) )

print("GST Complete!")