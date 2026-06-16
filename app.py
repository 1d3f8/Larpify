#!/usr/bin/env python3
import os
import sys
import subprocess
import urllib.request
import zipfile
import shutil
import threading
import tkinter as tk
from tkinter import ttk, colorchooser, messagebox, filedialog, simpledialog
from tkinter import font as tkfont
import random
import json
import time
import gc
import ctypes
try:
    from pygame import _sdl2 as sdl2
    HAS_SDL2_AUDIO = True
except ImportError:
    HAS_SDL2_AUDIO = False

# ----------------------------------------------------------------------
# 0. Auto‑download ffmpeg (if missing)
# ----------------------------------------------------------------------
FFMPEG_DIR = "ffmpeg"
FFMPEG_EXE = os.path.join(FFMPEG_DIR, "bin", "ffmpeg.exe")
FFMPEG_URL = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"

def ensure_ffmpeg():
    if os.path.exists(FFMPEG_EXE):
        return
    print("Downloading ffmpeg (approx. 50MB) – this happens only once...")
    zip_path = "ffmpeg.zip"
    try:
        urllib.request.urlretrieve(FFMPEG_URL, zip_path)
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(FFMPEG_DIR)
        for item in os.listdir(FFMPEG_DIR):
            item_path = os.path.join(FFMPEG_DIR, item)
            if os.path.isdir(item_path) and item.startswith("ffmpeg"):
                for sub in os.listdir(item_path):
                    shutil.move(os.path.join(item_path, sub), FFMPEG_DIR)
                os.rmdir(item_path)
                break
        os.remove(zip_path)
        print("ffmpeg ready.")
    except Exception as e:
        print(f"Failed to download ffmpeg: {e}")

ensure_ffmpeg()
os.environ["PATH"] = os.path.join(FFMPEG_DIR, "bin") + os.pathsep + os.environ.get("PATH", "")

# ----------------------------------------------------------------------
# 1. Auto‑install Python dependencies
# ----------------------------------------------------------------------
packages = [
    ("yt-dlp", "yt_dlp"),
    ("pygame", "pygame"),
    ("pillow", "PIL"),
    ("sounddevice", "sounddevice"),
]
missing = []
for pkg, imp in packages:
    try:
        __import__(imp)
    except ImportError:
        missing.append(pkg)

if missing:
    print(f"Installing missing packages: {missing}")
    subprocess.check_call([sys.executable, "-m", "pip", "install"] + missing)
    print("Restarting...")
    os.execv(sys.executable, [sys.executable] + sys.argv)

import yt_dlp
import pygame
from PIL import Image, ImageTk, ImageDraw, ImageFont

# ----------------------------------------------------------------------
# Constants & directories
# ----------------------------------------------------------------------
DOWNLOADS_BASE = "downloads"
PLAYLISTS_DIR = "playlists"
CONFIG_DIR = "configs"
TEMP_DIR = os.path.join(DOWNLOADS_BASE, "temp")
INSTL_DIR = os.path.join(DOWNLOADS_BASE, "instl")
os.makedirs(PLAYLISTS_DIR, exist_ok=True)
os.makedirs(CONFIG_DIR, exist_ok=True)
os.makedirs(TEMP_DIR, exist_ok=True)
os.makedirs(INSTL_DIR, exist_ok=True)

# ----------------------------------------------------------------------
# Playlist management (JSON based)
# ----------------------------------------------------------------------

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

def get_playlist_file(name):
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
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([f"https://www.youtube.com/watch?v={video_id}"])
        if not os.path.exists(filepath):
            for f in os.listdir(target_folder):
                if f.endswith(".mp3") and safe_title in f:
                    actual = os.path.join(target_folder, f)
                    if actual != filepath:
                        os.rename(actual, filepath)
                    break
        return filepath
    except Exception as e:
        raise Exception(f"Download failed: {e}")

def download_playlist_songs(playlist_name):
    songs = load_playlist(playlist_name)
    updated = False
    for song in songs:
        if not song.get('filepath') or not os.path.exists(song['filepath']):
            try:
                abs_path = download_song_to_folder(song['videoId'], song['title'], song['artist'], INSTL_DIR)
                song['filepath'] = abs_path
                updated = True
            except Exception as e:
                print(f"Failed to download {song['title']}: {e}")
    if updated:
        save_playlist(playlist_name, songs)

