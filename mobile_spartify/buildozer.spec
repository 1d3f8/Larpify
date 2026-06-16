[app]
# (str) Title of your application
title = Spartify Mobile

# (str) Package name
package.name = spartify_mobile

# (str) Package domain (needed for android/ios packaging)
package.domain = org.example

# (str) Source code where the main.py lives
source.dir = .
source.include_exts = py,png,jpg,kv,atlas

# (list) Application requirements
requirements = python3,kivy==2.1.0,kivymd,yt-dlp

# (str) Icon of the application
icon.filename = %(source.dir)s/icon.png

# (str) Supported orientation (one of landscape, portrait or all)
orientation = portrait

# (bool) Indicate if the application should be fullscreen or not
fullscreen = 0

# (int) Android API to use
android.api = 33

# (int) Minimum Android API your APK will support
android.minapi = 21

# (str) Android NDK version to use
#android.ndk = 23b

# (str) Android entry point, defaults to org.kivy.android.PythonActivity
#android.entrypoint = org.kivy.android.PythonActivity

# (list) Permissions
android.permissions = INTERNET, WRITE_EXTERNAL_STORAGE, READ_EXTERNAL_STORAGE, WAKE_LOCK, FOREGROUND_SERVICE

# (str) Application versioning
version = 0.1

# (int) Target SDK
android.target = 33

# (bool) If you want to use AndroidX
android.use_androidx = True

# (str) Presplash image
#presplash.filename = %(source.dir)s/presplash.png
