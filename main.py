import os
import time
import math
import wave
import threading
from datetime import datetime

from kivy.app import App
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.core.audio import SoundLoader
from kivy.properties import StringProperty, NumericProperty, BooleanProperty
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.slider import Slider
from kivy.uix.scrollview import ScrollView
from kivy.uix.gridlayout import GridLayout
from kivy.uix.popup import Popup
from kivy.utils import platform

# Android specific imports
if platform == 'android':
    from android.permissions import request_permissions, Permission
    from jnius import autoclass
    from android.storage import primary_external_storage_path
    
    AudioRecord = autoclass('android.media.AudioRecord')
    AudioFormat = autoclass('android.media.AudioFormat')
    MediaRecorder = autoclass('android.media.MediaRecorder')
    PowerManager = autoclass('android.os.PowerManager')
    Context = autoclass('android.content.Context')
    PythonActivity = autoclass('org.kivy.android.PythonActivity')
else:
    primary_external_storage_path = lambda: os.path.dirname(os.path.abspath(__file__))

# Audio Configuration
SAMPLE_RATE = 16000
BUFFER_SIZE = 2048
TRIGGER_DURATION = 1.5
RELEASE_DURATION = 5.0
MAX_RECORD_TIME = 120

class SnoreRecorderApp(App):
    status_text = StringProperty("Status: IDLE")
    current_volume = NumericProperty(0)
    threshold = NumericProperty(1500)
    is_monitoring = BooleanProperty(False)
    nudge_enabled = BooleanProperty(False)
    log_text = StringProperty("App started.\n")

    def build(self):
        Window.clearcolor = (0.05, 0.05, 0.05, 1) # Dark theme
        self.save_dir = os.path.join(primary_external_storage_path(), "SnoreRecords")
        
        if not os.path.exists(self.save_dir):
            os.makedirs(self.save_dir, exist_ok=True)
            
        self.purge_old_files()
        self.current_playback = None 

        # Main UI Layout
        layout = BoxLayout(orientation='vertical', padding=20, spacing=15)
        
        self.status_label = Label(text=self.status_text, font_size='24sp', bold=True, size_hint=(1, 0.15))
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

        # Smart Nudge Toggle
        nudge_layout = BoxLayout(orientation='horizontal', size_hint=(1, 0.15), padding=[0, 10, 0, 10])
        nudge_layout.add_widget(Label(text="Smart Nudge (Vibrate):", font_size='18sp', halign='left'))
        self.nudge_btn = Button(text="OFF", background_color=(0.8, 0.2, 0.2, 1), size_hint=(0.4, 1), bold=True)
        self.nudge_btn.bind(on_press=self.toggle_nudge)
        nudge_layout.add_widget(self.nudge_btn)
        layout.add_widget(nudge_layout)
        
        # Buttons Layout
        btn_layout = BoxLayout(orientation='horizontal', size_hint=(1, 0.2), spacing=15)
        self.toggle_btn = Button(
            text="START\nMONITORING", background_color=(0.2, 0.8, 0.2, 1),
            font_size='18sp', bold=True, halign='center'
        )
        self.toggle_btn.bind(on_press=self.toggle_monitoring)
        btn_layout.add_widget(self.toggle_btn)

        self.listen_btn = Button(
            text="LISTEN TO\nSNORES", background_color=(0.2, 0.4, 0.8, 1),
            font_size='18sp', bold=True, halign='center'
        )
        self.listen_btn.bind(on_press=self.open_player_popup)
        btn_layout.add_widget(self.listen_btn)
        
        layout.add_widget(btn_layout)
        
        # Log Viewer
        scroll = ScrollView(size_hint=(1, 0.2))
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
                Permission.FOREGROUND_SERVICE,
                Permission.VIBRATE
            ])
            self.acquire_wakelock()

        return layout

    def toggle_nudge(self, instance):
        self.nudge_enabled = not self.nudge_enabled
        if self.nudge_enabled:
            self.nudge_btn.text = "ON"
            self.nudge_btn.background_color = (0.2, 0.8, 0.2, 1)
        else:
            self.nudge_btn.text = "OFF"
            self.nudge_btn.background_color = (0.8, 0.2, 0.2, 1)

    # --- IN-APP AUDIO PLAYER LOGIC ---
    def open_player_popup(self, instance):
        content = BoxLayout(orientation='vertical', spacing=10, padding=10)
        files = [f for f in os.listdir(self.save_dir) if f.endswith('.wav')]
        files.sort(reverse=True)

        scroll = ScrollView(size_hint=(1, 0.8))
        list_layout = GridLayout(cols=1, spacing=10, size_hint_y=None)
        list_layout.bind(minimum_height=list_layout.setter('height'))

        if not files:
            list_layout.add_widget(Label(text="No snoring recorded yet!", size_hint_y=None, height=50))
        else:
            for f in files:
                row = BoxLayout(orientation='horizontal', size_hint_y=None, height=60, spacing=10)
                display_name = f.replace('snore_', '').replace('.wav', '')
                try:
                    dt = datetime.strptime(display_name, "%Y%m%d_%H%M%S")
                    friendly_name = dt.strftime("%b %d - %I:%M %p")
                except:
                    friendly_name = f
                
                row.add_widget(Label(text=friendly_name, size_hint_x=0.7, font_size='16sp'))
                play_btn = Button(text="PLAY", size_hint_x=0.3, background_color=(0.2, 0.6, 0.2, 1))
                play_btn.bind(on_press=lambda btn, filename=f: self.play_audio(filename))
                row.add_widget(play_btn)
                list_layout.add_widget(row)

        scroll.add_widget(list_layout)
        content.add_widget(scroll)

        close_btn = Button(text="CLOSE", size_hint=(1, 0.2), background_color=(0.8, 0.2, 0.2, 1))
        self.popup = Popup(title="Your Recordings", content=content, size_hint=(0.9, 0.8))
        close_btn.bind(on_press=self.close_popup)
        content.add_widget(close_btn)
        
        self.popup.open()

    def play_audio(self, filename):
        if self.current_playback:
            self.current_playback.stop()
            self.current_playback.unload()
            
        filepath = os.path.join(self.save_dir, filename)
        self.current_playback = SoundLoader.load(filepath)
        
        if self.current_playback:
            self.current_playback.play()
            self.log(f"Playing: {filename}")
        else:
            self.log(f"Error loading {filename}")

    def close_popup(self, instance):
        if self.current_playback:
            self.current_playback.stop()
            self.current_playback.unload()
            self.current_playback = None
        self.popup.dismiss()
    # ---------------------------------

    def update_threshold(self, instance, value):
        self.threshold = value

    def update_ui(self, *args):
        self.status_label.text = self.status_text
        self.meter_label.text = f"Volume: {int(self.current_volume)} / {int(self.threshold)}"
        self.log_label.text = self.log_text

    def log(self, message):
        timestamp = datetime.now().strftime("%H:%M:%S")
        new_text = self.log_text + f"[{timestamp}] {message}\n"
        lines = new_text.split('\n')
        if len(lines) > 20:
            lines = lines[-20:]
        self.log_text = '\n'.join(lines)

    def purge_old_files(self):
        now = time.time()
        cutoff = now - (3 * 86400) 
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
            self.toggle_btn.text = "STOP\nMONITORING"
            self.toggle_btn.background_color = (0.8, 0.2, 0.2, 1)
            self.status_text = "Status: LISTENING"
            self.log("Started monitoring.")
            threading.Thread(target=self.audio_loop, daemon=True).start()
        else:
            self.is_monitoring = False
            self.toggle_btn.text = "START\nMONITORING"
            self.toggle_btn.background_color = (0.2, 0.8, 0.2, 1)
            self.status_text = "Status: IDLE"
            self.current_volume = 0
            self.log("Stopped monitoring.")

    def audio_loop(self):
        if platform != 'android':
            return

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

        frames_per_sec = SAMPLE_RATE / (buffer_size / 2)
        frames_for_trigger = int(TRIGGER_DURATION * frames_per_sec)
        frames_for_release = int(RELEASE_DURATION * frames_per_sec)

        try:
            while self.is_monitoring:
                short_array = bytearray(buffer_size)
                read_result = recorder.read(short_array, 0, buffer_size)
                
                if read_result > 0:
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
                        
                        # --- SMART NUDGE LOGIC ---
                        if self.nudge_enabled:
                            try:
                                vibrator = PythonActivity.mActivity.getSystemService(Context.VIBRATOR_SERVICE)
                                if vibrator.hasVibrator():
                                    try:
                                        # Modern Android Devices
                                        VibrationEffect = autoclass('android.os.VibrationEffect')
                                        effect = VibrationEffect.createOneShot(800, VibrationEffect.DEFAULT_AMPLITUDE)
                                        vibrator.vibrate(effect)
                                    except:
                                        # Fallback for older devices
                                        vibrator.vibrate(800)
                                Clock.schedule_once(lambda dt: self.log("Nudge sent!"))
                            except Exception as e:
                                Clock.schedule_once(lambda dt, err=e: self.log(f"Vibrator err: {err}"))
                        # -------------------------

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
        if self.current_playback:
            self.current_playback.stop()
        self.release_wakelock()

if __name__ == '__main__':
    SnoreRecorderApp().run()
