import os
import time
from datetime import datetime
from kivy.lang import Builder
from kivymd.app import MDApp
from kivy.clock import Clock
from kivy.utils import platform
from kivymd.uix.button import MDRaisedButton
from kivy.properties import StringProperty, NumericProperty, BooleanProperty

# KivyMD UI Layout
KV = '''
MDScreen:
    md_bg_color: 0.1, 0.1, 0.1, 1  # Dark theme for night

    BoxLayout:
        orientation: 'vertical'
        padding: "20dp"
        spacing: "20dp"

        MDLabel:
            text: app.status_text
            theme_text_color: "Custom"
            text_color: app.status_color
            font_style: "H4"
            halign: "center"
            size_hint_y: None
            height: "60dp"

        MDProgressBar:
            id: audio_meter
            value: app.current_volume
            max: 100
            size_hint_y: None
            height: "20dp"
            color: 0.2, 0.8, 0.2, 1

        BoxLayout:
            orientation: 'vertical'
            size_hint_y: None
            height: "80dp"
            
            MDLabel:
                text: f"Trigger Threshold: {int(app.threshold_volume)}"
                theme_text_color: "Secondary"
                halign: "center"
            
            MDSlider:
                min: 5
                max: 100
                value: 30
                on_value: app.threshold_volume = self.value
                hint: False

        MDRaisedButton:
            text: "STOP MONITORING" if app.is_monitoring else "START MONITORING"
            md_bg_color: (0.8, 0.2, 0.2, 1) if app.is_monitoring else (0.2, 0.6, 0.2, 1)
            pos_hint: {"center_x": .5}
            size_hint: (0.8, None)
            height: "60dp"
            font_style: "H6"
            on_release: app.toggle_monitoring()

        ScrollView:
            MDList:
                id: log_list
                MDLabel:
                    text: app.log_text
                    theme_text_color: "Hint"
                    size_hint_y: None
                    height: self.texture_size[1]
'''

class SnoreRecorderApp(MDApp):
    status_text = StringProperty("Status: IDLE")
    status_color = (0.7, 0.7, 0.7, 1)
    current_volume = NumericProperty(0)
    threshold_volume = NumericProperty(30)
    is_monitoring = BooleanProperty(False)
    log_text = StringProperty("Session Logs:\n")

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.mr = None
        self.audio_event = None
        self.is_recording = False
        self.trigger_time = 0
        self.silence_time = 0
        self.record_start_time = 0
        self.current_filepath = ""
        
        # Max amplitude from MediaRecorder is 32767. We map this to 0-100.
        self.MAX_AMP = 32767.0
        
        if platform == 'android':
            from android.permissions import request_permissions, Permission
            request_permissions([
                Permission.RECORD_AUDIO,
                Permission.WRITE_EXTERNAL_STORAGE,
                Permission.READ_EXTERNAL_STORAGE,
                Permission.FOREGROUND_SERVICE
            ])
            # Set up private app storage directory
            from jnius import autoclass
            PythonActivity = autoclass('org.kivy.android.PythonActivity')
            self.storage_dir = PythonActivity.mActivity.getExternalFilesDir(None).getAbsolutePath()
        else:
            self.storage_dir = os.path.dirname(os.path.abspath(__file__))

    def build(self):
        self.theme_cls.theme_style = "Dark"
        self.cleanup_old_files()
        return Builder.load_string(KV)

    def log(self, msg):
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_text += f"[{timestamp}] {msg}\n"

    def cleanup_old_files(self):
        """Deletes M4A files older than 3 days in the app's local storage."""
        try:
            now = time.time()
            deleted_count = 0
            for filename in os.listdir(self.storage_dir):
                if filename.endswith(".m4a"):
                    filepath = os.path.join(self.storage_dir, filename)
                    if os.stat(filepath).st_mtime < now - (3 * 86400):
                        os.remove(filepath)
                        deleted_count += 1
            if deleted_count > 0:
                self.log(f"Purged {deleted_count} old file(s).")
        except Exception as e:
            self.log(f"Cleanup error: {e}")

    def toggle_monitoring(self):
        if self.is_monitoring:
            self.stop_monitoring()
        else:
            self.start_monitoring()

    def _get_media_recorder(self, filepath):
        if platform != 'android':
            return None
        from jnius import autoclass
        MediaRecorder = autoclass('android.media.MediaRecorder')
        AudioSource = autoclass('android.media.MediaRecorder$AudioSource')
        OutputFormat = autocHere is the complete project for the "Minimal Snore Recorder". 

To achieve the precise VOX timing (1.5s trigger, 5s release) and continuous ambient analysis, we use Android's native `AudioRecord` class via `pyjnius` to analyze raw PCM data. 

