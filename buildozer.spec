[app]
title = AeroVox
package.name = snorerecorder
package.domain = org.minimal
source.dir = .
source.include_exts = py,png,jpg,kv,atlas
version = 1.0

# Requirements: Kivy and PyJnius for Android API access
requirements = python3, kivy==2.3.1, android, pyjnius

# Declare the persistent microphone recording service
services = Recorder:services/recorder.py:foreground:sticky:foregroundServiceType=microphone

# Android Specific Configuration
android.permissions = RECORD_AUDIO,WAKE_LOCK,FOREGROUND_SERVICE,FOREGROUND_SERVICE_MICROPHONE,VIBRATE
android.api = 35
android.minapi = 24
android.archs = arm64-v8a, armeabi-v7a

# Keep the app running when screen is off (WakeLock support)
android.wakelock = True

# Lock the screen to portrait to prevent SDL2 rotation crashes
orientation = portrait

# Disable debug output for final release performance
# p4a.local_recipes = 
p4a.branch = develop

[buildozer]
log_level = 2
warn_on_root = 1
