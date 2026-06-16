Spartify Mobile (all-in-one) — Kivy + Buildozer

This folder contains a Kivy-based mobile app scaffold that bundles Python code and can be built to an APK using Buildozer / python-for-android.

Notes:
- This is an initial scaffold. The app uses `yt-dlp` to download audio and will call the `yt-dlp` binary at runtime.
- Building an APK requires a Linux environment (WSL2 on Windows or CI) and Buildozer.

Local build (WSL2 / Ubuntu recommended):

1. Install system deps (Ubuntu):

```bash
sudo apt update && sudo apt install -y python3-pip build-essential git openjdk-11-jdk zlib1g-dev libncurses5 libffi-dev libssl-dev libsqlite3-dev
```

2. Install Buildozer & Cython:

```bash
python3 -m pip install --upgrade pip
python3 -m pip install cython buildozer
```

3. From this folder run:

```bash
buildozer android debug
```

This will produce an unsigned debug APK in `bin/`.

CI: A GitHub Actions workflow is included in the repo root that can run Buildozer on `ubuntu-latest` and produce APK artifacts.

Caveats:
- The APK will be large due to bundling Python runtime and media tools.
- You must test downloads and playback on a device; some native binaries (ffmpeg) may need to be added manually.

