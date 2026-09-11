[app]
title = Minimal Snore Recorder
package.name = snorerecorder
package.domain = org.minimal
source.dir = .
source.include_exts = py,png,jpg,kv,atlas
version = 1.0

# Requirements: Kivy and PyJnius for Android API access
requirements = python3,kivy,android,pyjnius

# Android Specific Configuration
android.permissions = RECORD_AUDIO, WRITE_EXTERNAL_STORAGE, READ_EXTERNAL_STORAGE, WAKE_LOCK, FOREGROUND_SERVICE, FOREGROUND_SERVICE_MICROPHONE
android.api = 33
android.minapi = 24
android.archs = arm64-v8a, armeabi-v7a

# Keep the app running when screen is off (WakeLock support)
android.wakelock = True

# Disable debug output for final release performance
# p4a.local_recipes = 
# p4a.branch = master

[buildozer]
log_level = 2
warn_on_root = 1
