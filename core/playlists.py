import os
import json

PLAYLISTS_DIR = os.path.join(os.getcwd(), 'playlists')

def default_settings():
    return {
        "accent_color": "#ff9bb3",
        "secondary_color": "#2d2f36",
        "text_color": "#f3f4f6",
        "button_color": "#ffacc6",
        "menu_base_color": "#ffacc6",
        "bg_color": "#121212",
        "divider_color": "#3a3a3a",
        "dividers_enabled": True,
        "shadows_enabled": True,
        "shadow_intensity": 6,
        "bg_darkness": 0,
        "slider_style": "larpify",
    }

def _ensure_playlists_dir():
    os.makedirs(PLAYLISTS_DIR, exist_ok=True)

def get_playlist_file(name):
    _ensure_playlists_dir()
    safe_name = "".join(c for c in name if c.isalnum() or c in (' ', '-', '_')).strip()
    return os.path.join(PLAYLISTS_DIR, f"{safe_name}.json")

def load_playlist(name):
    path = get_playlist_file(name)
    if os.path.exists(path):
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    return []

def save_playlist(name, songs):
    path = get_playlist_file(name)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(songs, f, indent=2)

def list_playlists():
    _ensure_playlists_dir()
    files = os.listdir(PLAYLISTS_DIR)
    return [f[:-5] for f in files if f.endswith('.json')]

def delete_playlist(name):
    path = get_playlist_file(name)
    if os.path.exists(path):
        os.remove(path)

def rename_playlist(old, new):
    old_path = get_playlist_file(old)
    new_path = get_playlist_file(new)
    if os.path.exists(old_path):
        os.rename(old_path, new_path)

def add_song_to_playlist(playlist_name, song_dict):
    path = get_playlist_file(playlist_name)
    songs = []
    if os.path.exists(path):
        try:
            with open(path, 'r', encoding='utf-8') as f:
                songs = json.load(f)
        except Exception:
            songs = []

    title = song_dict.get('title', '')
    artist = song_dict.get('artist', song_dict.get('artists', ''))
    videoId = song_dict.get('videoId', '')
    filepath = song_dict.get('filepath', '')

    duplicate = False
    if videoId:
        duplicate = any(s.get('videoId') == videoId for s in songs)
    else:
        duplicate = any(s.get('title') == title and s.get('artist') == artist for s in songs)

    if duplicate:
        return False

    songs.append({'title': title, 'artist': artist, 'videoId': videoId, 'filepath': filepath})
    try:
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(songs, f, indent=2)
        return True
    except Exception:
        return False

def remove_song_from_playlist(playlist_name, song_index):
    songs = load_playlist(playlist_name)
    if 0 <= song_index < len(songs):
        del songs[song_index]
        save_playlist(playlist_name, songs)