# ----------------------------------------------------------------------
# Larpify GUI
# ----------------------------------------------------------------------
class LarpifyGUI:
    def __init__(self, root):
        self.root = root
        self.root._larpify_owner = self
        self._theme_buttons = []
        self.root.title("Larpify - YouTube Music Player")
        self.root.geometry("1200x800")
        self.root.minsize(1000, 600)
        self.root.configure(bg="#121212")

        # Load saved theme
        self.config_file = os.path.join(CONFIG_DIR, "settings.json")
        self.settings = self._load_settings()
        self.accent_color = self.settings.get("accent_color", "#ff9bb3")
        self.text_color = self.settings.get("text_color", "#ffffff")
        try:
            self.secondary_color = self.settings.get("secondary_color", self._lighter_color(self.accent_color, 0.85))
        except Exception:
            self.secondary_color = self.settings.get("secondary_color", "#1f2937")
        try:
            self.tertiary_color = self.settings.get("tertiary_color", self._lighter_color(self.accent_color, 0.6))
        except Exception:
            self.tertiary_color = self.settings.get("tertiary_color", "#141414")
        self.bg_image_path = self.settings.get("bg_image", None)
        self.bg_color = self.settings.get("bg_color", "#0b0b0b")
        self.menu_base_color = self.settings.get("menu_base_color", "#ff9bb3")
        self.button_color = self.settings.get("button_color", self.menu_base_color)
        self.eye_color = self.settings.get("eye_color", "#ffffff")
        self._transparent_key = "#123456"
        self.avatar_path = self.settings.get("avatar", None)
        self.shadows_enabled = self.settings.get("shadows_enabled", True)
        self.shadow_intensity = self.settings.get("shadow_intensity", 6)
        self.slider_style = self.settings.get("slider_style", "larpify")
        self.bg_darkness = self.settings.get("bg_darkness", 0)

        # Divider settings
        self.dividers_enabled = self.settings.get("dividers_enabled", True)
        self.divider_color = self.settings.get("divider_color", "#3a3a3a")

        # Player state
        pygame.mixer.init()
        self.current_song_path = None
        self.is_playing = False
        self.current_duration = 0
        self.seeking = False
        self._play_start_time = None
        self._play_start_offset = 0.0
        self._current_sound = None
        self._bg_canvases = []
        self._current_overlay = None

        self.queue = []
        self.queue_index = -1
        self.shuffle = False
        self.current_output_device = None

        self.current_search_query = ""
        self.all_results = []
        self.displayed_count = 0
        self.step = 15

        # Build UI
        self._create_layout()
        self._create_top_bar()
        self._create_left_sidebar()
        self._create_main_area()
        self._create_bottom_control_bar()
        self._apply_theme()

        try:
            self._clear_temp_dir()
        except Exception:
            pass
        try:
            self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        except Exception:
            pass

        self._show_search_view()
        self._update_ui_loop()
        self.popout_window = None

    # ---------- Settings & Theme ----------
    def _load_settings(self):
        defaults = default_settings()
        if not os.path.exists(self.config_file):
            try:
                with open(self.config_file, 'w', encoding='utf-8') as f:
                    json.dump(defaults, f, indent=2)
            except Exception:
                pass
            return defaults.copy()

        try:
            with open(self.config_file, 'r', encoding='utf-8') as f:
                raw = f.read().strip()
            if not raw:
                with open(self.config_file, 'w', encoding='utf-8') as f:
                    json.dump(defaults, f, indent=2)
                return defaults.copy()
            loaded = json.loads(raw)
            merged = defaults.copy()
            merged.update({k: v for k, v in loaded.items() if v is not None})
            if loaded != merged:
                with open(self.config_file, 'w', encoding='utf-8') as f:
                    json.dump(merged, f, indent=2)
            return merged
        except Exception:
            try:
                with open(self.config_file, 'w', encoding='utf-8') as f:
                    json.dump(defaults, f, indent=2)
            except Exception:
                pass
            return defaults.copy()

    def _save_settings(self):
        with open(self.config_file, 'w') as f:
            json.dump(self.settings, f, indent=2)

    def _normalize_color(self, color):
        try:
            value = str(color or '').strip()
            if not value:
                return None
            if not value.startswith('#'):
                value = '#' + value
            return value[:7]
        except Exception:
            return None

    def _iter_button_widgets(self, parent):
        try:
            stack = [parent]
            seen = set()
            while stack:
                widget = stack.pop()
                try:
                    ident = id(widget)
                except Exception:
                    ident = None
                if ident is not None and ident in seen:
                    continue
                if ident is not None:
                    seen.add(ident)
                try:
                    yield widget
                except Exception:
                    pass
                try:
                    for child in widget.winfo_children():
                        stack.append(child)
                except Exception:
                    pass
        except Exception:
            return

    def _refresh_bottom_bar(self):
        try:
            if hasattr(self, 'bottom') and self.bottom.winfo_exists():
                self.bottom.configure(bg=self._main_bg())
                self._refresh_canvas_bg(self.bottom)
                self.bottom.event_generate('<Configure>')
                for name in ('song_info_label', 'current_time_label', 'total_time_label',
                             'volume_pct_label', 'volume_icon_label'):
                    try:
                        widget = getattr(self, name, None)
                        if widget is not None and hasattr(widget, 'config'):
                            widget.config(bg=self._main_bg(), fg=self.text_color)
                    except Exception:
                        pass
                for name in ('prev_btn', 'play_pause_btn', 'next_btn', 'shuffle_btn', 'popout_btn'):
                    try:
                        widget = getattr(self, name, None)
                        if widget is not None and hasattr(widget, 'config'):
                            widget.config(bg=self.button_color, fg='white')
                    except Exception:
                        pass
                try:
                    if hasattr(self, 'seek_bar'):
                        self.seek_bar.set_accent(self.accent_color)
                except Exception:
                    pass
                try:
                    if hasattr(self, 'volume_slider'):
                        self.volume_slider.set_accent(self.accent_color)
                except Exception:
                    pass
        except Exception:
            pass

    def _refresh_live_theme(self):
        """Update all UI elements with the latest theme settings instantly."""
        try:
            self.root.update_idletasks()
            self._apply_theme()
            self._refresh_accent_colors()
            self._update_text_colors()
            
            # Refresh bottom bar and dividers explicitly
            self._refresh_bottom_bar()
            self._redraw_dividers()
            self._update_topmost_divider()
            self._update_logo_divider()
        except Exception as e:
            print(f"Theme refresh error: {e}")

        try:
            for widget in self._iter_button_widgets(self.root):
                try:
                    if hasattr(widget, 'config'):
                        try:
                            widget.config(bg=self.button_color, fg='white')
                        except Exception:
                            pass
                        try:
                            widget.configure(bg=self.button_color, fg='white')
                        except Exception:
                            pass
                except Exception:
                    pass
        except Exception:
            pass
        try:
            for widget in self._iter_widget_tree(self.root):
                try:
                    if isinstance(widget, tk.Label):
                        widget.config(bg=self._main_bg(), fg=self.text_color)
                    elif isinstance(widget, tk.Entry):
                        widget.config(bg='#1b1b1b', fg=self.text_color, insertbackground=self.text_color)
                    elif isinstance(widget, tk.Frame):
                        widget.config(bg=self._main_bg())
                    elif isinstance(widget, tk.Canvas):
                        widget.config(bg=self._main_bg())
                except Exception:
                    pass
        except Exception:
            pass

        try:
            self._refresh_bottom_bar()
        except Exception:
            pass

    def _iter_widget_tree(self, parent):
        try:
            stack = [parent]
            seen = set()
            while stack:
                widget = stack.pop()
                ident = id(widget)
                if ident in seen:
                    continue
                seen.add(ident)
                try:
                    yield widget
                except Exception:
                    pass
                try:
                    for child in widget.winfo_children():
                        stack.append(child)
                except Exception:
                    pass
        except Exception:
            return

    def _refresh_accent_colors(self):
        try:
            if hasattr(self, 'title_label'):
                self.title_label.config(fg=self.button_color, bg=self._main_bg())
        except Exception: pass

        try:
            # Explicitly refresh all tracked rounded buttons
            for btn in getattr(self, '_theme_buttons', []):
                try:
                    if btn.winfo_exists():
                        btn.config(bg=self.button_color, fg='white')
                except Exception:
                    pass
        except Exception: pass

        try:
            if hasattr(self, 'playlist_listbox'):
                self.playlist_listbox.config(selectbackground=self.button_color)
        except Exception:
            pass

        try:
            self._style_global_buttons()
        except Exception:
            pass

        try:
            for sname in ('seek_bar','volume_slider','popout_seek','popout_volume'):
                if hasattr(self, sname):
                    try:
                        s = getattr(self, sname)
                        try:
                            s.set_accent(self.accent_color)
                        except Exception:
                            s.accent = self.accent_color
                    except Exception:
                        pass
        except Exception:
            pass

        try:
            st = ttk.Style()
            try:
                st.theme_use('clam')
            except Exception:
                pass
            trough = self._lighter_color(self.accent_color, 0.32)
            try:
                st.configure('Larpify.Horizontal.TScale', troughcolor=trough, background=self.accent_color)
            except Exception:
                try:
                    st.configure('Horizontal.TScale', troughcolor=trough, background=self.accent_color)
                except Exception:
                    pass
        except Exception:
            pass

        try:
            if hasattr(self, '_bg_canvases'):
                for c in self._bg_canvases:
                    try:
                        if c.winfo_exists():
                            self._refresh_canvas_bg(c)
                    except Exception:
                        pass
        except Exception:
            pass

        self._refresh_bottom_bar()
        self._redraw_dividers()
        self._update_logo_divider()

        # Update all text colors
        self._update_text_colors()

    def _update_text_colors(self):
        """Apply global text color to all labels and entry fields."""
        for widget_name in ('song_info_label', 'current_time_label', 'total_time_label',
                            'volume_pct_label', 'popout_info', 'popout_current', 'popout_total',
                            'popout_volume_label'):
            try:
                widget = getattr(self, widget_name, None)
                if widget is not None and hasattr(widget, 'config'):
                    widget.config(fg=self.text_color)
            except Exception:
                pass
        # Update entry fields
        if hasattr(self, 'search_entry'):
            try:
                self.search_entry.config(fg=self.text_color)
            except:
                pass
        # Update queue and playlist labels dynamically (they are recreated, but we set when created)

    def _redraw_dividers(self):
        try:
            if hasattr(self, 'top') and self.top.winfo_exists():
                self.top.event_generate('<Configure>')
        except Exception:
            pass
        try:
            if hasattr(self, 'left') and self.left.winfo_exists():
                self.left.event_generate('<Configure>')
        except Exception:
            pass
        try:
            if hasattr(self, 'bottom') and self.bottom.winfo_exists():
                self.bottom.event_generate('<Configure>')
        except Exception:
            pass

    def _bind_hover_effect(self, widget):
        try:
            widget.bind('<Enter>', lambda e: e.widget.config(cursor='hand2'))
            widget.bind('<Leave>', lambda e: e.widget.config(cursor=''))
        except Exception:
            pass

    def _set_accent_color(self, color):
        color = self._normalize_color(color)
        if not color:
            return
        try:
            self.accent_color = color
            self.settings['accent_color'] = color
            self._save_settings()
            self._refresh_accent_colors()
            self._apply_theme()
        except Exception:
            pass

    def _set_secondary_color(self, color):
        color = self._normalize_color(color)
        if not color:
            return
        try:
            self.secondary_color = color
            self.settings['secondary_color'] = color
            self._save_settings()
            self._refresh_accent_colors()
            self._apply_theme()
        except Exception:
            pass

    def _set_button_color(self, color):
        color = self._normalize_color(color)
        if not color:
            return
        try:
            self.button_color = color
            self.menu_base_color = color
            self.settings['button_color'] = color
            self.settings['menu_base_color'] = color
            self._save_settings()
            self._refresh_accent_colors()
            self._apply_theme()
        except Exception:
            pass

    def _set_text_color(self, color):
        color = self._normalize_color(color)
        if not color:
            return
        try:
            self.text_color = color
            self.settings['text_color'] = color
            self._save_settings()
            self._update_text_colors()
            self._apply_theme()
        except Exception:
            pass

    def _set_bg_color(self, color):
        color = self._normalize_color(color)
        if not color:
            return
        try:
            self.bg_color = color
            self.settings['bg_color'] = color
            self._save_settings()
            self._apply_theme()
            self._refresh_accent_colors()
            self._update_text_colors()
        except Exception:
            pass

    def _set_dividers_enabled(self, enabled):
        self.dividers_enabled = bool(enabled)
        self.settings['dividers_enabled'] = self.dividers_enabled
        self._save_settings()
        self._redraw_dividers()
        self._apply_theme()
        try:
            self._update_topmost_divider()
            self._update_logo_divider()
        except Exception:
            pass

    def _set_divider_color(self, color):
        color = self._normalize_color(color)
        if not color:
            return
        try:
            self.divider_color = color
            self.settings['divider_color'] = color
            self._save_settings()
            self._redraw_dividers()
            self._apply_theme()
            try:
                self._update_topmost_divider()
                self._update_logo_divider()
                if hasattr(self, 'top') and self.top.winfo_exists():
                    self.top.itemconfig(self.top_divider_line, fill=color)
                    self.top.itemconfig(self.logo_divider, fill=color)
            except Exception:
                pass
        except Exception:
            pass

    def _style_global_buttons(self):
        names = ['prev_btn', 'play_pause_btn', 'next_btn', 'shuffle_btn', 'popout_btn', 'palette_btn']
        for nm in names:
            try:
                btn = getattr(self, nm)
                btn.config(relief=tk.FLAT, bd=0, padx=8, pady=4, fg='white')
                try:
                    btn.config(activebackground=self._lighter_color(self.accent_color, 1.05))
                except Exception:
                    pass
                self._bind_hover_effect(btn)
            except Exception:
                pass

    # ---------- UI helpers: rounded rects, animations ----------
    class RoundedButton(tk.Canvas):
        def __init__(self, parent, text="", command=None, width=54, height=36, radius=None,
                     bg=None, fg="white", font=("Helvetica", 12), **kwargs):
            canvas_bg = None
            try:
                p = parent
                while p is not None:
                    try:
                        val = p.cget('bg')
                    except Exception:
                        val = None
                    if val:
                        canvas_bg = val
                        break
                    try:
                        p = p.master
                    except Exception:
                        break
            except Exception:
                canvas_bg = None
            if not canvas_bg:
                try:
                    t = parent.winfo_toplevel()
                    try:
                        tb = t.cget('bg')
                        if tb:
                            canvas_bg = tb
                    except Exception:
                        pass
                except Exception:
                    pass
            if not canvas_bg:
                canvas_bg = bg or '#000000'

            try:
                fobj = tkfont.Font(font=font)
                measured = fobj.measure(text) if text else 0
            except Exception:
                measured = 0
            min_width = measured + 28 if measured else width
            actual_width = max(width, min_width)

            super().__init__(parent, width=actual_width, height=height, bg=canvas_bg, highlightthickness=0, bd=0)
            self._parent = parent
            self._radius = radius
            self._bg = bg if bg is not None else canvas_bg
            self._fg = fg
            self._font = font
            self._command = command
            self._text = text
            self._width = actual_width
            self._height = height
            try:
                owner = getattr(self.winfo_toplevel(), '_larpify_owner', None)
                if owner is not None and self not in getattr(owner, '_theme_buttons', []):
                    owner._theme_buttons.append(self)
            except Exception:
                pass
            if self._radius is None:
                self._radius = height // 2
            try:
                self._bg_photo = None
                self._bg_img_id = None
                self._render_bg_image(self._bg)
            except Exception:
                r = min(self._radius, height // 2)
                cx1 = r
                cx2 = self._width - r
                try:
                    self._center_rect = self.create_rectangle(cx1, 0, cx2, height, fill=self._bg, outline='')
                    self._left_oval = self.create_oval(0, 0, r*2, height, fill=self._bg, outline='')
                    self._right_oval = self.create_oval(self._width - r*2, 0, self._width, height, fill=self._bg, outline='')
                except Exception:
                    pts = [r, 0, self._width-r, 0, self._width, r, self._width, height-r, self._width-r, height, r, height, 0, height-r, 0, r]
                    self._center_rect = self.create_polygon(pts, smooth=True, splinesteps=72, fill=self._bg, outline='')
                    self._left_oval = None
                    self._right_oval = None
                self._text_id = self.create_text(self._width//2, height//2, text=text, fill=fg, font=font)
            else:
                self._text_id = self.create_text(self._width//2, height//2, text=text, fill=fg, font=font)
            self.bind('<Button-1>', lambda e: self._on_click())
            self.bind('<Enter>', lambda e: self._on_hover_enter())
            self.bind('<Leave>', lambda e: self._on_hover_leave())

        def _on_click(self):
            try:
                if callable(self._command):
                    self._command()
            except Exception:
                pass

        def config(self, **kwargs):
            if 'bg' in kwargs:
                self._bg = kwargs.pop('bg')
                try:
                    self._render_bg_image(self._bg)
                except Exception:
                    pass
            if 'fg' in kwargs:
                self._fg = kwargs.pop('fg')
                try:
                    self.itemconfig(self._text_id, fill=self._fg)
                except Exception:
                    pass
            if 'text' in kwargs:
                self._text = kwargs.pop('text')
                try:
                    self.itemconfig(self._text_id, text=self._text)
                except Exception:
                    pass
            if 'command' in kwargs:
                self._command = kwargs.pop('command')
            try:
                super().config(**{k: v for k, v in kwargs.items() if k in ('width', 'height')})
            except Exception:
                pass

        def cget(self, key):
            if key == 'bg':
                return self._bg
            if key == 'text':
                return self._text
            return super().cget(key)

        def _set_fill(self, color):
            try:
                self._render_bg_image(color)
            except Exception:
                pass

        def _on_hover_enter(self):
            try:
                hover_color = self._lighter_color(self._bg, 1.08)
                self._set_fill(hover_color)
            except Exception:
                pass

        def _on_hover_leave(self):
            try:
                self._set_fill(self._bg)
            except Exception:
                pass

        def set_text(self, t):
            self.config(text=t)

        def _hex_to_rgb(self, h):
            try:
                h = h.lstrip('#')
                return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))
            except Exception:
                return (0, 0, 0)

        def _rgb_to_hex(self, rgb):
            try:
                return '#%02x%02x%02x' % rgb
            except Exception:
                return '#000000'

        def _lighter_color(self, hexc, factor=1.15):
            try:
                r, g, b = self._hex_to_rgb(hexc)
                r = min(255, int(r * factor))
                g = min(255, int(g * factor))
                b = min(255, int(b * factor))
                return self._rgb_to_hex((r, g, b))
            except Exception:
                return hexc

        def _render_bg_image(self, color):
            try:
                scale = 4
                W = max(1, int(self._width * scale))
                H = max(1, int(self._height * scale))
                r = max(1, int(self._radius * scale))
                img = Image.new('RGBA', (W, H), (0, 0, 0, 0))
                draw = ImageDraw.Draw(img)
                try:
                    draw.rounded_rectangle([0, 0, W, H], radius=r, fill=color)
                except Exception:
                    draw.rectangle([r, 0, W-r, H], fill=color)
                    draw.ellipse([0, 0, r*2, H], fill=color)
                    draw.ellipse([W - r*2, 0, W, H], fill=color)
                img = img.resize((self._width, self._height), Image.LANCZOS)
                self._bg_photo = ImageTk.PhotoImage(img)
                if getattr(self, '_bg_img_id', None):
                    try:
                        self.itemconfig(self._bg_img_id, image=self._bg_photo)
                    except Exception:
                        pass
                else:
                    try:
                        self._bg_img_id = self.create_image(0, 0, image=self._bg_photo, anchor='nw')
                    except Exception:
                        pass
            except Exception:
                raise

    def _hex_to_rgb(self, h):
        h = h.lstrip('#')
        return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))

    def _rgb_to_hex(self, rgb):
        return '#%02x%02x%02x' % rgb

    def _lighter_color(self, hexc, factor=1.15):
        try:
            r, g, b = self._hex_to_rgb(hexc)
            r = min(255, int(r * factor))
            g = min(255, int(g * factor))
            b = min(255, int(b * factor))
            return self._rgb_to_hex((r, g, b))
        except Exception:
            return hexc

    def _draw_rounded_rect(self, canvas, x1, y1, x2, y2, r=12, shadow=False, shadow_color=None, shadow_offset=None, **kwargs):
        points = [x1+r, y1, x2-r, y1, x2, y1+r, x2, y2-r, x2-r, y2, x1+r, y2, x1, y2-r, x1, y1+r]
        if shadow and getattr(self, 'shadows_enabled', False):
            off = shadow_offset if shadow_offset is not None else getattr(self, 'shadow_intensity', 6)
            try:
                sc = shadow_color or self._lighter_color(self.bg_color, 0.7)
            except Exception:
                sc = shadow_color or '#000000'
            sh_pts = []
            for i in range(0, len(points), 2):
                x = points[i] + off
                y = points[i+1] + off
                sh_pts.extend([x, y])
            try:
                canvas.create_polygon(sh_pts, smooth=True, splinesteps=36, fill=sc, outline='')
            except Exception:
                pass
        return canvas.create_polygon(points, smooth=True, splinesteps=36, **kwargs)

    # ---------- CustomSlider (no gaps) ----------
    class CustomSlider(tk.Canvas):
        def __init__(self, parent, from_=0, to=100, orient=tk.HORIZONTAL, length=200, height=18, accent="#8a7af2", bg="#121212", **kwargs):
            try:
                canvas_bg = parent.cget('bg')
            except Exception:
                canvas_bg = bg
            super().__init__(parent, width=length, height=height, bg=canvas_bg, highlightthickness=0, bd=0)
            self.from_ = from_
            self.to = to
            self.orient = orient
            self.length = length
            self.height = height
            self.accent = accent
            self.bg_color = canvas_bg
            self._val = from_
            self._thumb_size = max(14, height + 2)
            r = height // 2
            y1 = 0
            y2 = height
            start = 0
            end = length
            self._track_left = self.create_oval(start - r, y1, start + r, y2, fill="#3a3a3a", outline='')
            self._track_rect = self.create_rectangle(start, y1, end, y2, fill="#3a3a3a", outline='')
            self._track_right = self.create_oval(end - r, y1, end + r, y2, fill="#3a3a3a", outline='')
            self._fill_rect = self.create_rectangle(start, y1, start, y2, fill=self.accent, outline='')
            self._fill_right = self.create_oval(start - r, y1, start + r, y2, fill=self.accent, outline='')
            self._thumb = self.create_oval(start - self._thumb_size//2, y1, start + self._thumb_size//2, y2, fill=self.accent, outline='')
            self.command = kwargs.get('command', None)
            self.bind('<Button-1>', self._on_press)
            self.bind('<B1-Motion>', self._on_drag)
            self.bind('<ButtonRelease-1>', self._on_release)
            self.bind('<Configure>', self._on_configure)

        def _on_configure(self, event):
            try:
                self.length = event.width
                r = self.height // 2
                y1 = 0
                y2 = self.height
                start = 0
                end = self.length
                self.coords(self._track_left, start - r, y1, start + r, y2)
                self.coords(self._track_rect, start, y1, end, y2)
                self.coords(self._track_right, end - r, y1, end + r, y2)
                x = self._pos_from_val(self._val)
                self.coords(self._fill_rect, start, y1, max(start, x), y2)
                self.coords(self._fill_right, max(start - r, x - r), y1, x + r, y2)
                self.coords(self._thumb, x - self._thumb_size//2, y1, x + self._thumb_size//2, y2)
            except Exception:
                pass

        def _pos_from_val(self, val):
            ratio = (val - self.from_) / max(1, (self.to - self.from_))
            x = ratio * self.length
            return x

        def _val_from_pos(self, x):
            ratio = x / max(1, self.length)
            ratio = max(0.0, min(1.0, ratio))
            return self.from_ + ratio * (self.to - self.from_)

        def set(self, val):
            try:
                self._val = max(self.from_, min(self.to, val))
                x = self._pos_from_val(self._val)
                r = self.height // 2
                y1 = 0
                y2 = self.height
                start = 0
                self.coords(self._fill_rect, start, y1, max(start, x), y2)
                self.coords(self._fill_right, max(start - r, x - r), y1, x + r, y2)
                self.coords(self._thumb, x - self._thumb_size//2, y1, x + self._thumb_size//2, y2)
            except Exception:
                pass

        def get(self):
            return self._val

        def _on_press(self, event):
            val = self._val_from_pos(event.x)
            self.set(val)
            if callable(self.command):
                try:
                    self.command(str(int(val)))
                except Exception:
                    try:
                        self.command(val)
                    except Exception:
                        pass

        def _on_drag(self, event):
            val = self._val_from_pos(event.x)
            self.set(val)
            if callable(self.command):
                try:
                    self.command(str(int(val)))
                except Exception:
                    try:
                        self.command(val)
                    except Exception:
                        pass

        def _on_release(self, event):
            val = self._val_from_pos(event.x)
            self.set(val)
            if callable(self.command):
                try:
                    self.command(str(int(val)))
                except Exception:
                    try:
                        self.command(val)
                    except Exception:
                        pass

        def set_accent(self, color):
            try:
                self.accent = color
                self.itemconfig(self._fill_rect, fill=color)
                self.itemconfig(self._fill_right, fill=color)
                self.itemconfig(self._thumb, fill=color)
            except Exception:
                pass

    def _slide_widget(self, widget, start_x, target_x, steps=12, delay=12):
        try:
            dx = (target_x - start_x) / max(1, steps)
            cur = float(start_x)
            i = 0
            def _step():
                nonlocal cur, i
                i += 1
                cur += dx
                try:
                    widget.place_configure(x=int(cur))
                except Exception:
                    pass
                if i < steps:
                    widget.after(delay, _step)
            _step()
        except Exception:
            pass

    def _hide_overlay(self, overlay):
        try:
            w = overlay.winfo_width()
            start_x = overlay.winfo_x()
            target_x = self.root.winfo_width() + 20
            self._slide_widget(overlay, start_x, target_x)
            overlay.after(260, lambda: overlay.destroy())
        except Exception:
            try:
                overlay.destroy()
            except Exception:
                pass
        if hasattr(self, '_current_overlay') and self._current_overlay == overlay:
            self._current_overlay = None

    def _close_current_overlay(self):
        if self._current_overlay and self._current_overlay.winfo_exists():
            try:
                self._current_overlay.destroy()
            except Exception:
                pass
        self._current_overlay = None

    def _main_bg(self):
        try:
            if self.bg_image_path and os.path.exists(self.bg_image_path):
                return self._transparent_key
        except Exception:
            pass
        return self.bg_color

    def _ensure_main_toplevel(self):
        try:
            if hasattr(self, '_main_toplevel_created') and self._main_toplevel_created:
                return
        except Exception:
            pass
        try:
            self.main_canvas = self.main_placeholder
            self.main_scrollable = self.main_placeholder
            self._main_toplevel_created = True

            def _on_mousewheel(event):
                # Only scroll if canvas has scrollregion bigger than viewport
                try:
                    bbox = self.main_canvas.bbox("all")
                    if bbox and bbox[3] > self.main_canvas.winfo_height():
                        self.main_canvas.yview_scroll(int(-1*(event.delta/120)), "units")
                except Exception:
                    pass
            try:
                self.main_canvas.bind("<Enter>", lambda e: self.main_canvas.bind_all("<MouseWheel>", _on_mousewheel))
                self.main_canvas.bind("<Leave>", lambda e: self.main_canvas.unbind_all("<MouseWheel>"))
            except Exception:
                pass
        except Exception:
            pass

    def _create_bg_canvas_container(self, parent, **pack_opts):
        if not hasattr(self, '_bg_slices'):
            self._bg_slices = {}
        if not hasattr(self, '_bg_canvases'):
            self._bg_canvases = []

        canvas = tk.Canvas(parent, bg=self._main_bg(), highlightthickness=0)
        try:
            self._bg_canvases.append(canvas)
        except Exception:
            pass

        pack_args = {}
        for k in ('fill', 'expand', 'padx', 'pady', 'side'):
            if k in pack_opts:
                pack_args[k] = pack_opts.pop(k)
        if not pack_args:
            canvas.pack(fill=tk.BOTH, expand=True)
        else:
            canvas.pack(**pack_args)

        content = tk.Frame(canvas, bg=self._main_bg())
        win = canvas.create_window(0, 0, anchor='nw', window=content)

        def _on_config(e):
            try:
                w = e.width
                h = e.height
                canvas.itemconfigure(win, width=w, height=h)
            except Exception:
                pass
            try:
                self._refresh_canvas_bg(canvas)
            except Exception:
                pass

        canvas.bind('<Configure>', _on_config)
        try:
            self.root.after(50, lambda c=canvas: self._refresh_canvas_bg(c))
        except Exception:
            pass
        return canvas, content

    def _refresh_canvas_bg(self, canvas):
        try:
            if not hasattr(self, 'bg_pil') or self.bg_pil is None:
                canvas.config(bg=self._main_bg())
                return

            try:
                rx = self.root.winfo_rootx()
                ry = self.root.winfo_rooty()
                cx = canvas.winfo_rootx() - rx
                cy = canvas.winfo_rooty() - ry
            except Exception:
                cx, cy = 0, 0

            w = max(1, canvas.winfo_width())
            h = max(1, canvas.winfo_height())

            if w < 2 or h < 2:
                return

            img_w, img_h = self.bg_pil.size
            left = max(0, min(img_w, cx))
            top = max(0, min(img_h, cy))
            right = max(0, min(img_w, cx + w))
            bottom = max(0, min(img_h, cy + h))
            if right <= left or bottom <= top:
                canvas.delete('bgimg')
                canvas.config(bg=self.bg_color)
                return
            crop = self.bg_pil.crop((left, top, right, bottom))
            photo = ImageTk.PhotoImage(crop)
            self._bg_slices[canvas] = photo
            try:
                canvas.delete('bgimg')
            except Exception:
                pass
            canvas.create_image(-(left - cx), -(top - cy), image=photo, anchor='nw', tags='bgimg')
            canvas.tag_lower('bgimg')
        except Exception:
            pass

    def _refresh_example_container(self):
        try:
            if not hasattr(self, 'example_container') or self.example_container is None:
                return
            # Removed example container image and color – keep simple
            self.example_container.config(bg=self.bg_color)
        except Exception:
            pass

    def _choose_color(self):
        color_code = colorchooser.askcolor(title="Choose your accent color")
        if color_code[1]:
            self.accent_color = color_code[1]
            self.settings["accent_color"] = self.accent_color
            self._save_settings()
            self._refresh_accent_colors()

    def _apply_theme(self):
        try:
            self.root.update_idletasks()
            rw, rh = self.root.winfo_width(), self.root.winfo_height()
            if rw < 10: rw, rh = 1200, 800
            
            if self.bg_image_path and os.path.exists(self.bg_image_path):
                img = Image.open(self.bg_image_path).convert('RGBA')
                img = img.resize((rw, rh), Image.Resampling.LANCZOS)
                try:
                    d = int(self.bg_darkness)
                    if d > 0:
                        alpha = int(max(0, min(255, (d/100.0)*255)))
                        overlay = Image.new('RGBA', img.size, (0,0,0,alpha))
                        img = Image.alpha_composite(img, overlay)
                except Exception:
                    pass
                self.bg_pil = img.copy()
                self.bg_image = ImageTk.PhotoImage(img)
                if not hasattr(self, 'bg_label'):
                    self.bg_label = tk.Label(self.root, image=self.bg_image)
                    self.bg_label.place(x=0, y=0, relwidth=1, relheight=1)
                    try:
                        self.bg_label.lower()
                    except Exception:
                        pass
                else:
                    self.bg_label.config(image=self.bg_image)
                    self.bg_label.image = self.bg_image
                    try:
                        self.bg_label.place(x=0, y=0, relwidth=1, relheight=1)
                        self.bg_label.lower()
                    except Exception:
                        pass
            else:
                if hasattr(self, 'bg_label'):
                    try:
                        self.bg_label.place_forget()
                    except Exception:
                        pass
                try:
                    self.root.configure(bg=self.bg_color)
                except Exception:
                    pass
        except Exception:
            pass

        try:
            if hasattr(self, 'main_container'):
                try:
                    self.main_container.config(bg=self._main_bg())
                except Exception:
                    pass
            if hasattr(self, 'main_canvas'):
                try:
                    self.main_canvas.config(bg=self._main_bg())
                except Exception:
                    pass
            if hasattr(self, 'main_scrollable'):
                try:
                    self.main_scrollable.config(bg=self._main_bg())
                except Exception:
                    pass
            if hasattr(self, 'top'):
                try:
                    self.top.config(bg=self._main_bg())
                    self._refresh_canvas_bg(self.top)
                except Exception:
                    pass
            if hasattr(self, 'left'):
                try:
                    self.left.config(bg=self._main_bg())
                    self._refresh_canvas_bg(self.left)
                except Exception:
                    pass
            if hasattr(self, 'bottom'):
                try:
                    self.bottom.config(bg=self._main_bg())
                    self._refresh_canvas_bg(self.bottom)
                except Exception:
                    pass
            if hasattr(self, '_bg_canvases'):
                for c in self._bg_canvases:
                    try:
                        if c.winfo_exists():
                            self._refresh_canvas_bg(c)
                    except Exception:
                        pass
            try:
                if hasattr(self, 'title_label'):
                    self.title_label.config(bg=self._main_bg(), fg=self.accent_color)
            except Exception:
                pass
        except Exception:
            pass

        self._refresh_accent_colors()

        try:
            self._refresh_example_container()
        except Exception:
            pass

        try:
            st = ttk.Style()
            try:
                st.theme_use('clam')
            except Exception:
                pass
            st.configure('Larpify.Vertical.TScrollbar', troughcolor=self.bg_color, background=self.bg_color, arrowcolor=self.accent_color)
            st.configure('Larpify.Horizontal.TScrollbar', troughcolor=self.bg_color, background=self.bg_color, arrowcolor=self.accent_color)
        except Exception:
            pass

        self._center_title()
        self._update_logo_divider()

    # ------------------------------------------------------------------
    # Customization panel (simplified)
    # ------------------------------------------------------------------
    def _open_customization_panel(self):
        self._close_current_overlay()
        try:
            self._open_customization_window()
            return
        except Exception:
            pass

            tk.Label(content, text="Customize", fg=self.text_color, bg=self.bg_color, font=("Helvetica", 12, "bold")).pack(pady=(6,8))
            preview = tk.Canvas(content, width=120, height=36, highlightthickness=0, bg=self.bg_color)
            preview_rect = preview.create_rectangle(0, 0, 120, 36, fill=self.accent_color, outline="")
            preview.pack(pady=6)

            swatch_frame = tk.Frame(content, bg=self.bg_color)
            swatch_frame.pack(pady=(2,6))
            preset_colors = [self.accent_color, '#ef4444', '#f59e0b', '#10b981', '#8b5cf6', '#ec4899', '#64748b', '#111827']
            def _make_click(col):
                return lambda e: (self._set_accent_color(col), preview.itemconfig(preview_rect, fill=col))
            for ccol in preset_colors:
                c_can = tk.Canvas(swatch_frame, width=28, height=28, highlightthickness=0, bg=self.bg_color)
                c_can.create_oval(3,3,25,25, fill=ccol, outline='')
                c_can.pack(side=tk.LEFT, padx=6)
                c_can.bind('<Button-1>', _make_click(ccol))
                c_can.bind('<Enter>', lambda e: e.widget.config(cursor='hand2'))

            hex_frame = tk.Frame(content, bg=self.bg_color)
            hex_frame.pack(pady=6)
            hex_var = tk.StringVar(value=self.accent_color)
            hex_entry = tk.Entry(hex_frame, textvariable=hex_var, width=10, bg="#1b1b1b", fg=self.text_color)
            hex_entry.pack(side=tk.LEFT, padx=(6,8))
            def _apply_hex():
                v = hex_var.get().strip()
                if v and not v.startswith('#'):
                    v = '#' + v
                if len(v) == 7:
                    self._set_accent_color(v)
                    preview.itemconfig(preview_rect, fill=v)
            btn_apply = self.RoundedButton(hex_frame, text="Apply", command=_apply_hex, width=56, height=28, radius=8, bg=self.button_color, fg="white", font=("Helvetica", 9))
            btn_apply.pack(side=tk.LEFT, padx=4)
            btn_adv = self.RoundedButton(hex_frame, text="Advanced...", command=lambda: (self._choose_color(), preview.itemconfig(preview_rect, fill=self.accent_color)), width=96, height=28, radius=8, bg=self.button_color, fg="white", font=("Helvetica", 9))
            btn_adv.pack(side=tk.LEFT, padx=6)

            # Text color (new)
            tk.Label(content, text="Text color", fg=self.text_color, bg=self.bg_color, font=("Helvetica", 10)).pack(pady=(8,2))
            txt_frame = tk.Frame(content, bg=self.bg_color)
            txt_frame.pack()
            txt_var = tk.StringVar(value=self.text_color)
            txt_preview = tk.Canvas(txt_frame, width=80, height=26, highlightthickness=0, bg=self.bg_color)
            txt_rect = txt_preview.create_rectangle(0, 0, 80, 26, fill=self.text_color, outline="")
            txt_preview.pack(side=tk.LEFT, padx=6)
            txt_hex = tk.Entry(txt_frame, textvariable=txt_var, width=10, bg="#1b1b1b", fg=self.text_color)
            txt_hex.pack(side=tk.LEFT, padx=6)
            def _apply_text_color():
                v = txt_var.get().strip()
                if v and not v.startswith('#'):
                    v = '#' + v
                if len(v) == 7:
                    self._set_text_color(v)
                    txt_preview.itemconfig(txt_rect, fill=v)
            btn_txt_apply = self.RoundedButton(txt_frame, text="Apply", command=_apply_text_color, width=64, height=28, radius=8, bg=self.button_color, fg="white", font=("Helvetica", 9))
            btn_txt_apply.pack(side=tk.LEFT, padx=6)

            # Secondary color
            tk.Label(content, text="Secondary color", fg=self.text_color, bg=self.bg_color, font=("Helvetica", 10)).pack(pady=(8,2))
            sec_frame = tk.Frame(content, bg=self.bg_color)
            sec_frame.pack()
            sec_var = tk.StringVar(value=self.secondary_color)
            sec_preview = tk.Canvas(sec_frame, width=80, height=26, highlightthickness=0, bg=self.bg_color)
            sec_rect = sec_preview.create_rectangle(0, 0, 80, 26, fill=self.secondary_color, outline="")
            sec_preview.pack(side=tk.LEFT, padx=6)
            sec_hex = tk.Entry(sec_frame, textvariable=sec_var, width=10, bg="#1b1b1b", fg=self.text_color)
            sec_hex.pack(side=tk.LEFT, padx=6)
            def _apply_secondary():
                v = sec_var.get().strip()
                if v and not v.startswith('#'):
                    v = '#' + v
                if len(v) == 7:
                    self._set_secondary_color(v)
                    sec_preview.itemconfig(sec_rect, fill=v)
            btn_sec_apply = self.RoundedButton(sec_frame, text="Apply", command=_apply_secondary, width=64, height=28, radius=8, bg=self.button_color, fg="white", font=("Helvetica", 9))
            btn_sec_apply.pack(side=tk.LEFT, padx=6)

            # Button color
            tk.Label(content, text="Button color", fg=self.text_color, bg=self.bg_color, font=("Helvetica", 10)).pack(pady=(8,2))
            btnc_frame = tk.Frame(content, bg=self.bg_color)
            btnc_frame.pack()
            btnc_var = tk.StringVar(value=self.button_color)
            btnc_preview = tk.Canvas(btnc_frame, width=80, height=26, highlightthickness=0, bg=self.bg_color)
            btnc_rect = btnc_preview.create_rectangle(0, 0, 80, 26, fill=self.button_color, outline="")
            btnc_preview.pack(side=tk.LEFT, padx=6)
            btnc_hex = tk.Entry(btnc_frame, textvariable=btnc_var, width=10, bg="#1b1b1b", fg=self.text_color)
            btnc_hex.pack(side=tk.LEFT, padx=6)
            def _apply_button_color():
                v = btnc_var.get().strip()
                if v and not v.startswith('#'):
                    v = '#' + v
                if len(v) == 7:
                    self._set_button_color(v)
                    btnc_preview.itemconfig(btnc_rect, fill=v)
            btnc_apply = self.RoundedButton(btnc_frame, text="Apply", command=_apply_button_color, width=64, height=28, radius=8, bg=self.button_color, fg="white", font=("Helvetica", 9))
            btnc_apply.pack(side=tk.LEFT, padx=6)

            # Background color
            tk.Label(content, text="Background color", fg=self.text_color, bg=self.bg_color, font=("Helvetica", 10)).pack(pady=(8,2))
            bg_frame = tk.Frame(content, bg=self.bg_color)
            bg_frame.pack()
            bg_var = tk.StringVar(value=self.bg_color)
            bg_preview = tk.Canvas(bg_frame, width=120, height=26, highlightthickness=0, bg=self.bg_color)
            bg_rect = bg_preview.create_rectangle(0, 0, 120, 26, fill=self.bg_color, outline="")
            bg_preview.pack(side=tk.LEFT, padx=6)
            bg_hex = tk.Entry(bg_frame, textvariable=bg_var, width=10, bg="#1b1b1b", fg=self.text_color)
            bg_hex.pack(side=tk.LEFT, padx=6)
            def _apply_bg():
                v = bg_var.get().strip()
                if v and not v.startswith('#'):
                    v = '#' + v
                if len(v) == 7:
                    self._set_bg_color(v)
                    bg_preview.itemconfig(bg_rect, fill=v)
            btn_bg_apply = self.RoundedButton(bg_frame, text="Apply", command=_apply_bg, width=64, height=28, radius=8, bg=self.button_color, fg="white", font=("Helvetica", 9))
            btn_bg_apply.pack(side=tk.LEFT, padx=6)
            btn_bg_pick = self.RoundedButton(bg_frame, text="Pick", command=lambda: (self._choose_bg_color(bg_var, bg_preview, bg_rect)), width=56, height=28, radius=8, bg=self.button_color, fg="white", font=("Helvetica", 9))
            btn_bg_pick.pack(side=tk.LEFT, padx=6)

            # Divider settings (keep)
            tk.Label(content, text="Dividers", fg=self.text_color, bg=self.bg_color, font=("Helvetica", 10)).pack(pady=(8,2))
            div_frame = tk.Frame(content, bg=self.bg_color)
            div_frame.pack(fill=tk.X, padx=8)
            div_enabled = tk.IntVar(value=1 if self.dividers_enabled else 0)
            chk = tk.Checkbutton(div_frame, text="Show dividers", variable=div_enabled, bg=self.bg_color, fg=self.text_color, selectcolor=self.bg_color,
                                 command=lambda: self._set_dividers_enabled(div_enabled.get()))
            chk.pack(side=tk.LEFT)
            tk.Label(div_frame, text="Divider color", fg=self.text_color, bg=self.bg_color).pack(side=tk.LEFT, padx=(10,6))
            div_color_var = tk.StringVar(value=self.divider_color)
            div_entry = tk.Entry(div_frame, textvariable=div_color_var, width=10, bg="#1b1b1b", fg=self.text_color)
            div_entry.pack(side=tk.LEFT, padx=6)
            def _apply_div_color():
                v = div_color_var.get().strip()
                if v and not v.startswith('#'):
                    v = '#' + v
                if len(v) == 7:
                    self._set_divider_color(v)
            btn_div = self.RoundedButton(div_frame, text="Apply", command=_apply_div_color, width=64, height=28, radius=8, bg=self.button_color, fg="white", font=("Helvetica", 9))
            btn_div.pack(side=tk.LEFT, padx=6)

            # Removed: background darkness, shadows, avatar, example container color

            btn_reset = self.RoundedButton(content, text="Reset Theme", command=lambda: (self._reset_theme(), self._apply_theme()), width=220, height=34, radius=10, bg=self.button_color, fg="white", font=("Helvetica", 10))
            btn_reset.pack(pady=6)

            btn_close = self.RoundedButton(content, text="Close", command=lambda: (self._hide_overlay(overlay), setattr(self, '_custom_overlay', None)), width=220, height=34, radius=10, bg=self.button_color, fg="white", font=("Helvetica", 10))
            btn_close.pack(pady=10)

            target_x = 12
            start_x = -ow - 20
            overlay.place_configure(x=start_x)
            self._slide_widget(overlay, start_x, target_x)
            self._custom_overlay = overlay
            self._current_overlay = overlay
        except Exception as e:
            print(f"Customization panel error: {e}")

    def _apply_all_customization_settings(self, values):
        try:
            normalized = {}
            for key in ('accent', 'button', 'text', 'secondary', 'bg', 'divider'):
                raw = values.get(key, '')
                if isinstance(raw, str):
                    raw = raw.strip()
                if raw:
                    normalized[key] = self._normalize_color(raw) or raw

            if normalized.get('accent'):
                self.accent_color = normalized['accent']
                self.settings['accent_color'] = self.accent_color
            if normalized.get('button'):
                self.button_color = normalized['button']
                self.menu_base_color = self.button_color
                self.settings['button_color'] = self.button_color
                self.settings['menu_base_color'] = self.button_color
            if normalized.get('text'):
                self.text_color = normalized['text']
                self.settings['text_color'] = self.text_color
            if normalized.get('secondary'):
                self.secondary_color = normalized['secondary']
                self.settings['secondary_color'] = self.secondary_color
            if normalized.get('bg'):
                self.bg_color = normalized['bg']
                self.settings['bg_color'] = self.bg_color
            if normalized.get('divider'):
                self.divider_color = normalized['divider']
                self.settings['divider_color'] = self.divider_color

            self._save_settings()
            try:
                self._refresh_live_theme()
            except Exception:
                pass
            try:
                self._clear_main_content()
                self._show_search_view()
            except Exception:
                pass
        except Exception:
            pass

    def _open_customization_window(self):
        self._close_current_overlay()
        try:
            self._clear_main_content()
            try:
                self._set_active_menu(None)
            except Exception:
                pass

            try:
                if hasattr(self, '_custom_view_win') and self._custom_view_win:
                    try:
                        self.main_canvas.delete(self._custom_view_win)
                    except Exception:
                        pass
            except Exception:
                pass

            frame = tk.Frame(self.main_canvas, bg=self._main_bg())
            w = max(400, self.main_canvas.winfo_width())
            h = max(300, self.main_canvas.winfo_height())
            win_id = self.main_canvas.create_window(0, 0, anchor='nw', window=frame, width=w, height=h, tags=('custom_view',))
            self._custom_view_win = win_id

            def _on_canvas_config(e):
                try:
                    self.main_canvas.coords(self._custom_view_win, 0, 0)
                    self.main_canvas.itemconfig(self._custom_view_win, width=self.main_canvas.winfo_width(), height=self.main_canvas.winfo_height())
                except Exception:
                    pass
            try:
                self.main_canvas.bind('<Configure>', _on_canvas_config)
            except Exception:
                pass

            tk.Label(frame, text="Customize Larpify", fg=self.text_color, bg=self._main_bg(), font=("Helvetica", 14, "bold")).pack(pady=(8,12))

            # Accent color
            tk.Label(frame, text="Accent color", fg=self.text_color, bg=self._main_bg()).pack(anchor='w')
            ac_frame = tk.Frame(frame, bg=self._main_bg())
            ac_frame.pack(fill=tk.X, pady=6)
            ac_var = tk.StringVar(value=self.accent_color)
            ac_entry = tk.Entry(ac_frame, textvariable=ac_var, width=12, bg="#1b1b1b", fg=self.text_color)
            ac_entry.pack(side=tk.LEFT, padx=(0,8))
            ac_preview = tk.Canvas(ac_frame, width=28, height=20, bg=self._main_bg(), highlightthickness=0)
            ac_preview_rect = ac_preview.create_rectangle(0,0,28,20, fill=self.accent_color, outline='')
            ac_preview.pack(side=tk.LEFT, padx=(4,8))

            # Button color
            tk.Label(frame, text="Button color", fg=self.text_color, bg=self._main_bg()).pack(anchor='w')
            btn_frame_ui = tk.Frame(frame, bg=self._main_bg())
            btn_frame_ui.pack(fill=tk.X, pady=6)
            btn_var = tk.StringVar(value=self.button_color)
            btn_entry = tk.Entry(btn_frame_ui, textvariable=btn_var, width=12, bg="#1b1b1b", fg=self.text_color)
            btn_entry.pack(side=tk.LEFT, padx=(0,8))
            btn_preview = tk.Canvas(btn_frame_ui, width=28, height=20, bg=self._main_bg(), highlightthickness=0)
            btn_preview_rect = btn_preview.create_rectangle(0,0,28,20, fill=self.button_color, outline='')
            btn_preview.pack(side=tk.LEFT, padx=(4,8))
            def _pick_button():
                c = colorchooser.askcolor(title="Pick button color")
                if c and c[1]:
                    btn_var.set(c[1])
                    try:
                        btn_preview.itemconfig(btn_preview_rect, fill=c[1])
                    except Exception:
                        pass
            self.RoundedButton(btn_frame_ui, text="Pick...", command=_pick_button, width=72, height=30, radius=8, bg=self.button_color, fg="white").pack(side=tk.LEFT, padx=6)
            def _pick_accent():
                c = colorchooser.askcolor(title="Pick accent color")
                if c and c[1]:
                    ac_var.set(c[1])
                    try:
                        ac_preview.itemconfig(ac_preview_rect, fill=c[1])
                    except Exception:
                        pass
            self.RoundedButton(ac_frame, text="Pick...", command=_pick_accent, width=72, height=30, radius=8, bg=self.button_color, fg="white").pack(side=tk.LEFT, padx=6)

            # Text color (new)
            tk.Label(frame, text="Text color", fg=self.text_color, bg=self._main_bg()).pack(anchor='w')
            txt_frame = tk.Frame(frame, bg=self._main_bg())
            txt_frame.pack(fill=tk.X, pady=6)
            txt_var = tk.StringVar(value=self.text_color)
            txt_entry = tk.Entry(txt_frame, textvariable=txt_var, width=12, bg="#1b1b1b", fg=self.text_color)
            txt_entry.pack(side=tk.LEFT, padx=(0,8))
            txt_preview = tk.Canvas(txt_frame, width=28, height=20, bg=self._main_bg(), highlightthickness=0)
            txt_preview_rect = txt_preview.create_rectangle(0,0,28,20, fill=self.text_color, outline='')
            txt_preview.pack(side=tk.LEFT, padx=(4,8))
            def _pick_text():
                c = colorchooser.askcolor(title="Pick text color")
                if c and c[1]:
                    txt_var.set(c[1])
                    try:
                        txt_preview.itemconfig(txt_preview_rect, fill=c[1])
                    except Exception:
                        pass
            self.RoundedButton(txt_frame, text="Pick...", command=_pick_text, width=72, height=30, radius=8, bg=self.button_color, fg="white").pack(side=tk.LEFT, padx=6)

            # Secondary color
            tk.Label(frame, text="Secondary color", fg=self.text_color, bg=self._main_bg()).pack(anchor='w', pady=(8,0))
            sec_frame = tk.Frame(frame, bg=self._main_bg())
            sec_frame.pack(fill=tk.X, pady=6)
            sec_var = tk.StringVar(value=self.secondary_color)
            sec_entry = tk.Entry(sec_frame, textvariable=sec_var, width=12, bg="#1b1b1b", fg=self.text_color)
            sec_entry.pack(side=tk.LEFT, padx=(0,8))
            sec_preview = tk.Canvas(sec_frame, width=28, height=20, bg=self._main_bg(), highlightthickness=0)
            sec_preview_rect = sec_preview.create_rectangle(0,0,28,20, fill=self.secondary_color, outline='')
            sec_preview.pack(side=tk.LEFT, padx=(4,8))
            def _pick_sec():
                c = colorchooser.askcolor(title="Pick secondary color")
                if c and c[1]:
                    sec_var.set(c[1])
                    try:
                        sec_preview.itemconfig(sec_preview_rect, fill=c[1])
                    except Exception:
                        pass
            self.RoundedButton(sec_frame, text="Pick...", command=_pick_sec, width=72, height=30, radius=8, bg=self.button_color, fg="white").pack(side=tk.LEFT, padx=6)

            # Background color
            tk.Label(frame, text="Background color", fg=self.text_color, bg=self._main_bg()).pack(anchor='w', pady=(8,0))
            bg_frame = tk.Frame(frame, bg=self._main_bg())
            bg_frame.pack(fill=tk.X, pady=6)
            bg_var = tk.StringVar(value=self.bg_color)
            bg_entry = tk.Entry(bg_frame, textvariable=bg_var, width=12, bg="#1b1b1b", fg=self.text_color)
            bg_entry.pack(side=tk.LEFT, padx=(0,8))
            bg_preview = tk.Canvas(bg_frame, width=28, height=20, bg=self._main_bg(), highlightthickness=0)
            bg_preview_rect = bg_preview.create_rectangle(0,0,28,20, fill=self.bg_color, outline='')
            bg_preview.pack(side=tk.LEFT, padx=(4,8))
            def _pick_bg():
                c = colorchooser.askcolor(title="Pick background color")
                if c and c[1]:
                    bg_var.set(c[1])
                    try:
                        bg_preview.itemconfig(bg_preview_rect, fill=c[1])
                    except Exception:
                        pass
            self.RoundedButton(bg_frame, text="Pick...", command=_pick_bg, width=72, height=30, radius=8, bg=self.button_color, fg="white").pack(side=tk.LEFT, padx=6)

            # Divider settings
            tk.Label(frame, text="Dividers", fg=self.text_color, bg=self._main_bg()).pack(anchor='w', pady=(8,0))
            div_frame = tk.Frame(frame, bg=self._main_bg())
            div_frame.pack(fill=tk.X, pady=6)
            div_enabled = tk.IntVar(value=1 if self.dividers_enabled else 0)
            chk = tk.Checkbutton(div_frame, text="Show dividers", variable=div_enabled, bg=self.bg_color, fg=self.text_color, selectcolor=self.bg_color,
                                 command=lambda: self._set_dividers_enabled(div_enabled.get()))
            chk.pack(side=tk.LEFT, padx=(0,10))
            tk.Label(div_frame, text="Divider color", fg=self.text_color, bg=self._main_bg()).pack(side=tk.LEFT, padx=(0,6))
            div_color_var = tk.StringVar(value=self.divider_color)
            div_entry = tk.Entry(div_frame, textvariable=div_color_var, width=10, bg="#1b1b1b", fg=self.text_color)
            div_entry.pack(side=tk.LEFT, padx=(0,8))

            # Removed: background darkness, shadows, avatar, example container color

            btn_row = tk.Frame(frame, bg=self._main_bg())
            btn_row.pack(pady=12)
            def _apply_all():
                values = {
                    'accent': ac_var.get().strip(),
                    'button': btn_var.get().strip(),
                    'text': txt_var.get().strip(),
                    'secondary': sec_var.get().strip(),
                    'bg': bg_var.get().strip(),
                    'divider': div_color_var.get().strip(),
                }
                self._apply_all_customization_settings(values)
                # Force app restart to ensure all components are re-initialized with new theme
                try:
                    pygame.mixer.quit()
                    self.root.destroy()
                except:
                    pass
                os.execv(sys.executable, [sys.executable] + sys.argv)

            self.RoundedButton(btn_row, text="Apply All", command=_apply_all, width=180, height=36, radius=10, bg=self.button_color, fg="white").pack(side=tk.LEFT, padx=6)
            self.RoundedButton(btn_row, text="Reset Theme", command=lambda: (self._reset_theme(), self._apply_theme()), width=160, height=36, radius=10, bg=self.button_color, fg="white").pack(side=tk.LEFT, padx=6)
            self.RoundedButton(btn_row, text="Close", command=lambda: (self.main_canvas.delete(self._custom_view_win), setattr(self, '_custom_view_win', None), self._show_search_view()), width=120, height=36, radius=10, bg=self.button_color, fg="white").pack(side=tk.LEFT, padx=6)

        except Exception as e:
            print(f"Customization view error: {e}")

    def _show_profile_popup(self):
        popup = tk.Toplevel(self.root)
        popup.title("Profile")
        popup.geometry("300x400")
        popup.configure(bg=self.bg_color)
        avatar_label = tk.Label(popup, text="🖼️", font=("Segoe UI Emoji", 60), bg=self.bg_color, fg=self.eye_color)
        avatar_label.pack(pady=10)
        if self.avatar_path and os.path.exists(self.avatar_path):
            try:
                img = Image.open(self.avatar_path)
                img = img.resize((100, 100), Image.Resampling.LANCZOS)
                avatar_img = ImageTk.PhotoImage(img)
                avatar_label.config(image=avatar_img, text="")
                avatar_label.image = avatar_img
            except:
                pass
        self.RoundedButton(popup, text="Change Avatar", command=self._change_avatar, width=220, height=36, radius=10, bg=self.button_color, fg="white").pack(pady=5)
        self.RoundedButton(popup, text="Reset to Default", command=self._reset_theme, width=220, height=36, radius=10, bg=self.button_color, fg="white").pack(pady=5)

    def _change_avatar(self):
        file = filedialog.askopenfilename(filetypes=[("Image files", "*.png *.jpg *.jpeg *.gif")])
        if file:
            self.settings["avatar"] = file
            self.avatar_path = file
            self._save_settings()

    def _change_bg_image(self):
        file = filedialog.askopenfilename(filetypes=[("Image files", "*.png *.jpg *.jpeg *.gif")])
        if file:
            self.settings["bg_image"] = file
            self.bg_image_path = file
            self._save_settings()
            self._apply_theme()

    def _reset_theme(self):
        defaults = default_settings()
        self.settings.update(defaults)
        self.settings.pop("bg_image", None)
        self.settings.pop("avatar", None)
        self.bg_image_path = None
        self.avatar_path = None
        self.accent_color = defaults['accent_color']
        self.secondary_color = defaults['secondary_color']
        self.text_color = defaults['text_color']
        self.button_color = defaults['button_color']
        self.menu_base_color = defaults['menu_base_color']
        self.bg_color = defaults['bg_color']
        self.divider_color = defaults['divider_color']
        self.dividers_enabled = defaults['dividers_enabled']
        self.shadows_enabled = defaults['shadows_enabled']
        self.shadow_intensity = defaults['shadow_intensity']
        self.slider_style = defaults['slider_style']
        self.bg_darkness = defaults['bg_darkness']
        self._save_settings()
        self._apply_theme()
        messagebox.showinfo("Reset", "Theme reset to default.")

    def _set_example_container_color(self, color):
        # No longer used
        pass

    def _change_example_container_image(self):
        # No longer used
        pass

    # ---------- UI Layout ----------
    def _create_layout(self):
        self.root.grid_rowconfigure(0, weight=0)
        self.root.grid_rowconfigure(1, weight=1)
        self.root.grid_rowconfigure(2, weight=0)
        self.root.grid_columnconfigure(0, weight=0)
        self.root.grid_columnconfigure(1, weight=1)

    def _create_top_bar(self):
        self.top = tk.Canvas(self.root, bg=self._main_bg(), height=60, highlightthickness=0)
        self.top.grid(row=0, column=0, columnspan=2, sticky="ew")
        self.top.grid_propagate(False)
        self._bg_canvases.append(self.top)
        self.root.after(50, lambda c=self.top: self._refresh_canvas_bg(c))
        try:
            self.top.bind('<MouseWheel>', lambda e: 'break')
        except Exception:
            pass

        self.title_label = tk.Label(self.top, text="🎵 LARPIFY", fg=self.button_color, bg=self._main_bg(),
                        font=("Helvetica", 18, "bold"), cursor="hand2")
        self.title_label_win = self.top.create_window(0, 15, window=self.title_label, anchor="n")

        # Initialize divider objects
        self.top_divider_line = self.top.create_line(0, 0, 0, 0, fill=self.divider_color, width=1, tags='top_divider')
        self.side_sep = self.top.create_line(0, 0, 0, 0, fill=self.divider_color, width=1, tags='side_sep')

        def _center_title(e=None):
            try:
                w = max(1, self.top.winfo_width())
                self.top.coords(self.title_label_win, w//2, 15)
                # Update vertical separator to bridge gap with sidebar
                if self.dividers_enabled:
                    self.top.coords(self.side_sep, 220, 0, 220, self.top.winfo_height())
                    self.top.itemconfig(self.side_sep, state='normal')
                else:
                    self.top.itemconfig(self.side_sep, state='hidden')
            except Exception:
                pass
        self.top.bind('<Configure>', lambda e: (_center_title(e), self._refresh_canvas_bg(self.top), self._draw_top_divider(e)))
        self._center_title = _center_title
        self.root.after(50, _center_title)

        self.title_label.bind("<Button-1>", lambda e: self._show_queue_view())
        try:
            self.title_label.bind("<Button-3>", lambda e: self._open_customization_window())
        except Exception:
            pass

        # Additional divider below the logo (light gray line)
        self.logo_divider = self.top.create_line(0, 0, 0, 0, fill=self.divider_color, width=1, tags='logo_divider')
        self._update_logo_divider()

    def _update_topmost_divider(self):
        if not hasattr(self, 'top') or not self.top.winfo_exists():
            return
        if not self.dividers_enabled:
            try:
                self.top.itemconfig(self.top_divider_line, state='hidden')
            except:
                pass
            return
        try:
            w = self.top.winfo_width()
            h = self.top.winfo_height()
            y = h - 1 # Position at the bottom of the header bar
            self.top.coords(self.top_divider_line, 0, y, w, y)
            self.top.itemconfig(self.top_divider_line, fill=self.divider_color, state='normal')
        except:
            pass

    def _update_logo_divider(self):
        if not hasattr(self, 'top') or not self.top.winfo_exists():
            return
        if not self.dividers_enabled:
            try:
                self.top.itemconfig(self.logo_divider, state='hidden')
            except:
                pass
            return
        try:
            y = 45  # below the title (which is at y=15 + font height ~30)
            w = self.top.winfo_width()
            self.top.coords(self.logo_divider, 0, y, w, y)
            self.top.itemconfig(self.logo_divider, fill=self.divider_color, state='normal')
        except:
            pass

    def _draw_top_divider(self, event):
        # Vertical divider to continue from sidebar
        if self.dividers_enabled:
             self.top.coords(self.side_sep, 220, 0, 220, event.height)
             self.top.itemconfig(self.side_sep, state='normal')
        else:
             self.top.itemconfig(self.side_sep, state='hidden')
             
        self._update_logo_divider()
        self._update_topmost_divider()

    def _create_left_sidebar(self):
        self.left = tk.Canvas(self.root, bg=self._main_bg(), width=220, highlightthickness=0)
        self.left.grid(row=1, column=0, sticky="ns", padx=(0, 2))
        self.left.grid_propagate(False)

        self.left.bind('<Configure>', lambda e: (self._refresh_canvas_bg(self.left), self._draw_left_divider(e)))
        self._bg_canvases.append(self.left)
        self.root.after(50, lambda c=self.left: self._refresh_canvas_bg(c))
        try:
            self.left.bind('<MouseWheel>', lambda e: 'break')
        except Exception:
            pass

        self.left_custom_btn = self.RoundedButton(self.left, text="Customize", command=self._open_customization_window,
                              width=196, height=44, radius=12, bg=self.button_color, fg="white", font=("Helvetica", 11))
        self.left.create_window(12, 12, window=self.left_custom_btn, anchor="nw")

        menu_items = ["Search", "Queue", "Playlists", "Library"]
        self.menu_buttons = {}
        y_offset = 12 + 44 + 8
        for text in menu_items:
            btn = self.RoundedButton(self.left, text=text, bg=self.button_color, fg="white",
                                     width=196, height=44, radius=12, font=("Helvetica", 12))
            self.left.create_window(12, y_offset, window=btn, anchor="nw")
            y_offset += 44 + 8
            btn.config(command=lambda t=text: self._activate_menu(t))
            btn.bind('<Enter>', lambda e, b=btn: b.config(bg=self._lighter_color(self.button_color, 0.85)))
            btn.bind('<Leave>', lambda e, b=btn: b.config(bg=self.button_color if self._active_menu != text else self._lighter_color(self.button_color, 0.85)))
            self.menu_buttons[text] = btn

        self._active_menu = None

    def _draw_left_divider(self, event):
        try:
            self.left.delete('divider_left')
            if self.dividers_enabled:
                x = event.width - 1
                self.left.create_line(x, 0, x, event.height, fill=self.divider_color, width=1, tags='divider_left')
        except Exception:
            pass

    def _activate_menu(self, name):
        try:
            mapping = {
                'Search': self._show_search_view,
                'Queue': self._show_queue_view,
                'Playlists': self._show_playlists_view,
                'Library': self._show_library_view,
            }
            func = mapping.get(name)
            if callable(func):
                func()
            self._set_active_menu(name)
        except Exception:
            pass

    def _set_active_menu(self, name):
        try:
            self._active_menu = name
            for n, btn in getattr(self, 'menu_buttons', {}).items():
                try:
                    if n == name:
                        btn.config(fg='white', bg=self._lighter_color(self.button_color, 0.85))
                    else:
                        btn.config(fg='white', bg=self.button_color)
                except Exception:
                    pass
        except Exception:
            pass

    def _create_main_area(self):
        self.main_placeholder = tk.Canvas(self.root, bg=self._main_bg(), highlightthickness=0)
        self.main_placeholder.grid(row=1, column=1, sticky="nsew", padx=10, pady=10)
        self.main_placeholder.grid_rowconfigure(0, weight=1)
        self.main_placeholder.grid_columnconfigure(0, weight=1)

        self.main_placeholder.bind('<Configure>', lambda e: self._refresh_canvas_bg(self.main_placeholder))
        self._bg_canvases.append(self.main_placeholder)
        self.root.after(50, lambda c=self.main_placeholder: self._refresh_canvas_bg(c))

        self._ensure_main_toplevel()

        # Example container (kept for compatibility but not used)
        try:
            self.example_container = tk.Frame(self.main_canvas, bg=self.bg_color, width=820, height=420)
            self.example_container_win = self.main_canvas.create_window(20, 20, window=self.example_container, anchor='nw')

            def _position_example(e=None):
                try:
                    w = max(1, self.main_canvas.winfo_width())
                    h = max(1, self.main_canvas.winfo_height())
                    ex_w = 820
                    ex_h = 420
                    x = max(20, (w - ex_w) // 2)
                    y = max(20, (h - ex_h) // 2)
                    self.main_canvas.coords(self.example_container_win, x, y)
                except Exception:
                    pass

            try:
                self.main_canvas.bind('<Configure>', lambda e: (_position_example(e), self._refresh_canvas_bg(self.main_canvas)))
            except Exception:
                pass

            self.root.after(80, _position_example)
            self._refresh_example_container()
        except Exception:
            pass

    def _create_bottom_control_bar(self):
        self.bottom = tk.Canvas(self.root, bg=self._main_bg(), height=100, highlightthickness=0)
        self.bottom.grid(row=2, column=0, columnspan=2, sticky="ew")
        self.bottom.grid_propagate(False)

        def _on_bottom_config(e):
            try:
                self._refresh_canvas_bg(self.bottom)
            except Exception:
                pass
            try:
                w = max(200, e.width - 40)
                if hasattr(self, 'song_info_win'):
                    try:
                        self.bottom.itemconfigure(self.song_info_win, width=w)
                    except Exception:
                        pass
                if hasattr(self, 'seek_frame_win'):
                    try:
                        self.bottom.itemconfigure(self.seek_frame_win, width=w)
                    except Exception:
                        pass
                if hasattr(self, 'controls_row_win'):
                    try:
                        self.bottom.coords(self.controls_row_win, 20, 55)
                        try:
                            self.bottom.itemconfigure(self.controls_row_win, width=w)
                        except Exception:
                            pass
                    except Exception:
                        pass
            except Exception:
                pass
            self._draw_bottom_divider(e)

        self.bottom.bind('<Configure>', _on_bottom_config)
        self._bg_canvases.append(self.bottom)
        self.root.after(50, lambda c=self.bottom: self._refresh_canvas_bg(c))
        try:
            self.bottom.bind('<MouseWheel>', lambda e: 'break')
        except Exception:
            pass

        self.song_info_label = tk.Label(self.bottom, text="Not playing", fg=self.text_color, bg=self._main_bg(), 
                                        font=("Helvetica", 10), anchor="w")
        self.song_info_win = self.bottom.create_window(20, 5, window=self.song_info_label, anchor="nw", width=self.root.winfo_width()-40)

        seek_frame = tk.Frame(self.bottom, bg=self._main_bg(), highlightthickness=0)
        self.current_time_label = tk.Label(seek_frame, text="0:00", fg=self.text_color, bg=self._main_bg(), font=("Helvetica", 9))
        self.current_time_label.pack(side=tk.LEFT)
        self.seek_bar = self.CustomSlider(seek_frame, from_=0, to=100, orient=tk.HORIZONTAL, length=600, height=12, accent=self.secondary_color)
        self.seek_bar.bind("<ButtonPress-1>", self._on_seek_press)
        self.seek_bar.bind("<B1-Motion>", self._on_seek_drag)
        self.seek_bar.bind("<ButtonRelease-1>", self._on_seek_release)
        self.seek_bar.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=10)
        self.total_time_label = tk.Label(seek_frame, text="0:00", fg=self.text_color, bg=self._main_bg(), font=("Helvetica", 9))
        self.total_time_label.pack(side=tk.RIGHT)
        self.seek_frame_win = self.bottom.create_window(20, 30, window=seek_frame, anchor="nw", width=self.root.winfo_width()-40)

        controls_row = tk.Frame(self.bottom, bg=self._main_bg(), highlightthickness=0)

        control_frame = tk.Frame(controls_row, bg=self._main_bg())
        control_frame.pack(side=tk.LEFT)

        btn_width = 54
        btn_height = 40
        self.prev_btn = self.RoundedButton(control_frame, text="⏮", command=self._prev_song,
            width=btn_width, height=btn_height, radius=12, bg=self.button_color, fg="white", font=("Helvetica", 14))
        self.prev_btn.pack(side=tk.LEFT, padx=6)

        self.play_pause_btn = self.RoundedButton(control_frame, text="⏸", command=self._toggle_play_pause,
                width=64, height=44, radius=16, bg=self.button_color, fg="white", font=("Helvetica", 14))
        self.play_pause_btn.pack(side=tk.LEFT, padx=6)

        self.next_btn = self.RoundedButton(control_frame, text="⏭", command=self._next_song,
            width=btn_width, height=btn_height, radius=12, bg=self.button_color, fg="white", font=("Helvetica", 14))
        self.next_btn.pack(side=tk.LEFT, padx=6)

        self.shuffle_btn = self.RoundedButton(control_frame, text="🔀", command=self._toggle_shuffle,
              width=btn_width, height=btn_height, radius=12, bg=self.button_color, fg="white", font=("Helvetica", 12))
        self.shuffle_btn.pack(side=tk.LEFT, padx=6)

        right_frame = tk.Frame(controls_row, bg=self._main_bg())
        right_frame.pack(side=tk.RIGHT)
        self.volume_icon_label = tk.Label(right_frame, text="🔊", bg=self._main_bg(), fg=self.text_color, font=("Segoe UI Emoji", 12))
        self.volume_icon_label.pack(side=tk.LEFT)
        self.volume_slider = self.CustomSlider(right_frame, from_=0, to=100, orient=tk.HORIZONTAL, length=140, height=12, accent=self.accent_color, command=self._set_volume)
        self.volume_slider.set(80)
        self.volume_slider.pack(side=tk.LEFT, padx=6)
        self.volume_pct_label = tk.Label(right_frame, text="80%", fg=self.text_color, bg=self._main_bg(), font=("Helvetica", 9))
        self.volume_pct_label.pack(side=tk.LEFT, padx=(4,12))
        pygame.mixer.music.set_volume(0.8)

        self.RoundedButton(right_frame, text="📀 Add to Playlist", command=self._add_current_song_to_playlist, width=160, height=34, radius=10, bg=self.button_color, fg="white").pack(side=tk.LEFT, padx=12)
        self.RoundedButton(right_frame, text="💾 Keep Download", command=self._keep_current_song, width=160, height=34, radius=10, bg=self.button_color, fg="white").pack(side=tk.LEFT, padx=12)

        self.popout_btn = self.RoundedButton(right_frame, text="📌 Pop out", command=self._open_popout,
            width=btn_width, height=btn_height, radius=12, bg=self.button_color, fg="white", font=("Helvetica", 10))
        self.popout_btn.pack(side=tk.LEFT, padx=14)

        self.device_btn = self.RoundedButton(right_frame, text="🎧 Output", command=self._show_output_device_dialog,
            width=btn_width, height=btn_height, radius=12, bg=self.button_color, fg="white", font=("Helvetica", 10))
        self.device_btn.pack(side=tk.LEFT, padx=5)

        self.controls_row_win = self.bottom.create_window(20, 55, window=controls_row, anchor="nw", width=self.root.winfo_width()-40)

    def _draw_bottom_divider(self, event):
        try:
            self.bottom.delete('divider_bottom')
            if self.dividers_enabled:
                y = 0
                self.bottom.create_line(0, y, event.width, y, fill=self.divider_color, width=1, tags='divider_bottom')
        except Exception:
            pass

    def _list_output_devices(self):
        try:
            import sounddevice as sd
            devs = sd.query_devices()
            seen = set()
            outs = []
            for i, d in enumerate(devs):
                try:
                    if d.get('max_output_channels', 0) <= 0:
                        continue
                    name = d.get('name') or f"Device {i}"
                    if name in seen:
                        continue
                    seen.add(name)
                    outs.append((i, name))
                except Exception:
                    continue
            return outs
        except Exception:
            return []

    def _ensure_soundvolumeview(self):
        # Download NirSoft SoundVolumeView if not present; return path to exe or None
        svv_name = "SoundVolumeView.exe"
        svv_path = os.path.join(os.getcwd(), svv_name)
        if os.path.exists(svv_path):
            return svv_path
        try:
            url = "https://www.nirsoft.net/utils/soundvolumeview.zip"
            tmp_zip = os.path.join(TEMP_DIR, "svv.zip")
            urllib.request.urlretrieve(url, tmp_zip)
            with zipfile.ZipFile(tmp_zip, 'r') as z:
                for name in z.namelist():
                    if name.lower().endswith(svv_name.lower()):
                        z.extract(name, os.getcwd())
                        extracted = os.path.join(os.getcwd(), name)
                        # Move to root if it's inside a folder
                        if extracted != svv_path:
                            try:
                                shutil.move(extracted, svv_path)
                            except Exception:
                                pass
                        break
            try:
                os.remove(tmp_zip)
            except Exception:
                pass
            if os.path.exists(svv_path):
                return svv_path
        except Exception:
            pass
        return None

    def _set_default_device_with_svv(self, device_name):
        svv = self._ensure_soundvolumeview()
        if not svv:
            return False, "SoundVolumeView not available"
        try:
            # /SetDefault "Device Name" 0  -> set as default playback device
            subprocess.check_call([svv, '/SetDefault', device_name, '0'])
            return True, None
        except Exception as e:
            return False, str(e)

    def _show_output_device_dialog(self):
        try:
            devices = self._list_output_devices()
            dlg = tk.Toplevel(self.root)
            dlg.title("Output Device")
            dlg.geometry("520x340")
            dlg.transient(self.root)

            tk.Label(dlg, text="Select an output device:", font=("Helvetica", 10, "bold")).pack(anchor="w", padx=12, pady=(10,4))

            list_frame = tk.Frame(dlg)
            list_frame.pack(fill=tk.BOTH, expand=True, padx=12)

            lb = tk.Listbox(list_frame, activestyle='none')
            lb.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
            for idx, name in devices:
                lb.insert(tk.END, name)

            sb = tk.Scrollbar(list_frame, command=lb.yview)
            sb.pack(side=tk.RIGHT, fill=tk.Y)
            lb.config(yscrollcommand=sb.set)

            status = tk.Label(dlg, text="", fg="#f3f4f6", bg=self._main_bg())
            status.pack(fill=tk.X, padx=12, pady=(6,0))

            def on_set_default():
                sel = lb.curselection()
                if not sel:
                    status.config(text="Select a device first")
                    return
                name = lb.get(sel[0])
                status.config(text="Setting default device...")
                dlg.update()
                ok, err = self._set_default_device_with_svv(name)
                if ok:
                    status.config(text=f"Default device set to: {name}")
                    self.current_output_device = name
                    try:
                        pygame.mixer.quit()
                    except Exception:
                        pass
                    try:
                        pygame.mixer.init()
                        pygame.mixer.music.set_volume(getattr(self, 'volume', 0.8))
                    except Exception:
                        pass
                else:
                    status.config(text=f"Failed: {err}")

            btn_frame = tk.Frame(dlg)
            btn_frame.pack(fill=tk.X, padx=12, pady=10)
            tk.Button(btn_frame, text="Set as Default", command=on_set_default, width=16).pack(side=tk.LEFT)
            tk.Button(btn_frame, text="Download SoundVolumeView", command=lambda: (self._ensure_soundvolumeview(), status.config(text="Downloaded (or already present).")), width=22).pack(side=tk.LEFT, padx=8)
            tk.Button(btn_frame, text="Close", command=dlg.destroy).pack(side=tk.RIGHT)
        except Exception:
            pass

    # ---------- Seek bar events ----------
    def _on_seek_press(self, event):
        self._was_playing = self.is_playing
        self.seeking = True
        try:
            w = event.widget.winfo_width()
            if w > 0:
                ratio = max(0.0, min(1.0, event.x / float(w)))
                value = ratio * 100.0
                self.seek_bar.set(value)
                if self.current_duration:
                    pos_sec = (value / 100.0) * self.current_duration
                    cur_min = int(pos_sec // 60)
                    cur_sec = int(pos_sec % 60)
                    self.current_time_label.config(text=f"{cur_min}:{cur_sec:02d}")
        except Exception:
            pass

    def _on_seek_drag(self, event):
        if not self.current_duration:
            return
        value = self.seek_bar.get()
        pos_sec = (value / 100.0) * self.current_duration
        cur_min = int(pos_sec // 60)
        cur_sec = int(pos_sec % 60)
        self.current_time_label.config(text=f"{cur_min}:{cur_sec:02d}")

    def _on_seek_release(self, event):
        self.seeking = False
        value = self.seek_bar.get()
        resume = getattr(self, '_was_playing', True)
        self._perform_seek(value, resume=resume)

    def _perform_seek(self, value, resume=True):
        if self.current_duration <= 0 or not self.current_song_path:
            return
        pos_sec = (value / 100.0) * self.current_duration
        try:
            pygame.mixer.music.stop()
            pygame.mixer.music.load(self.current_song_path)
            pygame.mixer.music.play(0, pos_sec)
            self._play_start_offset = pos_sec
            if resume:
                self._play_start_time = time.monotonic()
            else:
                pygame.mixer.music.pause()
                self._play_start_time = None
            self.is_playing = bool(resume)
            self.play_pause_btn.config(text="⏸" if self.is_playing else "▶")
        except Exception:
            try:
                pygame.mixer.music.stop()
                pygame.mixer.music.load(self.current_song_path)
                pygame.mixer.music.play(start=pos_sec)
                self._play_start_offset = pos_sec
                if resume:
                    self._play_start_time = time.monotonic()
                else:
                    pygame.mixer.music.pause()
                    self._play_start_time = None
                self.is_playing = bool(resume)
                self.play_pause_btn.config(text="⏸" if self.is_playing else "▶")
            except Exception:
                pygame.mixer.music.stop()
                pygame.mixer.music.load(self.current_song_path)
                pygame.mixer.music.play()
                if resume:
                    self._play_start_offset = 0.0
                    self._play_start_time = time.monotonic()
                    self.is_playing = True
                else:
                    self._play_start_offset = 0.0
                    self._play_start_time = None
                    pygame.mixer.music.pause()
                    self.is_playing = False
                self.play_pause_btn.config(text="⏸" if self.is_playing else "▶")
        cur_min = int(pos_sec // 60)
        cur_sec = int(pos_sec % 60)
        self.current_time_label.config(text=f"{cur_min}:{cur_sec:02d}")

    def _update_seek_display(self):
        if self.seeking:
            return
        try:
            if self.is_playing and self._play_start_time is not None:
                pos_sec = self._play_start_offset + (time.monotonic() - self._play_start_time)
            else:
                pos_sec = self._play_start_offset
        except Exception:
            pos_ms = pygame.mixer.music.get_pos()
            if pos_ms == -1:
                return
            pos_sec = pos_ms / 1000.0

        if self.current_duration > 0:
            if pos_sec < 0:
                pos_sec = 0.0
            if pos_sec > self.current_duration:
                pos_sec = self.current_duration
            percent = (pos_sec / self.current_duration) * 100
            self.seek_bar.set(percent)
            cur_min = int(pos_sec // 60)
            cur_sec = int(pos_sec % 60)
            self.current_time_label.config(text=f"{cur_min}:{cur_sec:02d}")
            if self.popout_window and self.popout_window.winfo_exists():
                try:
                    self.popout_seek.set(percent)
                    self.popout_current.config(text=f"{cur_min}:{cur_sec:02d}")
                except Exception:
                    pass

    # ---------- Pop‑out window ----------
    def _open_popout(self):
        if self.popout_window and self.popout_window.winfo_exists():
            self.popout_window.lift()
            return
        self.popout_window = tk.Toplevel(self.root)
        self.popout_window.title("Larpify Controls")
        self.popout_window.geometry("500x350")
        self.popout_window.configure(bg=self.bg_color)
        self.popout_window.protocol("WM_DELETE_WINDOW", self._close_popout)
        frame = tk.Frame(self.popout_window, bg=self.bg_color)
        frame.pack(expand=True, fill=tk.BOTH, padx=10, pady=10)

        lbl = tk.Label(frame, text="Now playing", fg=self.text_color, bg=self.bg_color, font=("Helvetica", 10))
        lbl.pack(pady=5)
        self.popout_info = tk.Label(frame, text="Not playing", fg=self.accent_color, bg=self.bg_color,
                                    font=("Helvetica", 9))
        self.popout_info.pack(pady=5)

        seek_frame = tk.Frame(frame, bg=self.bg_color)
        seek_frame.pack(fill=tk.X, pady=10)
        self.popout_current = tk.Label(seek_frame, text="0:00", fg=self.text_color, bg=self.bg_color)
        self.popout_current.pack(side=tk.LEFT)
        self.popout_seek = self.CustomSlider(seek_frame, from_=0, to=100, orient=tk.HORIZONTAL, length=420, height=12, accent=self.secondary_color)
        self.popout_seek.bind("<ButtonPress-1>", self._on_popout_seek_press)
        self.popout_seek.bind("<B1-Motion>", self._on_popout_seek_drag)
        self.popout_seek.bind("<ButtonRelease-1>", self._on_popout_seek_release)
        self.popout_seek.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=10)
        self.popout_total = tk.Label(seek_frame, text="0:00", fg=self.text_color, bg=self.bg_color)
        self.popout_total.pack(side=tk.RIGHT)
        btn_frame = tk.Frame(frame, bg=self.bg_color)
        btn_frame.pack(pady=10)
        self.RoundedButton(btn_frame, text="⏮", command=self._prev_song, width=48, height=32, radius=10, bg=self.button_color, fg="white").pack(side=tk.LEFT, padx=5)
        self.popout_play = self.RoundedButton(btn_frame, text="⏸", command=self._toggle_play_pause,
                             width=64, height=40, radius=14, bg=self.accent_color, fg="white", font=("Helvetica", 14))
        self.popout_play.pack(side=tk.LEFT, padx=5)
        self.RoundedButton(btn_frame, text="⏭", command=self._next_song, width=48, height=32, radius=10, bg=self.button_color, fg="white").pack(side=tk.LEFT, padx=5)
        self.RoundedButton(btn_frame, text="🔀", command=self._toggle_shuffle, width=48, height=32, radius=10, bg=self.button_color, fg="white").pack(side=tk.LEFT, padx=5)
        self.RoundedButton(btn_frame, text="📀 Add to Playlist", command=self._add_current_song_to_playlist, width=140, height=34, radius=10, bg=self.button_color, fg="white").pack(side=tk.LEFT, padx=10)

        vol_frame = tk.Frame(frame, bg=self.bg_color)
        vol_frame.pack(pady=10)
        tk.Label(vol_frame, text="Volume", fg=self.text_color, bg=self.bg_color).pack(side=tk.LEFT)
        self.popout_volume = self.CustomSlider(vol_frame, from_=0, to=100, orient=tk.HORIZONTAL, length=140, height=12, accent=self.secondary_color, command=self._set_volume)
        self.popout_volume.set(80)
        self.popout_volume.pack(side=tk.LEFT, padx=10)
        self.popout_volume_label = tk.Label(vol_frame, text="80%", fg=self.text_color, bg=self.bg_color, font=("Helvetica", 9))
        self.popout_volume_label.pack(side=tk.LEFT, padx=(8,0))

        self._update_popout()

    def _update_popout(self):
        if self.popout_window and self.popout_window.winfo_exists():
            if self.queue_index >= 0 and self.queue_index < len(self.queue):
                song = self.queue[self.queue_index]
                self.popout_info.config(text=f"{song['title']} - {song['artist']}")
            else:
                self.popout_info.config(text="Not playing")
            self.popout_play.config(text="⏸" if self.is_playing else "▶")
            self.popout_volume.set(self.volume_slider.get())
            self.popout_seek.set(self.seek_bar.get())
            self.popout_current.config(text=self.current_time_label.cget("text"))
            self.popout_total.config(text=self.total_time_label.cget("text"))
            self.popout_window.after(500, self._update_popout)

    def _close_popout(self):
        if self.popout_window:
            self.popout_window.destroy()
            self.popout_window = None

    def _on_popout_seek_press(self, event):
        self.seeking = True

    def _on_popout_seek_drag(self, event):
        if not self.current_duration:
            return
        value = self.popout_seek.get()
        pos_sec = (value / 100.0) * self.current_duration
        cur_min = int(pos_sec // 60)
        cur_sec = int(pos_sec % 60)
        self.popout_current.config(text=f"{cur_min}:{cur_sec:02d}")

    def _on_popout_seek_release(self, event):
        self.seeking = False
        value = self.popout_seek.get()
        self._perform_seek(value)

    # ---------- Player core ----------
    def _add_current_song_to_playlist(self):
        if self.queue_index < 0 or self.queue_index >= len(self.queue):
            messagebox.showinfo("No song", "No song is currently playing.")
            return
        song = self.queue[self.queue_index]
        self._add_song_to_playlist_dialog(song)

    def _keep_current_song(self):
        if self.queue_index < 0 or self.queue_index >= len(self.queue):
            messagebox.showinfo("No song", "No song is currently playing.")
            return
        song = self.queue[self.queue_index]
        self._permanently_keep_song(song)

    def _add_to_queue(self, song, is_temporary=True):
        song['is_temporary'] = is_temporary
        self.queue.append(song)
        self._refresh_queue_display()
        if self.queue_index == -1 and not self.is_playing:
            self._play_song_index(0)
        try:
            if self.queue_index >= 0:
                nxt = self.queue_index + 1
                if nxt < len(self.queue):
                    def dl_next(s=self.queue[nxt]):
                        try:
                            path = download_song_to_folder(s['videoId'], s['title'], s.get('artist',''), TEMP_DIR)
                            s['filepath'] = path
                        except Exception:
                            pass
                    threading.Thread(target=dl_next, daemon=True).start()
        except Exception:
            pass

    def _refresh_queue_display(self):
        try:
            if not hasattr(self, 'queue_display_canvas') or not self.queue_display_canvas.winfo_exists():
                return
        except Exception:
            return

        try:
            self.queue_display_canvas.delete('queue_item')
        except Exception:
            pass

        if not self.queue:
            self.queue_display_canvas.create_text(self.queue_display_canvas.winfo_width()//2, 120, text="Queue is empty. Add songs from Search or Library.",
                                         fill=self.text_color, font=("Helvetica", 12), tags=('queue_item',))
            return

        y = 20
        canvas_w = max(800, self.queue_display_canvas.winfo_width())
        if self.queue_index >= 0 and self.queue_index < len(self.queue):
            current = self.queue[self.queue_index]
            try:
                banner_w = min(820, canvas_w - 40)
                bx1 = 20
                bx2 = bx1 + banner_w
                self.queue_display_canvas.create_rectangle(bx1, y, bx2, y+64, fill=self.accent_color, outline='', tags=('queue_item',))
                self.queue_display_canvas.create_text(bx1+12, y+6, text="▶ NOW PLAYING", anchor='nw', fill='white', font=("Helvetica", 10, 'bold'), tags=('queue_item',))
                self.queue_display_canvas.create_text(bx1+12, y+30, text=f"{current['title']} - {current.get('artist','')}", anchor='nw', fill='white', font=("Helvetica", 11), tags=('queue_item',))
                y += 64 + 10
            except Exception:
                pass

        self.queue_display_canvas.create_text(20, y, text="Queue", anchor='nw', fill=self.text_color, font=("Helvetica", 12, 'bold'), tags=('queue_item',))
        y += 28

        for idx, song in enumerate(self.queue):
            if idx == self.queue_index:
                continue
            row_tag = f'queue_row_{idx}'
            self.queue_display_canvas.create_text(30, y+12, text=f"{song.get('title','')} - {song.get('artist','')}", anchor='w', fill=self.text_color, font=("Helvetica", 11), tags=('queue_item', row_tag))

            btn_h = 28
            right = canvas_w - 20
            play_w = 44
            play_x2 = right
            play_x1 = play_x2 - play_w
            self.queue_display_canvas.create_rectangle(play_x1, y, play_x2, y+btn_h, fill=self.secondary_color, outline='', tags=('queue_item', f'play_{idx}'))
            self.queue_display_canvas.create_text((play_x1+play_x2)//2, y+btn_h//2, text='▶', fill='white', font=("Helvetica", 9), tags=('queue_item', f'play_{idx}_text'))
            right = play_x1 - 8
            rm_x2 = right
            rm_x1 = rm_x2 - 44
            self.queue_display_canvas.create_rectangle(rm_x1, y, rm_x2, y+btn_h, fill=self.secondary_color, outline='', tags=('queue_item', f'rm_{idx}'))
            self.queue_display_canvas.create_text((rm_x1+rm_x2)//2, y+btn_h//2, text='✖', fill='white', font=("Helvetica", 9), tags=('queue_item', f'rm_{idx}_text'))
            right = rm_x1 - 8
            add_x2 = right
            add_x1 = add_x2 - 44
            self.queue_display_canvas.create_rectangle(add_x1, y, add_x2, y+btn_h, fill=self.secondary_color, outline='', tags=('queue_item', f'addpl_{idx}'))
            self.queue_display_canvas.create_text((add_x1+add_x2)//2, y+btn_h//2, text='📀', fill='white', font=("Helvetica", 9), tags=('queue_item', f'addpl_{idx}_text'))
            right = add_x1 - 8
            if song.get('is_temporary', True) and song.get('filepath') and TEMP_DIR in song['filepath']:
                keep_x2 = right
                keep_x1 = keep_x2 - 64
                self.queue_display_canvas.create_rectangle(keep_x1, y, keep_x2, y+btn_h, fill=self.secondary_color, outline='', tags=('queue_item', f'keep_{idx}'))
                self.queue_display_canvas.create_text((keep_x1+keep_x2)//2, y+btn_h//2, text='⬇️ Keep', fill='white', font=("Helvetica", 9), tags=('queue_item', f'keep_{idx}_text'))
                right = keep_x1 - 8

            try:
                self.queue_display_canvas.tag_bind(f'play_{idx}', '<Button-1>', lambda e, i=idx: self._play_song_index(i))
                self.queue_display_canvas.tag_bind(f'play_{idx}_text', '<Button-1>', lambda e, i=idx: self._play_song_index(i))
                self.queue_display_canvas.tag_bind(f'rm_{idx}', '<Button-1>', lambda e, i=idx: self._remove_from_queue(i))
                self.queue_display_canvas.tag_bind(f'rm_{idx}_text', '<Button-1>', lambda e, i=idx: self._remove_from_queue(i))
                self.queue_display_canvas.tag_bind(f'addpl_{idx}', '<Button-1>', lambda e, s=song: self._add_song_to_playlist_dialog(s))
                self.queue_display_canvas.tag_bind(f'addpl_{idx}_text', '<Button-1>', lambda e, s=song: self._add_song_to_playlist_dialog(s))
                if song.get('is_temporary', True) and song.get('filepath') and TEMP_DIR in song['filepath']:
                    self.queue_display_canvas.tag_bind(f'keep_{idx}', '<Button-1>', lambda e, s=song: self._permanently_keep_song(s))
                    self.queue_display_canvas.tag_bind(f'keep_{idx}_text', '<Button-1>', lambda e, s=song: self._permanently_keep_song(s))
            except Exception:
                pass

            y += btn_h + 6

        try:
            self.queue_display_canvas.config(scrollregion=(0,0, canvas_w, y + 20))
        except Exception:
            pass

    def _remove_from_queue(self, idx):
        if 0 <= idx < len(self.queue):
            song = self.queue[idx]
            if idx == self.queue_index:
                self._stop_playback()
                try:
                    fp = song.get('filepath')
                    if fp and os.path.exists(fp) and TEMP_DIR in fp:
                        self._safe_delete(fp)
                except Exception:
                    pass
            else:
                if song.get('filepath') and os.path.exists(song['filepath']) and TEMP_DIR in song['filepath']:
                    try:
                        self._safe_delete(song['filepath'])
                    except Exception:
                        pass
            del self.queue[idx]
            if idx < self.queue_index:
                self.queue_index -= 1
            elif idx == self.queue_index:
                self.queue_index = -1
                if self.queue:
                    self._play_song_index(0 if not self.shuffle else random.randint(0, len(self.queue)-1))
            self._refresh_queue_display()
            self._update_now_playing_info()
            try:
                if song.get('filepath') and os.path.exists(song['filepath']) and TEMP_DIR in song['filepath']:
                    self._safe_delete(song['filepath'])
            except Exception:
                pass

    def _stop_playback(self):
        pygame.mixer.music.stop()
        self.is_playing = False
        self.play_pause_btn.config(text="▶")
        self.current_song_path = None
        self.current_duration = 0
        self.seek_bar.set(0)
        self.current_time_label.config(text="0:00")
        self.total_time_label.config(text="0:00")
        try:
            if hasattr(self, '_current_sound') and self._current_sound is not None:
                try:
                    self._current_sound.stop()
                except Exception:
                    pass
                self._current_sound = None
                gc.collect()
        except Exception:
            pass
        self._update_now_playing_info()

    def _clear_temp_dir(self):
        try:
            for fname in os.listdir(TEMP_DIR):
                fpath = os.path.join(TEMP_DIR, fname)
                if os.path.isfile(fpath):
                    try:
                        os.remove(fpath)
                    except Exception:
                        try:
                            self._safe_delete(fpath)
                        except Exception:
                            pass
        except Exception:
            pass

    def _safe_delete(self, path):
        if not path:
            return False
        p = os.path.abspath(path)

        def _force_release_audio():
            try:
                try:
                    pygame.mixer.music.stop()
                except Exception:
                    pass
                try:
                    pygame.mixer.stop()
                except Exception:
                    pass
                try:
                    if hasattr(pygame.mixer.music, 'unload'):
                        try:
                            pygame.mixer.music.unload()
                        except Exception:
                            pass
                except Exception:
                    pass
                try:
                    if getattr(self, '_current_sound', None) is not None:
                        try:
                            self._current_sound.stop()
                        except Exception:
                            pass
                        self._current_sound = None
                except Exception:
                    pass
                gc.collect()
                try:
                    pygame.mixer.quit()
                except Exception:
                    pass
            except Exception:
                pass

        _force_release_audio()
        delays = [0.12, 0.12, 0.25, 0.5, 1.0, 1.5]
        for attempt, delay in enumerate(delays, start=1):
            try:
                if os.path.exists(p):
                    os.remove(p)
                print(f"_safe_delete: deleted {p}")
                return True
            except Exception as e:
                print(f"_safe_delete: attempt {attempt} failed deleting {p}: {e}")
                time.sleep(delay)
                _force_release_audio()

        try:
            if sys.platform.startswith('win'):
                try:
                    MOVEFILE_DELAY_UNTIL_REBOOT = 0x4
                    res = ctypes.windll.kernel32.MoveFileExW(p, None, MOVEFILE_DELAY_UNTIL_REBOOT)
                    if res != 0:
                        print(f"_safe_delete: scheduled deletion on reboot for {p}")
                        return True
                except Exception as e:
                    print(f"_safe_delete: MoveFileExW failed: {e}")
            if not hasattr(self, '_deferred_deletes'):
                self._deferred_deletes = []
            if p not in self._deferred_deletes:
                self._deferred_deletes.append(p)
            print(f"_safe_delete: deferred deletion for {p}")
        except Exception:
            pass
        return False

    def _play_song_index(self, idx):
        if idx < 0 or idx >= len(self.queue):
            return
        prev_idx = self.queue_index
        if prev_idx != -1 and prev_idx != idx and 0 <= prev_idx < len(self.queue):
            prev_song = self.queue[prev_idx]
            try:
                pygame.mixer.music.stop()
            except Exception:
                pass
            try:
                if prev_song.get('filepath') and os.path.exists(prev_song['filepath']) and TEMP_DIR in prev_song['filepath']:
                    self._safe_delete(prev_song['filepath'])
            except Exception:
                pass
            if prev_song.get('is_temporary', True):
                del self.queue[prev_idx]
                if prev_idx < idx:
                    idx -= 1

        self.queue_index = idx
        if idx < 0 or idx >= len(self.queue):
            return
        song = self.queue[idx]
        file_path = song.get('filepath')
        if not file_path or not os.path.exists(file_path):
            self._download_and_play(song, idx)
        else:
            self._play_loaded_song(file_path)
        self._refresh_queue_display()
        self._update_now_playing_info()

    def _download_and_play(self, song, idx):
        status_label = tk.Label(self.main_scrollable, text=f"⬇️ Downloading: {song['title']}...",
                                fg=self.accent_color, bg="#121212")
        status_label.pack(pady=5)
        self.root.update()

        def download():
            try:
                installed = None
                if song.get('videoId'):
                    for pl in list_playlists():
                        for s in load_playlist(pl):
                            if s.get('videoId') == song.get('videoId') and s.get('filepath') and os.path.exists(s.get('filepath')):
                                installed = s.get('filepath')
                                break
                        if installed:
                            break
                if not installed:
                    artist = song.get('artist', song.get('artists', '')) or ''
                    safe_artist = "".join(c for c in artist if c.isalnum() or c in (' ', '-', '_')).rstrip()[:50]
                    safe_title = "".join(c for c in song.get('title', '') if c.isalnum() or c in (' ', '-', '_')).rstrip()[:50]
                    expected = os.path.join(INSTL_DIR, f"{safe_artist} - {safe_title}.mp3")
                    if os.path.exists(expected):
                        installed = expected

                if installed:
                    song['filepath'] = installed
                    self.root.after(0, lambda: self._play_loaded_song(installed))
                    self.root.after(0, status_label.destroy)
                    return

                target = TEMP_DIR if song.get('is_temporary', True) else INSTL_DIR
                try:
                    abs_path = download_song_to_folder(song['videoId'], song['title'], song.get('artist', song.get('artists','')) , target)
                    song['filepath'] = abs_path
                    self.root.after(0, lambda: self._play_loaded_song(abs_path))
                except Exception as e:
                    self.root.after(0, lambda: messagebox.showerror("Download Error", str(e)))
                finally:
                    self.root.after(0, status_label.destroy)
            except Exception as e:
                self.root.after(0, lambda: messagebox.showerror("Download Error", str(e)))
                self.root.after(0, status_label.destroy)

        threading.Thread(target=download, daemon=True).start()

    def _play_loaded_song(self, filepath):
        try:
            pygame.mixer.music.load(filepath)
            pygame.mixer.music.play()
            self.is_playing = True
            self.play_pause_btn.config(text="⏸")
            self.current_song_path = filepath
            try:
                sound = pygame.mixer.Sound(filepath)
                self._current_sound = sound
            except Exception:
                sound = None
                self._current_sound = None
            if sound is not None:
                self.current_duration = sound.get_length()
            else:
                self.current_duration = 0
            total_min = int(self.current_duration // 60)
            total_sec = int(self.current_duration % 60)
            self.total_time_label.config(text=f"{total_min}:{total_sec:02d}")
            if self.popout_window and self.popout_window.winfo_exists():
                self.popout_total.config(text=f"{total_min}:{total_sec:02d}")
            self._play_start_offset = 0.0
            self._play_start_time = time.monotonic()
            self._update_now_playing_info()
        except Exception as e:
            messagebox.showerror("Playback Error", f"Could not play: {e}")

    def _next_song(self):
        if not self.queue:
            return
        if self.queue_index >= 0:
            current = self.queue[self.queue_index]
            try:
                pygame.mixer.music.stop()
            except Exception:
                pass
            try:
                if current.get('filepath') and os.path.exists(current['filepath']) and TEMP_DIR in current['filepath']:
                    self._safe_delete(current['filepath'])
            except Exception:
                pass
            self.queue.pop(self.queue_index)
            if self.queue_index >= len(self.queue):
                self.queue_index = len(self.queue) - 1
        if not self.queue:
            self._stop_playback()
            self._refresh_queue_display()
            return
        if self.shuffle:
            new_idx = random.randint(0, len(self.queue)-1)
            self._play_song_index(new_idx)
        else:
            self._play_song_index(0)

    def _prev_song(self):
        if not self.queue:
            return
        if self.shuffle:
            new_idx = random.randint(0, len(self.queue)-1)
            self._play_song_index(new_idx)
            return

        if self.queue_index < 0:
            self._play_song_index(len(self.queue) - 1)
            return

        target = self.queue_index - 1
        if target < 0:
            target = len(self.queue) - 1
        self._play_song_index(target)

    def _get_audio_metadata_from_file(self, filepath):
        basename = os.path.basename(filepath)
        if " - " in basename:
            parts = basename[:-4].split(" - ", 1)
            artist, title = parts[0], parts[1]
        else:
            artist, title = "Unknown Artist", basename[:-4]
        return {
            'title': title,
            'artist': artist,
            'videoId': None,
            'filepath': filepath
        }

    def _toggle_play_pause(self):
        if self.is_playing:
            pygame.mixer.music.pause()
            self.is_playing = False
            self.play_pause_btn.config(text="▶")
            try:
                if self._play_start_time is not None:
                    elapsed = time.monotonic() - self._play_start_time
                    self._play_start_offset += elapsed
                    self._play_start_time = None
            except Exception:
                pass
        else:
            if self.current_song_path:
                pygame.mixer.music.unpause()
                self.is_playing = True
                self.play_pause_btn.config(text="⏸")
                try:
                    if self._play_start_time is None:
                        self._play_start_time = time.monotonic()
                except Exception:
                    pass
            elif self.queue:
                self._play_song_index(0)

    def _toggle_shuffle(self):
        self.shuffle = not self.shuffle
        try:
            self.shuffle_btn.config(bg=self.accent_color if self.shuffle else self.button_color)
        except Exception:
            pass

    def _set_volume(self, val):
        try:
            percent = int(float(val))
        except Exception:
            try:
                percent = int(self.volume_slider.get())
            except Exception:
                percent = 80
        vol = percent / 100.0
        try:
            pygame.mixer.music.set_volume(vol)
        except Exception:
            pass
        try:
            if hasattr(self, 'volume_pct_label'):
                self.volume_pct_label.config(text=f"{percent}%")
        except Exception:
            pass
        try:
            if hasattr(self, 'popout_volume_label') and self.popout_window and self.popout_window.winfo_exists():
                self.popout_volume_label.config(text=f"{percent}%")
        except Exception:
            pass
        if percent == 0:
            icon = "🔇"
        elif percent <= 33:
            icon = "🔈"
        elif percent <= 66:
            icon = "🔉"
        else:
            icon = "🔊"
        try:
            self.volume_icon_label.config(text=icon)
        except Exception:
            pass

    def _on_close(self):
        try:
            if hasattr(self, '_deferred_deletes') and self._deferred_deletes:
                for p in list(self._deferred_deletes):
                    try:
                        if os.path.exists(p):
                            os.remove(p)
                            self._deferred_deletes.remove(p)
                    except Exception:
                        pass
        except Exception:
            pass
        try:
            pygame.mixer.quit()
        except Exception:
            pass
        try:
            self.root.destroy()
        except Exception:
            pass

    def _update_now_playing_info(self):
        if self.queue_index >= 0 and self.queue_index < len(self.queue):
            song = self.queue[self.queue_index]
            text = f"Now playing: {song['title']} - {song['artist']}"
        else:
            text = "Not playing"
        self.song_info_label.config(text=text)

    def _update_ui_loop(self):
        if self.is_playing and not pygame.mixer.music.get_busy():
            try:
                if self.queue_index >= 0 and self.queue_index < len(self.queue):
                    cur = self.queue[self.queue_index]
                    fp = cur.get('filepath')
                    if fp and os.path.exists(fp) and TEMP_DIR in fp:
                        try:
                            pygame.mixer.music.stop()
                        except Exception:
                            pass
                        try:
                            self._safe_delete(fp)
                        except Exception:
                            pass
            except Exception:
                pass
            self.is_playing = False
            self.play_pause_btn.config(text="▶")
            self._next_song()
        self._update_seek_display()
        self.root.after(500, self._update_ui_loop)

    # ---------- Queue View ----------
    def _show_queue_view(self):
        self._clear_main_content()
        self.queue_frame = tk.Frame(self.main_canvas, bg=self.bg_color)
        self.queue_frame_win = self.main_canvas.create_window(0, 0, window=self.queue_frame, anchor='nw', width=self.main_canvas.winfo_width(), height=self.main_canvas.winfo_height())

        def _on_main_canvas_resize(event):
            self.main_canvas.coords(self.queue_frame_win, 0, 0)
            self.main_canvas.itemconfig(self.queue_frame_win, width=event.width, height=event.height)
        self.main_canvas.bind('<Configure>', _on_main_canvas_resize)

        # Create a canvas inside queue_frame for scrollable content
        self.queue_display_canvas = tk.Canvas(self.queue_frame, bg=self.bg_color, highlightthickness=0)
        self.queue_display_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.queue_scrollbar = ttk.Scrollbar(self.queue_frame, orient=tk.VERTICAL, command=self.queue_display_canvas.yview, style='Larpify.Vertical.TScrollbar')
        self.queue_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.queue_display_canvas.configure(yscrollcommand=self.queue_scrollbar.set)

        # Bind mousewheel for scrolling
        def _on_queue_mousewheel(event):
            self.queue_display_canvas.yview_scroll(int(-1*(event.delta/120)), "units")
        self.queue_display_canvas.bind("<Enter>", lambda e: self.queue_display_canvas.bind_all("<MouseWheel>", _on_queue_mousewheel))
        self.queue_display_canvas.bind("<Leave>", lambda e: self.queue_display_canvas.unbind_all("<MouseWheel>"))
        self.queue_display_canvas.bind('<Configure>', lambda e: self.queue_display_canvas.configure(scrollregion=self.queue_display_canvas.bbox("all")))

        self._set_active_menu('Queue')
        self._refresh_queue_display()

    # ---------- Playlists View ----------
    def _show_playlists_view(self):
        self._clear_main_content()
        action_frame = tk.Frame(self.main_canvas, bg=self.bg_color)
        action_win = self.main_canvas.create_window(20, 20, window=action_frame, anchor='nw', width=1140)
        self.RoundedButton(action_frame, text="New Playlist", command=self._create_playlist, width=140, height=36, radius=10, bg=self.button_color, fg="white").pack(side=tk.LEFT, padx=5)
        self.RoundedButton(action_frame, text="Import YouTube Playlist", command=self._import_youtube_playlist, width=220, height=36, radius=10, bg=self.button_color, fg="white").pack(side=tk.LEFT, padx=5)

        list_frame = tk.Frame(self.main_canvas, bg=self.bg_color)
        list_win = self.main_canvas.create_window(20, 72, window=list_frame, anchor='nw', width=1140, height=468)
        self.playlist_widgets = []
        for pl in list_playlists():
            lbl = tk.Label(list_frame, text=pl, fg=self.text_color, bg=self.bg_color, font=("Helvetica", 14), anchor='w', cursor='hand2')
            lbl.pack(fill=tk.X, pady=6)
            lbl.bind('<Button-1>', lambda e, name=pl: self._show_playlist_detail(name))
            lbl.bind('<Button-3>', lambda e, name=pl: self._show_playlist_context_menu_for_name(e, name))
            lbl.bind('<Enter>', lambda e: e.widget.config(fg=self.accent_color))
            lbl.bind('<Leave>', lambda e: e.widget.config(fg=self.text_color))
            self.playlist_widgets.append(lbl)
        self._set_active_menu('Playlists')

    def _show_playlist_detail(self, playlist_name):
        self._clear_main_content()
        action_frame = tk.Frame(self.main_canvas, bg=self._main_bg())
        self.main_canvas.create_window(20, 20, window=action_frame, anchor='nw')
        self.RoundedButton(action_frame, text="Load into Queue", command=lambda: self._load_playlist_into_queue(playlist_name), width=140, height=34, radius=10, bg=self.button_color, fg="white").pack(side=tk.LEFT, padx=6)
        self.RoundedButton(action_frame, text="Download All", command=lambda: self._download_playlist(playlist_name), width=140, height=34, radius=10, bg=self.button_color, fg="white").pack(side=tk.LEFT, padx=6)

        pl_container = tk.Frame(self.main_canvas, bg=self.bg_color)
        pl_container_win = self.main_canvas.create_window(20, 72, window=pl_container, anchor='nw', width=self.main_canvas.winfo_width()-40, height=self.main_canvas.winfo_height()-92)

        def _on_pl_canvas_resize(event):
            self.main_canvas.itemconfig(pl_container_win, width=event.width-40, height=event.height-92)
        self.main_canvas.bind('<Configure>', _on_pl_canvas_resize)

        pl_canvas = tk.Canvas(pl_container, bg=self._main_bg(), highlightthickness=0)
        pl_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self._bg_canvases.append(pl_canvas)
        pl_canvas.bind('<Configure>', lambda e: self._refresh_canvas_bg(pl_canvas))
        
        pl_scrollbar = ttk.Scrollbar(pl_container, orient=tk.VERTICAL, command=pl_canvas.yview, style='Larpify.Vertical.TScrollbar')
        pl_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        pl_canvas.configure(yscrollcommand=pl_scrollbar.set)

        list_frame = tk.Frame(pl_canvas, bg=self._main_bg())
        list_frame_win = pl_canvas.create_window(0, 0, window=list_frame, anchor='nw')

        def _on_list_frame_configure(e):
            pl_canvas.configure(scrollregion=pl_canvas.bbox("all"))
            pl_canvas.itemconfig(list_frame_win, width=pl_canvas.winfo_width())
        list_frame.bind('<Configure>', _on_list_frame_configure)

        def _on_pl_mousewheel(event):
            pl_canvas.yview_scroll(int(-1*(event.delta/120)), "units")
        pl_canvas.bind("<Enter>", lambda e: pl_canvas.bind_all("<MouseWheel>", _on_pl_mousewheel))
        pl_canvas.bind("<Leave>", lambda e: pl_canvas.unbind_all("<MouseWheel>"))

        songs = load_playlist(playlist_name)
        for idx, song in enumerate(songs):
            status = "✅" if os.path.exists(song.get('filepath', '')) else "⬇️"
            row = tk.Frame(list_frame, bg=self._main_bg(), pady=6)
            row.pack(fill=tk.X)
            lbl = tk.Label(row, text=f"{status} {song['title']} - {song['artist']}", fg=self.text_color, bg=self._main_bg(), font=("Helvetica", 13), anchor='w')
            lbl.pack(side=tk.LEFT, fill=tk.X, expand=True)
            self.RoundedButton(row, text="▶", command=lambda s=song: self._play_song_from_playlist(s), width=44, height=28, radius=8, bg=self.button_color, fg="white").pack(side=tk.RIGHT, padx=2)
            self.RoundedButton(row, text="✖", command=lambda i=idx: self._remove_song_from_playlist_and_refresh(playlist_name, i, row), width=44, height=28, radius=8, bg=self.button_color, fg="white").pack(side=tk.RIGHT, padx=2)
            if not os.path.exists(song.get('filepath', '')):
                self.RoundedButton(row, text="⬇️", command=lambda s=song: self._download_single_playlist_song(playlist_name, s, row), width=44, height=28, radius=8, bg=self.button_color, fg="white").pack(side=tk.RIGHT, padx=2)
        self._set_active_menu('Playlists')

    def _play_song_from_playlist(self, song):
        self.queue = [song.copy()]
        self.queue_index = -1
        self._stop_playback()
        self._refresh_queue_display()
        self._play_song_index(0)
        self._show_queue_view()

    def _remove_song_from_playlist_and_refresh(self, playlist_name, idx, parent_frame):
        remove_song_from_playlist(playlist_name, idx)
        self._show_playlist_detail(playlist_name)

    def _download_single_playlist_song(self, playlist_name, song, parent_frame):
        def download():
            try:
                abs_path = download_song_to_folder(song['videoId'], song['title'], song['artist'], INSTL_DIR)
                songs = load_playlist(playlist_name)
                for s in songs:
                    if s['videoId'] == song['videoId']:
                        s['filepath'] = abs_path
                        break
                save_playlist(playlist_name, songs)
                self.root.after(0, lambda: self._show_playlist_detail(playlist_name))
            except Exception as e:
                self.root.after(0, lambda: messagebox.showerror("Error", str(e)))
        threading.Thread(target=download, daemon=True).start()

    def _refresh_playlist_list(self):
        if hasattr(self, 'playlist_listbox') and getattr(self, 'playlist_listbox') is not None:
            try:
                self.playlist_listbox.delete(0, tk.END)
                for pl in list_playlists():
                    self.playlist_listbox.insert(tk.END, pl)
            except Exception:
                pass
        elif hasattr(self, 'playlist_widgets') and getattr(self, 'playlist_widgets') is not None:
            try:
                pls = list_playlists()
                for w in getattr(self, 'playlist_widgets', []):
                    try:
                        w.destroy()
                    except Exception:
                        pass
                self.playlist_widgets = []
                parent = None
                for pl in pls:
                    if parent is None:
                        parent = self.main_scrollable
                    lbl = tk.Label(self.main_scrollable, text=pl, fg=self.text_color, bg=self.bg_color, font=("Helvetica", 14), anchor='w', cursor='hand2')
                    lbl.pack(fill=tk.X, pady=6, padx=20)
                    lbl.bind('<Button-1>', lambda e, name=pl: self._show_playlist_detail(name))
                    lbl.bind('<Button-3>', lambda e, name=pl: self._show_playlist_context_menu_for_name(e, name))
                    lbl.bind('<Enter>', lambda e: e.widget.config(fg=self.accent_color))
                    lbl.bind('<Leave>', lambda e: e.widget.config(fg=self.text_color))
                    self.playlist_widgets.append(lbl)
            except Exception:
                pass

    def _create_playlist(self):
        name = simpledialog.askstring("New Playlist", "Enter playlist name:")
        if not name:
            return
        if name in list_playlists():
            messagebox.showerror("Error", "Playlist already exists.")
            return
        save_playlist(name, [])
        self._refresh_playlist_list()

    def _show_playlist_context_menu(self, event):
        if not hasattr(self, 'playlist_listbox') or getattr(self, 'playlist_listbox') is None:
            return
        idx = self.playlist_listbox.nearest(event.y)
        if idx < 0:
            return
        name = self.playlist_listbox.get(idx)
        try:
            menu = tk.Toplevel(self.root)
            menu.overrideredirect(True)
            menu.config(bg=self.bg_color)
            menu.geometry(f"+{event.x_root}+{event.y_root}")
            frame = tk.Frame(menu, bg="#111111", bd=0)
            frame.pack()
            self.RoundedButton(frame, text="Load into Queue", command=lambda: (self._load_playlist_into_queue(name), menu.destroy()), width=180, height=34, radius=10, bg=self.button_color, fg="white").pack(fill=tk.X, padx=8, pady=4)
            self.RoundedButton(frame, text="Download All", command=lambda: (self._download_playlist(name), menu.destroy()), width=180, height=34, radius=10, bg=self.button_color, fg="white").pack(fill=tk.X, padx=8, pady=4)
            self.RoundedButton(frame, text="Rename", command=lambda: (self._rename_playlist(name), menu.destroy()), width=180, height=34, radius=10, bg=self.button_color, fg="white").pack(fill=tk.X, padx=8, pady=4)
            self.RoundedButton(frame, text="Delete", command=lambda: (self._delete_playlist(name), menu.destroy()), width=180, height=34, radius=10, bg="#b91c1c", fg="white").pack(fill=tk.X, padx=8, pady=4)
            menu.focus_force()
            menu.bind('<FocusOut>', lambda e: menu.destroy())
        except Exception:
            try:
                menu = tk.Menu(self.root, tearoff=0)
                menu.add_command(label="Load into Queue", command=lambda: self._load_playlist_into_queue(name))
                menu.add_command(label="Download All", command=lambda: self._download_playlist(name))
                menu.add_command(label="Rename", command=lambda: self._rename_playlist(name))
                menu.add_command(label="Delete", command=lambda: self._delete_playlist(name))
                menu.post(event.x_root, event.y_root)
            except Exception:
                pass

    def _show_playlist_context_menu_for_name(self, event, name):
        try:
            menu = tk.Toplevel(self.root)
            menu.overrideredirect(True)
            menu.config(bg=self.bg_color)
            menu.geometry(f"+{event.x_root}+{event.y_root}")
            frame = tk.Frame(menu, bg="#111111", bd=0)
            frame.pack()
            self.RoundedButton(frame, text="Load into Queue", command=lambda: (self._load_playlist_into_queue(name), menu.destroy()), width=180, height=34, radius=10, bg=self.button_color, fg="white").pack(fill=tk.X, padx=8, pady=4)
            self.RoundedButton(frame, text="Download All", command=lambda: (self._download_playlist(name), menu.destroy()), width=180, height=34, radius=10, bg=self.button_color, fg="white").pack(fill=tk.X, padx=8, pady=4)
            self.RoundedButton(frame, text="Rename", command=lambda: (self._rename_playlist(name), menu.destroy()), width=180, height=34, radius=10, bg=self.button_color, fg="white").pack(fill=tk.X, padx=8, pady=4)
            self.RoundedButton(frame, text="Delete", command=lambda: (self._delete_playlist(name), menu.destroy()), width=180, height=34, radius=10, bg="#b91c1c", fg="white").pack(fill=tk.X, padx=8, pady=4)
            menu.focus_force()
            menu.bind('<FocusOut>', lambda e: menu.destroy())
        except Exception:
            try:
                menu = tk.Menu(self.root, tearoff=0)
                menu.add_command(label="Load into Queue", command=lambda: self._load_playlist_into_queue(name))
                menu.add_command(label="Download All", command=lambda: self._download_playlist(name))
                menu.add_command(label="Rename", command=lambda: self._rename_playlist(name))
                menu.add_command(label="Delete", command=lambda: self._delete_playlist(name))
                menu.post(event.x_root, event.y_root)
            except Exception:
                pass

    def _download_playlist(self, name):
        threading.Thread(target=lambda: download_playlist_songs(name), daemon=True).start()
        messagebox.showinfo("Download", f"Downloading playlist '{name}' in background.")

    def _load_playlist_into_queue(self, name):
        songs = load_playlist(name)
        if not songs:
            messagebox.showinfo("Empty", f"Playlist '{name}' has no songs.")
            return
        if self.queue and not messagebox.askyesno("Clear Queue", "Replace current queue?"):
            for s in songs:
                s_copy = s.copy()
                s_copy['is_temporary'] = False
                self.queue.append(s_copy)
        else:
            self.queue = [s.copy() for s in songs]
            for s in self.queue:
                s['is_temporary'] = False
            self.queue_index = -1
            self._stop_playback()
        self._refresh_queue_display()
        if self.queue:
            self._play_song_index(0)
        self._show_queue_view()

    def _load_selected_playlist_into_queue(self, event):
        if not hasattr(self, 'playlist_listbox') or getattr(self, 'playlist_listbox') is None:
            return
        sel = self.playlist_listbox.curselection()
        if not sel:
            return
        name = self.playlist_listbox.get(sel[0])
        self._load_playlist_into_queue(name)

    def _rename_playlist(self, old_name):
        new_name = simpledialog.askstring("Rename Playlist", "New name:", initialvalue=old_name)
        if not new_name or new_name == old_name:
            return
        rename_playlist(old_name, new_name)
        self._refresh_playlist_list()

    def _delete_playlist(self, name):
        if messagebox.askyesno("Delete", f"Delete playlist '{name}'?"):
            delete_playlist(name)
            self._refresh_playlist_list()

    def _import_youtube_playlist(self):
        url = simpledialog.askstring("Import YouTube Playlist", "Enter YouTube playlist URL:")
        if not url:
            return
        name = simpledialog.askstring("Playlist Name", "Name for the new playlist:", initialvalue="Imported Playlist")
        if not name:
            return
        if name in list_playlists():
            if not messagebox.askyesno("Overwrite", f"Playlist '{name}' already exists. Overwrite?"):
                return
            delete_playlist(name)
        try:
            ydl_opts = {'quiet': True, 'no_warnings': True, 'extract_flat': True}
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                entries = info.get('entries', [])
                songs = []
                for e in entries:
                    songs.append({
                        'title': e.get('title'),
                        'artist': e.get('uploader') or 'Unknown Artist',
                        'videoId': e.get('id'),
                        'filepath': ""
                    })
                save_playlist(name, songs)
                self._refresh_playlist_list()
                messagebox.showinfo("Success", f"Imported {len(songs)} songs into playlist '{name}'.\nUse 'Download All' to download them.")
        except Exception as e:
            messagebox.showerror("Error", str(e))

    # ---------- Library View ----------
    def _show_library_view(self):
        self._clear_main_content()
        lib_frame = tk.Frame(self.main_canvas, bg=self._main_bg())
        self.lib_frame_win = self.main_canvas.create_window(0, 0, window=lib_frame, anchor='nw')

        for child in lib_frame.winfo_children():
            child.destroy()

        all_songs = []
        for pl in list_playlists():
            for song in load_playlist(pl):
                song_copy = song.copy()
                song_copy['playlist'] = pl
                song_copy['is_temporary'] = False
                all_songs.append(song_copy)
        
        # Add songs from INSTL_DIR (local files)
        existing_filepaths = {s['filepath'] for s in all_songs if s.get('filepath')}
        for filename in os.listdir(INSTL_DIR):
            if filename.endswith('.mp3'):
                filepath = os.path.join(INSTL_DIR, filename)
                if filepath not in existing_filepaths:
                    metadata = self._get_audio_metadata_from_file(filepath)
                    if metadata:
                        metadata['playlist'] = "Local Files" # Indicate it's a local file not from a specific playlist
                        metadata['is_temporary'] = False
                        all_songs.append(metadata)
                        existing_filepaths.add(filepath) # Add to set to avoid re-adding if another playlist points to it

        # Sort songs for consistent display
        all_songs.sort(key=lambda x: (x.get('artist', '').lower(), x.get('title', '').lower()))

        if not all_songs:
            tk.Label(lib_frame, text="No songs in library. Add songs to playlists or download them first.", fg=self.text_color, bg=self._main_bg(), font=("Helvetica", 12)).pack(pady=20)
        else:
            for song in all_songs:
                row = tk.Frame(lib_frame, bg=self._main_bg(), pady=6)
                row.pack(fill=tk.X)
                status = "✅" if os.path.exists(song.get('filepath', '')) else "⬇️"
                lbl_text = f"{status} {song['title']} - {song['artist']}"
                if song.get('playlist') and song['playlist'] != "Local Files":
                    lbl_text += f"  [Playlist: {song['playlist']}]"
                else:
                    lbl_text += "  [Local File]" # Indicate it's a local file
                # Create action buttons (fixed pixel widths provided to RoundedButton)
                save_btn_w = 100
                queue_btn_w = 110
                # Pack buttons first on the right
                self.RoundedButton(row, text="➕ Queue", command=lambda s=song: self._add_song_to_queue_from_library(s), width=queue_btn_w, height=32, radius=8, bg=self.button_color, fg="white").pack(side=tk.RIGHT, padx=(5, 10))
                self.RoundedButton(row, text="📀 Save", command=lambda s=song: self._add_song_to_playlist_dialog(s), width=save_btn_w, height=32, radius=8, bg=self.accent_color, fg="white").pack(side=tk.RIGHT, padx=(5, 40))

                # Now create label and truncate its text once to fit before the buttons
                lbl = tk.Label(row, text=lbl_text, fg=self.text_color, bg=self._main_bg(), font=("Helvetica", 13), anchor='w')
                # Estimate available pixel width: use canvas width (fallback 600) minus button widths and margins
                try:
                    canvas_w = self.main_canvas.winfo_width() or 600
                except Exception:
                    canvas_w = 600
                other_w = save_btn_w + queue_btn_w + 40 + 12  # buttons + padx + label left padding
                max_label_px = max(40, canvas_w - other_w)
                try:
                    f = tkfont.Font(font=lbl['font'])
                    full = lbl_text
                    if f.measure(full) > max_label_px:
                        lo, hi = 0, len(full)
                        while lo < hi:
                            mid = (lo + hi) // 2
                            trial = full[:mid] + '…'
                            if f.measure(trial) <= max_label_px:
                                lo = mid + 1
                            else:
                                hi = mid
                        chars = max(0, lo - 1)
                        display = (full[:chars] + '…') if chars > 0 else '…'
                    else:
                        display = full
                except Exception:
                    display = lbl_text
                lbl.config(text=display)
                lbl.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(12,5))

        lib_frame.update_idletasks()
        self.main_canvas.itemconfig(self.lib_frame_win, width=self.main_canvas.winfo_width())
        self.main_canvas.config(scrollregion=self.main_canvas.bbox("all"))
        self._set_active_menu('Library')

    def _add_song_to_queue_from_library(self, song):
        if not os.path.exists(song.get('filepath', '')):
            if not song.get('videoId'):
                messagebox.showerror("Error", "Song file missing and no Video ID available for download.")
                return
            try:
                abs_path = download_song_to_folder(song['videoId'], song['title'], song['artist'], INSTL_DIR)
                song['filepath'] = abs_path
                pl = song['playlist']
                songs = load_playlist(pl)
                for s in songs:
                    if s['videoId'] == song['videoId']:
                        s['filepath'] = abs_path
                        save_playlist(pl, songs)
                        break
            except Exception as e:
                messagebox.showerror("Error", f"Cannot download: {e}")
                return
        self._add_to_queue(song, is_temporary=False)

    # ---------- Search View (centered, placeholder text) ----------
    def _show_search_view(self):
        self._clear_main_content()
        self.current_search_query = ""
        self.all_results = []
        self.displayed_count = 0

        # Create a container frame to center the search bar and button
        search_container = tk.Frame(self.main_canvas, bg=self._main_bg())
        search_container_win = self.main_canvas.create_window(0, 20, window=search_container, anchor='nw')
        # Center the frame inside the canvas
        self.main_canvas.bind('<Configure>', lambda e: self._center_search_frame(search_container, search_container_win))
        # Also keep the search-placeholder text centered when the canvas resizes
        try:
            self.main_canvas.bind('<Configure>', lambda e: self._center_search_placeholder(), add='+')
        except Exception:
            pass

        # Search button on the left
        self.search_btn = self.RoundedButton(search_container, text="Search", command=self._perform_search, width=100, height=36, radius=10, bg=self.button_color, fg="white")
        self.search_btn.pack(side=tk.LEFT, padx=(0, 10))

        # Search entry with placeholder text
        self.search_entry = tk.Entry(search_container, bg=self.tertiary_color, fg=self.text_color, insertbackground=self.text_color,
                                     font=("Helvetica", 14), relief=tk.FLAT, width=50)
        self.search_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.search_placeholder = "Search for songs..."
        self.search_entry.insert(0, self.search_placeholder)
        self.search_entry.config(fg=self._lighter_color(self.text_color, 0.6))
        self.search_entry.bind("<FocusIn>", self._on_search_focus_in)
        self.search_entry.bind("<FocusOut>", self._on_search_focus_out)
        self.search_entry.bind("<Return>", lambda e: self._perform_search())

        # Store placeholder state
        self.search_placeholder_active = True

        self.results_start_y = 80  # Move results down a bit
        self._update_search_results_placeholder()

        self._set_active_menu('Search')

    def _center_search_frame(self, frame, win_id):
        try:
            w = self.main_canvas.winfo_width()
            frame.update_idletasks()
            fw = frame.winfo_reqwidth()
            x = (w - fw) // 2
            self.main_canvas.coords(win_id, x, 20)
        except:
            pass

    def _center_search_placeholder(self, event=None):
        try:
            # Move any placeholder text with tag 'search_placeholder' to canvas center
            ids = self.main_canvas.find_withtag('search_placeholder')
            if not ids:
                return
            x = max(0, self.main_canvas.winfo_width()//2)
            for item in ids:
                try:
                    coords = self.main_canvas.coords(item)
                    y = coords[1] if coords and len(coords) > 1 else (self.results_start_y + 40)
                    self.main_canvas.coords(item, x, y)
                except Exception:
                    try:
                        self.main_canvas.coords(item, x, self.results_start_y + 40)
                    except Exception:
                        pass
        except Exception:
            pass

    def _on_search_focus_in(self, event):
        if self.search_placeholder_active:
            self.search_entry.delete(0, tk.END)
            self.search_entry.config(fg=self.text_color)
            self.search_placeholder_active = False

    def _on_search_focus_out(self, event):
        if not self.search_entry.get().strip():
            self.search_entry.insert(0, self.search_placeholder)
            self.search_entry.config(fg=self._lighter_color(self.text_color, 0.6))
            self.search_placeholder_active = True

    def _update_search_results_placeholder(self, new_results=None):
        if new_results is not None:
            self.all_results = new_results
            self.displayed_count = 0

        try:
            self.main_canvas.delete('search_item')
        except Exception:
            pass

        if not self.all_results:
            if self.current_search_query == "" and (not hasattr(self, 'search_placeholder_active') or self.search_placeholder_active):
                self.main_canvas.create_text(self.main_canvas.winfo_width()//2, self.results_start_y + 40,
                                             text="Enter a song name in the search bar above",
                                             fill=self.text_color, font=("Helvetica", 12), tags=('search_item','search_placeholder'))
                try:
                    self._center_search_placeholder()
                except Exception:
                    pass
            elif self.current_search_query != "":
                self.main_canvas.create_text(self.main_canvas.winfo_width()//2, self.results_start_y + 40,
                                             text="No results found. Try a different search term.",
                                             fill=self.text_color, font=("Helvetica", 12), tags=('search_item','search_placeholder'))
                try:
                    self._center_search_placeholder()
                except Exception:
                    pass
            if hasattr(self, 'more_btn_win'):
                try:
                    self.main_canvas.itemconfig(self.more_btn_win, state='hidden')
                except Exception:
                    pass
            return

        canvas_w = max(800, self.main_canvas.winfo_width())
        item_h = 68
        x_title = 70
        right_margin = 20
        save_w = 120
        queue_w = 100
        y = self.results_start_y + 6

        end = min(self.displayed_count + self.step, len(self.all_results))
        for idx in range(self.displayed_count, end):
            song = self.all_results[idx]
            tag_base = f'search_item_{idx}'
            self.main_canvas.create_text(30, y + item_h//2, text=f"{idx+1:2d}.", anchor='w', fill=self.text_color, font=("Helvetica", 11), tags=('search_item', tag_base))
            self.main_canvas.create_text(x_title, y + 8, text=song.get('title',''), anchor='nw', fill=self.text_color, font=("Helvetica", 13, 'bold'), tags=('search_item', tag_base))
            self.main_canvas.create_text(x_title, y + 36, text=song.get('artists',''), anchor='nw', fill=self._lighter_color(self.text_color, 0.8), font=("Helvetica", 10), tags=('search_item', tag_base))

            save_x2 = canvas_w - right_margin
            save_x1 = save_x2 - save_w
            queue_x2 = save_x1 - 8
            queue_x1 = queue_x2 - queue_w

            self.main_canvas.create_rectangle(save_x1, y+8, save_x2, y+item_h-8, fill=self.accent_color, outline='', tags=('search_item', f'save_{idx}'))
            self.main_canvas.create_text((save_x1+save_x2)//2, y+item_h//2, text='📀 Save', fill='white', font=("Helvetica", 9), tags=('search_item', f'save_{idx}_text'))

            self.main_canvas.create_rectangle(queue_x1, y+8, queue_x2, y+item_h-8, fill=self.secondary_color, outline='', tags=('search_item', f'queue_{idx}'))
            self.main_canvas.create_text((queue_x1+queue_x2)//2, y+item_h//2, text='➕ Queue', fill='white', font=("Helvetica", 9), tags=('search_item', f'queue_{idx}_text'))

            try:
                self.main_canvas.tag_bind(f'save_{idx}', '<Button-1>', lambda e, s=song: self._add_song_to_playlist_dialog(s))
                self.main_canvas.tag_bind(f'save_{idx}_text', '<Button-1>', lambda e, s=song: self._add_song_to_playlist_dialog(s))
                self.main_canvas.tag_bind(f'queue_{idx}', '<Button-1>', lambda e, s=song: self._add_temporary_to_queue(s))
                self.main_canvas.tag_bind(f'queue_{idx}_text', '<Button-1>', lambda e, s=song: self._add_temporary_to_queue(s))
                self.main_canvas.tag_bind(tag_base, '<Double-Button-1>', lambda e, s=song: self._add_temporary_to_queue(s))
            except Exception:
                pass

            y += item_h + 6

        self.displayed_count = end
        # Create the "Load more" button if not exists
        if not hasattr(self, 'more_btn'):
            self.more_btn = self.RoundedButton(self.main_canvas, text="Load more", command=self._load_more, width=120, height=34, radius=10, bg=self.button_color, fg="white")
            self.more_btn_win = self.main_canvas.create_window(0, 0, window=self.more_btn, anchor='nw')

        try:
            self.main_canvas.coords(self.more_btn_win, max(540, canvas_w//2-60), y + 8)
        except Exception:
            pass

        if self.displayed_count < len(self.all_results):
            self.main_canvas.itemconfig(self.more_btn_win, state='normal')
        else:
            self.main_canvas.itemconfig(self.more_btn_win, state='hidden')

        # Update scrollregion AFTER placing all elements including button
        self.main_canvas.update_idletasks()
        self.main_canvas.config(scrollregion=self.main_canvas.bbox("all"))

    def _add_temporary_to_queue(self, song_dict):
        song = {
            'title': song_dict['title'],
            'artist': song_dict['artists'],
            'videoId': song_dict['videoId'],
            'filepath': "",
            'is_temporary': True
        }
        self._add_to_queue(song)

    def _add_song_to_playlist_dialog(self, song_dict):
        self._close_current_overlay()
        try:
            self.root.update_idletasks()
            ow = 360
            oh = 420
            start_x = self.root.winfo_width() + 20
            top_y = 80
            overlay = tk.Canvas(self.root, bg=self.bg_color, highlightthickness=0)
            overlay.place(x=start_x, y=top_y, width=ow, height=oh)
            self._draw_rounded_rect(overlay, 0, 0, ow, oh, r=12, fill=self.bg_color, outline=self.secondary_color, shadow=True)
            content = tk.Frame(overlay, bg=self.bg_color)
            overlay.create_window(10, 10, anchor='nw', window=content, width=ow-20, height=oh-20)

            tk.Label(content, text="Save to Playlist", fg=self.text_color, bg=self.bg_color, font=("Helvetica", 11, "bold")).pack(pady=(6,6))
            listbox = tk.Listbox(content, bg=self.bg_color, fg=self.text_color, height=6)
            listbox.pack(fill=tk.X, padx=8, pady=(2,4))
            for pl in list_playlists():
                listbox.insert(tk.END, pl)

            entry_frame = tk.Frame(content, bg=self.bg_color)
            entry_frame.pack(fill=tk.X, padx=8, pady=4)
            new_name_var = tk.StringVar()
            tk.Entry(entry_frame, textvariable=new_name_var, bg="#1b1b1b", fg=self.text_color).pack(side=tk.LEFT, fill=tk.X, expand=True)
            def _create_new():
                name = new_name_var.get().strip()
                if not name:
                    return
                if name in list_playlists():
                    messagebox.showerror("Error", "Playlist already exists.")
                    return
                save_playlist(name, [])
                listbox.insert(tk.END, name)
                new_name_var.set("")
            self.RoundedButton(entry_frame, text="Create", command=_create_new, width=96, height=34, radius=8, bg=self.button_color, fg="white", font=("Helvetica", 9)).pack(side=tk.LEFT, padx=6)

            add_to_queue_var = tk.IntVar(value=0)
            tk.Checkbutton(content, text="Add to Queue after adding", variable=add_to_queue_var, bg=self.bg_color, fg=self.text_color, selectcolor=self.bg_color).pack(anchor='w', padx=8, pady=4)

            def _add_selected():
                sel = listbox.curselection()
                if not sel:
                    return
                pl_name = listbox.get(sel[0])
                title = song_dict.get('title', '')
                artist = song_dict.get('artist', song_dict.get('artists', ''))
                vid = song_dict.get('videoId', '')
                fp = song_dict.get('filepath', '')
                if fp and os.path.exists(fp) and TEMP_DIR in fp:
                    try:
                        new_path = os.path.join(INSTL_DIR, os.path.basename(fp))
                        shutil.move(fp, new_path)
                        fp = new_path
                        if 'is_temporary' in song_dict:
                            song_dict['filepath'] = new_path
                            song_dict['is_temporary'] = False
                    except Exception:
                        pass

                song_to_save = {'title': title, 'artist': artist, 'videoId': vid, 'filepath': fp}
                ok = add_song_to_playlist(pl_name, song_to_save)
                if ok:
                    messagebox.showinfo("Added", f"Added '{title}' to playlist '{pl_name}'")
                else:
                    messagebox.showinfo("Skipped", f"Song already in playlist '{pl_name}' or could not be added.")
                self._refresh_playlist_list()
                if add_to_queue_var.get():
                    self._add_temporary_to_queue(song_dict)
                self._hide_overlay(overlay)

            btn_frame = tk.Frame(content, bg=self.bg_color)
            btn_frame.pack(fill=tk.X, pady=6)
            self.RoundedButton(btn_frame, text="Add", command=_add_selected, width=96, height=34, radius=8, bg=self.button_color, fg="white").pack(side=tk.RIGHT, padx=8)
            self.RoundedButton(btn_frame, text="Close", command=lambda: self._hide_overlay(overlay), width=96, height=34, radius=8, bg=self.button_color, fg="white").pack(side=tk.RIGHT, padx=6)

            target_x = max(20, self.root.winfo_width() - ow - 20)
            self._slide_widget(overlay, start_x, target_x)
            self._playlist_overlay = overlay
            self._current_overlay = overlay
        except Exception as e:
            print(f"Playlist overlay error: {e}")

    def _perform_search(self):
        if self.search_placeholder_active:
            return
        query = self.search_entry.get().strip()
        if not query:
            self._update_search_results_placeholder([])
            return

        self.current_search_query = query
        try:
            self.main_canvas.delete('search_item')
        except Exception:
            pass
        self.main_canvas.create_text(self.main_canvas.winfo_width()//2, self.results_start_y + 40,
                                     text="🔍 Searching...", fill=self.accent_color, font=("Helvetica", 12), tags=('search_item',))
        self.root.update()

        def search_thread():
            try:
                ydl_opts = {
                    'quiet': True,
                    'no_warnings': True,
                    'extract_flat': True,
                }
                search_query = f"ytsearch50:{query}"
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(search_query, download=False)
                    entries = info.get('entries', [])
                    results = []
                    for entry in entries:
                        duration_raw = entry.get('duration')
                        if duration_raw is not None:
                            try:
                                duration_sec = int(float(duration_raw))
                                minutes = duration_sec // 60
                                seconds = duration_sec % 60
                                duration_str = f"{minutes}:{seconds:02d}"
                            except:
                                duration_str = ""
                        else:
                            duration_str = ""
                        artist = entry.get('uploader') or entry.get('channel') or "Unknown Artist"
                        results.append({
                            'videoId': entry.get('id'),
                            'title': entry.get('title'),
                            'duration': duration_str,
                            'artists': artist
                        })
                    self.root.after(0, lambda: self._update_search_results_placeholder(results))
            except Exception as e:
                print(f"Search error: {e}")
                self.root.after(0, lambda: self._update_search_results_placeholder([]))

        threading.Thread(target=search_thread, daemon=True).start()

    def _load_more(self):
        self._update_search_results_placeholder()

    def _clear_main_content(self):
        for item in self.main_canvas.find_all():
            try:
                self.main_canvas.delete(item)
            except Exception:
                pass

if __name__ == "__main__":
    root = tk.Tk()
    app = LarpifyGUI(root)
    root.mainloop()