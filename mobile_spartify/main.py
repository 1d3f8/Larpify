from kivy.lang import Builder
from kivymd.app import MDApp
from kivymd.uix.list import OneLineListItem
from kivy.uix.scrollview import ScrollView
from kivy.clock import mainthread
import threading, subprocess, os

KV = '''
Screen:
    MDBoxLayout:
        orientation: 'vertical'
        MDToolbar:
            title: 'Spartify Mobile (Preview)'
            elevation: 10
        ScrollView:
            MDList:
                id: song_list
        MDBottomAppBar:
            MDToolbar:
                icon: 'play'
                type: 'bottom'
'''

class SpartifyApp(MDApp):
    def build(self):
        self.theme_cls.primary_palette = "Blue"
        return Builder.load_string(KV)

    def on_start(self):
        self.populate_list()

    def populate_list(self):
        songs = [
            {'title':'Sample Song 1','url':'https://www.youtube.com/watch?v=dQw4w9WgXcQ'},
            {'title':'Sample Song 2','url':'https://www.youtube.com/watch?v=3JZ_D3ELwOQ'},
        ]
        list_view = self.root.ids.song_list
        for s in songs:
            item = OneLineListItem(text=s['title'], on_release=lambda x, s=s: self.show_action(s))
            list_view.add_widget(item)

    def show_action(self, song):
        from kivymd.uix.dialog import MDDialog
        from kivymd.uix.boxlayout import MDBoxLayout
        content = MDBoxLayout(orientation='vertical', spacing=10, padding=10)
        dialog = MDDialog(title=song['title'], type='custom', content_cls=content, size_hint=(0.9, None))
        from kivymd.uix.button import MDFlatButton
        dialog.add_action_button('Download', lambda *a: (dialog.dismiss(), self.download_song(song['url'])))
        dialog.add_action_button('Close', lambda *a: dialog.dismiss())
        dialog.open()

    def download_song(self, url):
        threading.Thread(target=self._download_thread, args=(url,), daemon=True).start()

    def _download_thread(self, url):
        outdir = os.path.join(self.user_data_dir, 'downloads')
        os.makedirs(outdir, exist_ok=True)
        cmd = ['yt-dlp','-f','bestaudio','-o', os.path.join(outdir, '%(title)s.%(ext)s'), url]
        try:
            subprocess.run(cmd, check=True)
            self._show_message('Download complete')
        except Exception as e:
            self._show_message(f'Error: {e}')

    @mainthread
    def _show_message(self, text):
        from kivymd.uix.snackbar import Snackbar
        Snackbar(text=text).open()

if __name__ == '__main__':
    SpartifyApp().run()
