"""PyInstaller hook для MediaPipe Tasks."""

from PyInstaller.utils.hooks import collect_all, collect_submodules

datas, binaries, hiddenimports = collect_all("mediapipe")
hiddenimports += collect_submodules("mediapipe.tasks")