*Note: Pure Python on Android lacks a built-in AAC/M4A encoder for raw PCM streams. The provided code outputs compressed WAV files, which are highly compatible. For production-grade M4A encoding, you would typically compile `ffmpeg-python` into your Buildozer toolchain or write a dedicated Java background service to utilize Android's `MediaCodec`.*

### File 1: `main.py`

```python
import os
import time
import math
import wave
import threading
from datetime import datetime, timedelta

from kivy.app import App
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.properties import StringProperty, NumericProperty, BooleanProperty
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.slider import Slider
from kivy.uix.scrollview import ScrollView
from kivy.utils import platform

# Android specific imports
if platform == 'android':
    from android.permissions import request_permissions, Permission
    from jnius import autoclass
    from android.storage import primary_external_storage_path
    
    AudioRecord = autoclass('android.media.AudioRecord')
    AudioFormat = autoclass('android.media.AudioFormat')
    MediaRecorder = autoclass('android.media.MediaRecorder')
    # Used to prevent CPU from sleeping
    PowerManager = autoclass('android.os.PowerManager')
    Context = autoclass('android.content.Context')
    PythonActivity = autoclass('org.kivy.android.PythonActivity')
else:
    # Mocks for desktop testing
    primary_external_storage_path = lambda: os.path.dirname(os.path.abspath(__file__))

# Audio Configuration
SAMPLE_RATE = 16000
BUFFER_SIZE = 2048
TRIGGER_DURATION = 1.5  # seconds
RELEASE_DURATION = 5.0  # seconds
MAX_RECORD_TIME = 120   # 2 minutes

class SnoreRecorderApp(App):
    status_text = StringProperty("Status: IDLE")
    current_volume = NumericProperty(0)
    threshold = NumericProperty(1500)
    is_monitoring = BooleanProperty(False)
    log_text = StringProperty("App started.\n")

    def build(self):
        Window.clearcolor = (0.05, 0.05, 0.05, 1) # Dark theme
        self.save_dir = os.path.join(primary_external_storage_path(), "SnoreRecords")
        
        if not os.path.exists(self.save_dir):
            os.makedirs(self.save_dir, exist_ok=True)
            
        self.purge_old_files()

        # UI Layout
        layout = BoxLayout(orientation='vertical', padding=20, spacing=20)
        
        self.status_label = Label(text=self.status_text, font_size='24sp', bold=True, size_hint=(1, 0.2))
        layout.add_widget(self.status_label)
        
        self.meter_label = Label(text="Volume: 0", font_size='18sp', size_hint=(1, 0.1))
        layout.add_widget(self.meter_label)
        
        # Sensitivity Slider
        slider_layout = BoxLayout(orientation='vertical', size_hint=(1, 0.2))
        slider_layout.add_widget(Label(text="Trigger Threshold"))
        self.slider = Slider(min=0, max=5000, value=self.threshold)
        self.slider.bind(value=self.update_threshold)
        slider_layout.add_widget(self.slider)
        layout.add_widget(slider_layout)
        
        # Start/Stop Button
        self.toggle_btn = Button(
            text="START MONITORING", 
            background_color=(0.2, 0.8, 0.2, 1),
            font_size='20sp', 
            bold=True, 
            size_hint=(1, 0.2)
        )
        self.toggle_btn.bind(on_press=self.toggle_monitoring)
        layout.add_widget(self.toggle_btn)
        
        # Log Viewer
        scroll = ScrollView(size_hint=(1, 0.3))
        self.log_label = Label(text=self.log_text, text_size=(Window.width * 0.9, None), halign='left', valign='top')
        self.log_label.bind(texture_size=self.log_label.setter('size'))
        scroll.add_widget(self.log_label)
        layout.add_widget(scroll)
        
        self.bind(status_text=self.update_ui, current_volume=self.update_ui, log_text=self.update_ui)
        
        if platform == 'android':
            request_permissions([
                Permission.RECORD_AUDIO, 
                Permission.WRITE_EXTERNAL_STORAGE, 
                Permission.READ_EXTERNAL_STORAGE,
                Permission.FOREGROUND_SERVICE
            ])
            self.acquire_wakelock()

        return layout

    def update_threshold(self, instance, value):
        self.threshold = value

    def update_ui(self, *args):
        self.status_label.text = self.status_text
        self.meter_label.text = f"Volume: {int(self.current_volume)} / {int(self.threshold)}"
        self.log_label.text = self.log_text

    def log(self, message):
        timestamp = datetime.now().strftime("%H:%M:%S")
        new_text = self.log_text + f"[{timestamp}] {message}\n"
        # Keep log short
        lines = new_text.split('\n')
        if len(lines) > 20:
            lines = lines[-20:]
        self.log_text = '\n'.join(lines)

    def purge_old_files(self):
        now = time.time()
        cutoff = now - (3 * 86400) # 3 days in seconds
        count = 0
        for f in os.listdir(self.save_dir):
            file_path = os.path.join(self.save_dir, f)
            if os.path.isfile(file_path):
                if os.path.getmtime(file_path) < cutoff:
                    os.remove(file_path)
                    count += 1
        if count > 0:
            self.log(f"Purged {count} old recordings.")

    def acquire_wakelock(self):
        # Keep CPU awake to monitor audio when screen is off
        activity = PythonActivity.mActivity
        pm = activity.getSystemService(Context.POWER_SERVICE)
        self.wakelock = pm.newWakeLock(PowerManager.PARTIAL_WAKE_LOCK, "SnoreRecorder::Wakelock")
        self.wakelock.acquire()

    def release_wakelock(self):
        if hasattr(self, 'wakelock') and self.wakelock.isHeld():
            self.wakelock.release()

    def toggle_monitoring(self, instance):
        if not self.is_monitoring:
            self.is_monitoring = True
            self.toggle_btn.text = "STOP MONITORING"
            self.toggle_btn.background_color = (0.8, 0.2, 0.2, 1)
            self.status_text = "Status: LISTENING"
            self.log("Started monitoring.")
            threading.Thread(target=self.audio_loop, daemon=True).start()
        else:
            self.is_monitoring = False
            self.toggle_btn.text = "START MONITORING"
            self.toggle_btn.background_color = (0.2, 0.8, 0.2, 1)
            self.status_text = "Status: IDLE"
            self.current_volume = 0
            self.log("Stopped monitoring.")

    def audio_loop(self):
        if platform != 'android':
            return # Mock exit for desktop

        # Set up Android AudioRecord
        AudioSource = autoclass('android.media.MediaRecorder$AudioSource')
        min_buffer = AudioRecord.getMinBufferSize(SAMPLE_RATE, AudioFormat.CHANNEL_IN_MONO, AudioFormat.ENCODING_PCM_16BIT)
        buffer_size = max(min_buffer, BUFFER_SIZE)
        
        recorder = AudioRecord(AudioSource.MIC, SAMPLE_RATE, AudioFormat.CHANNEL_IN_MONO, AudioFormat.ENCODING_PCM_16BIT, buffer_size)
        recorder.startRecording()

        audio_data = []
        is_recording = False
        trigger_frames = 0
        release_frames = 0
        record_start_time = 0

        frames_per_sec = SAMPLE_RATE / (buffer_size / 2) # 16-bit = 2 bytes per sample
        frames_for_trigger = int(TRIGGER_DURATION * frames_per_sec)
        frames_for_release = int(RELEASE_DURATION * frames_per_sec)

        try:
            while self.is_monitoring:
                short_array = bytearray(buffer_size)
                read_result = recorder.read(short_array, 0, buffer_size)
                
                if read_result > 0:
                    # Calculate RMS
                    sum_squares = sum((int.from_bytes(short_array[i:i+2], byteorder='little', signed=True) ** 2) for i in range(0, read_result, 2))
                    rms = math.sqrt(sum_squares / (read_result / 2))
                    Clock.schedule_once(lambda dt, r=rms: setattr(self, 'current_volume', r))

                    if rms > self.threshold:
                        trigger_frames += 1
                        release_frames = 0
                    else:
                        release_frames += 1
                        trigger_frames = 0 if not is_recording else trigger_frames

                    if not is_recording and trigger_frames >= frames_for_trigger:
                        is_recording = True
                        audio_data = []
                        record_start_time = time.time()
                        Clock.schedule_once(lambda dt: setattr(self, 'status_text', "Status: RECORDING"))
                        Clock.schedule_once(lambda dt: self.log("Snore detected, recording..."))

                    if is_recording:
                        audio_data.append(short_array)
                        
                        time_recording = time.time() - record_start_time
                        if release_frames >= frames_for_release or time_recording >= MAX_RECORD_TIME:
                            self.save_recording(audio_data)
                            is_recording = False
                            trigger_frames = 0
                            audio_data = []
                            Clock.schedule_once(lambda dt: setattr(self, 'status_text', "Status: LISTENING"))

        finally:
            recorder.stop()
            recorder.release()

    def save_recording(self, data_chunks):
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = os.path.join(self.save_dir, f"snore_{timestamp}.wav")
        
        with wave.open(filename, 'wb') as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(SAMPLE_RATE)
            for chunk in data_chunks:
                wf.writeframes(chunk)
                
        size_mb = os.path.getsize(filename) / (1024 * 1024)
        Clock.schedule_once(lambda dt: self.log(f"Saved: snore_{timestamp}.wav ({size_mb:.2f} MB)"))

    def on_stop(self):
        self.is_monitoring = False
        self.release_wakelock()

if __name__ == '__main__':
    SnoreRecorderApp().run()
