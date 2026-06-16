"""Core helpers for Spartify shared between desktop and mobile.

This module contains pure-Python logic for playlists and media downloads
so it can be reused by both the Tkinter desktop app and the Kivy mobile app.
"""

from .media import (
    ensure_ffmpeg,
    download_song_to_folder,
    download_playlist_songs,
)

from .playlists import (
    default_settings,
    get_playlist_file,
    load_playlist,
    save_playlist,
    list_playlists,
    delete_playlist,
    rename_playlist,
    add_song_to_playlist,
    remove_song_from_playlist,
)

__all__ = [
    'ensure_ffmpeg',
    'download_song_to_folder',
    'download_playlist_songs',
    'default_settings',
    'get_playlist_file',
    'load_playlist',
    'save_playlist',
    'list_playlists',
    'delete_playlist',
    'rename_playlist',
    'add_song_to_playlist',
    'remove_song_from_playlist',
]
