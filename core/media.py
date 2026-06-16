import os
import urllib.request
import zipfile
import shutil
import yt_dlp

FFMPEG_DIR = os.path.join(os.getcwd(), 'ffmpeg')
FFMPEG_EXE = os.path.join(FFMPEG_DIR, 'bin', 'ffmpeg')
# Windows uses ffmpeg.exe; mobile packaging will differ

FFMPEG_URL = 'https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip'

def ensure_ffmpeg():
    """Ensure an ffmpeg binary is present under ./ffmpeg/bin.
    On platforms where bundled ffmpeg is not possible, the caller should
    provide a system ffmpeg or use mobile-ffmpeg solutions.
    """
    exe = FFMPEG_EXE
    if os.name == 'nt':
        exe = exe + '.exe'
    if os.path.exists(exe):
        return
    try:
        os.makedirs(FFMPEG_DIR, exist_ok=True)
        zip_path = os.path.join(FFMPEG_DIR, 'ffmpeg.zip')
        urllib.request.urlretrieve(FFMPEG_URL, zip_path)
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(FFMPEG_DIR)
        # move extracted contents up if nested
        for item in os.listdir(FFMPEG_DIR):
            item_path = os.path.join(FFMPEG_DIR, item)
            if os.path.isdir(item_path) and item.startswith('ffmpeg'):
                for sub in os.listdir(item_path):
                    shutil.move(os.path.join(item_path, sub), FFMPEG_DIR)
                shutil.rmtree(item_path, ignore_errors=True)
                break
        os.remove(zip_path)
    except Exception:
        pass

def download_song_to_folder(video_id, title, artist, target_folder):
    os.makedirs(target_folder, exist_ok=True)
    safe_artist = "".join(c for c in artist if c.isalnum() or c in (' ', '-', '_')).rstrip()[:50]
    safe_title = "".join(c for c in title if c.isalnum() or c in (' ', '-', '_')).rstrip()[:50]
    filename = f"{safe_artist} - {safe_title}.mp3"
    filepath = os.path.join(target_folder, filename)
    if os.path.exists(filepath):
        return filepath
    ydl_opts = {
        'format': 'bestaudio/best',
        'outtmpl': filepath.replace('.mp3', '.%(ext)s'),
        'quiet': True,
        'no_warnings': True,
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }],
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([f'https://www.youtube.com/watch?v={video_id}'])
    return filepath

def download_playlist_songs(playlist_name):
    from .playlists import load_playlist, save_playlist
    songs = load_playlist(playlist_name)
    updated = False
    for song in songs:
        if not song.get('filepath') or not os.path.exists(song['filepath']):
            try:
                abs_path = download_song_to_folder(song.get('videoId',''), song.get('title',''), song.get('artist',''), os.path.join('downloads','instl'))
                song['filepath'] = abs_path
                updated = True
            except Exception:
                pass
    if updated:
        save_playlist(playlist_name, songs)
