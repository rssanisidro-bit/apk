[app]
title = FileLink
package.name = filefasttransfer
package.domain = org.tju.challenge
source.dir = .
source.include_exts = py,png,jpg,kv,atlas,md,txt
source.exclude_dirs = __pycache__,.buildozer,bin
version = 1.0
requirements = python3,kivy
orientation = portrait
fullscreen = 0

# Android needs network permission for socket communication.
android.permissions = INTERNET,ACCESS_NETWORK_STATE,ACCESS_WIFI_STATE,READ_EXTERNAL_STORAGE,WRITE_EXTERNAL_STORAGE,READ_MEDIA_IMAGES,READ_MEDIA_VIDEO,READ_MEDIA_AUDIO,MANAGE_EXTERNAL_STORAGE
android.api = 35
android.minapi = 23
android.archs = arm64-v8a, armeabi-v7a
android.accept_sdk_license = True

[buildozer]
log_level = 2
warn_on_root = 1
