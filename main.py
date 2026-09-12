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
from kivy.utils import platform, get_color_from_hex
from kivy.graphics import Color, RoundedRectangle

# Android specific imports
if platform == 'android':
    from android.permissions import request_permissions, Permission
    from jnius import autoclass
    
    AudioRecord = autoclass('android.media.AudioRecord')
    AudioFormat = autoclass('android.media.AudioFormat')
    MediaRecorder = autoclass('android.media.MediaRecorder')
    PowerManager = autoclass('android.os.PowerManager')
    Context = autoclass('android.content.Context')
    PythonActivity = autoclass('org.kivy.android.PythonActivity')

# Audio Configuration
SAMPLE_RATE = 16000
BUFFER_SIZE = 2048
TRIGGER_DURATION = 1.5
RELEASE_DURATION = 5.0
MAX_RECORD_TIME = 120

# --- CUSTOM UI WIDGETS ---
class RoundedButton(Button):
    def __init__(self, bg_hex="#2979FF", radius=15, **kwargs):
        super().__init__(**kwargs)
        self.background_normal = ''
        self.background_color = (0, 0, 0, 0)
        self.markup = True
        with self.canvas.before:
            self.bg = Color(rgba=get_color_from_hex(bg_hex))
            self.rect = RoundedRectangle(pos=self.pos, size=self.size, radius=[radius])
        self.bind(pos=self.update_graphics, size=self.update_graphics)

    def update_graphics(self, *args):
        self.rect.pos = self.pos
        self.rect.size = self.size

    def set_color(self, hex_color):
        self.bg.rgba = get_color_from_hex(hex_color)

class RoundedCard(BoxLayout):
    def __init__(self, bg_hex="#1A1A1A", radius=15, **kwargs):
        super().__init__(**kwargs)
        with self.canvas.before:
            Color(rgba=get_color_from_hex(bg_hex))
            self.rect = RoundedRectangle(pos=self.pos, size=self.size, radius=[radius])
        self.bind(pos=self.update_graphics, size=self.update_graphics)

    def update_graphics(self, *args):
        self.rect.pos = self.pos
        self.rect.size = self.size
# -------------------------

class SnoreRecorderApp(App):
    status_text = StringProperty("READY TO SLEEP")
    current_volume = NumericProperty(0)
    threshold = NumericProperty(1500)
    is_monitoring = BooleanProperty(False)
    nudge_enabled = BooleanProperty(False)
    log_text = StringProperty("AeroVox Engine Initialized.\n")

    def build(self):
        Window.clearcolor = get_color_from_hex("#0D0D0D") 
        
        # FIX: Use safe, private internal app storage instead of public hard drive
        self.save_dir = os.path.join(self.user_data_dir, "SnoreRecords")
        
        if not os.path.exists(self.save_dir):
            os.makedirs(self.save_dir, exist_ok=True)
            
        self.purge_old_files()
        self.current_playback = None 

        # Main UI Layout
        layout = BoxLayout(orientation='vertical', padding=30, spacing=20)
        
        # Header
        header = Label(text="[b]AeroVox[/b]", markup=True, font_size='28sp', color=get_color_from_hex("#FFFFFF"), size_hint=(1, 0.1))
        layout.add_widget(header)

        # Status & Meter
        self.status_label = Label(text=self.status_text, font_size='16sp', color=get_color_from_hex("#888888"), size_hint=(1, 0.05))
        layout.add_widget(self.status_label)
        
        self.meter_label = Label(text="[b]0[/b]", markup=True, font_size='70sp', color=get_color_from_hex("#00E676"), size_hint=(1, 0.2))
        layout.add_widget(self.meter_label)
        
        # Threshold Slider Card
        slider_card = RoundedCard(orientation='vertical', padding=20, size_hint=(1, 0.2))
        self.threshold_label = Label(text=f"Trigger Line: [b]{int(self.threshold)}[/b]", markup=True, color=get_color_from_hex("#CCCCCC"))
        slider_card.add_widget(self.threshold_label)
        
        self.slider = Slider(min=0, max=5000, value=self.threshold, cursor_size=(40,40), value_track=True, value_track_color=get_color_from_hex("#2979FF"))
        self.slider.bind(value=self.update_threshold)
        slider_card.add_widget(self.slider)
        layout.add_widget(slider_card)

        # Smart Nudge Card
        nudge_card = RoundedCard(orientation='horizontal', padding=20, size_hint=(1, 0.15))
        nudge_card.add_widget(Label(text="Smart Nudge\n[size=12sp][color=#888888]Vibrate on snore[/color][/size]", markup=True, halign='left', valign='middle'))
        
        self.nudge_btn = RoundedButton(bg_hex="#333333", text="OFF", size_hint=(0.4, 0.8), pos_hint={'center_y': 0.5})
        self.nudge_btn.bind(on_press=self.toggle_nudge)
        nudge_card.add_widget(self.nudge_btn)
        layout.add_widget(nudge_card)
        
        # Action Buttons
        btn_layout = BoxLayout(orientation='horizontal', size_hint=(1, 0.15), spacing=15)
        
        self.toggle_btn = RoundedButton(bg_hex="#2979FF", text="[b]START[/b]", font_size='18sp')
        self.toggle_btn.bind(on_press=self.toggle_monitoring)
        btn_layout.add_widget(self.toggle_btn)

        self.listen_btn = RoundedButton(bg_hex="#333333", text="[b]RECORDS[/b]", font_size='18sp')
        self.listen_btn.bind(on_press=self.open_player_popup)
        btn_layout.add_widget(self.listen_btn)
        
        layout.add_widget(btn_layout)
        
        # Log Viewer
        self.log_label = Label(text=self.log_text, color=get_color_from_hex("#555555"), font_size='12sp', text_size=(Window.width * 0.85, None), halign='center', size_hint=(1, 0.1))
        layout.add_widget(self.log_label)
        
        self.bind(status_text=self.update_ui, current_volume=self.update_ui, log_text=self.update_ui)
        
        if platform == 'android':
            # FIX: Only request dangerous runtime permissions. Vibrate/Service are granted via manifest.
            request_permissions([Permission.RECORD_AUDIO])
            self.acquire_wakelock()

        return layout

    def toggle_nudge(self, instance):
        self.nudge_enabled = not self.nudge_enabled
        if self.nudge_enabled:
            self.nudge_btn.text = "ON"
            self.nudge_btn.set_color("#00E676")
        else:
            self.nudge_btn.text = "OFF"
            self.nudge_btn.set_color("#333333")

    def open_player_popup(self, instance):
        content = BoxLayout(orientation='vertical', spacing=15, padding=20)
        
        with content.canvas.before:
            Color(rgba=get_color_from_hex("#0D0D0D"))
            RoundedRectangle(pos=content.pos, size=content.size, radius=[20])
            
        files = [f for f in os.listdir(self.save_dir) if f.endswith('.wav')]
        files.sort(reverse=True)

        scroll = ScrollView(size_hint=(1, 0.85))
        list_layout = GridLayout(cols=1, spacing=15, size_hint_y=None)
        list_layout.bind(minimum_height=list_layout.setter('height'))

        if not files:
            list_layout.add_widget(Label(text="No sleep data recorded yet.", color=get_color_from_hex("#888888"), size_hint_y=None, height=50))
        else:
            for f in files:
                row = RoundedCard(bg_hex="#1A1A1A", orientation='horizontal', padding=15, size_hint_y=None, height=80, spacing=10)
                
                display_name = f.replace('snore_', '').replace('.wav', '')
                try:
                    dt = datetime.strptime(display_name, "%Y%m%d_%H%M%S")
                    friendly_name = dt.strftime("%b %d\n[size=14sp][color=#888888]%I:%M %p[/color][/size]")
                except:
                    friendly_name = f
                
                row.add_widget(Label(text=friendly_name, markup=True, halign='left', size_hint_x=0.7))
                play_btn = RoundedButton(bg_hex="#2979FF", text="PLAY", size_hint_x=0.3, radius=10)
                play_btn.bind(on_press=lambda btn, filename=f: self.play_audio(filename))
                row.add_widget(play_btn)
                list_layout.add_widget(row)

        scroll.add_widget(list_layout)
        content.add_widget(scroll)

        close_btn = RoundedButton(bg_hex="#333333", text="CLOSE", size_hint=(1, 0.15))
        self.popup = Popup(title="Sleep Records", title_color=get_color_from_hex("#FFFFFF"), title_align='center', 
                           separator_color=get_color_from_hex("#2979FF"), background='', background_color=(0,0,0,0),
                           content=content, size_hint=(0.9, 0.8))
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

    def close_popup(self, instance):
        if self.current_playback:
            self.current_playback.stop()
            self.current_playback.unload()
            self.current_playback = None
        self.popup.dismiss()

    def update_threshold(self, instance, value):
        self.threshold = value
        self.threshold_label.text = f"Trigger Line: [b]{int(self.threshold)}[/b]"

    def update_ui(self, *args):
        self.status_label.text = self.status_text
        self.meter_label.text = f"[b]{int(self.current_volume)}[/b]"
        
        if self.current_volume > self.threshold:
            self.meter_label.color = get_color_from_hex("#FF1744") 
        else:
            self.meter_label.color = get_color_from_hex("#00E676") 
            
        self.log_label.text = self.log_text

    def log(self, message):
        timestamp = datetime.now().strftime("%H:%M")
        new_text = self.log_text + f"[{timestamp}] {message}\n"
        lines = new_text.split('\n')
        if len(lines) > 4: 
            lines = lines[-4:]
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
            self.toggle_btn.text = "[b]STOP[/b]"
            self.toggle_btn.set_color("#FF1744") 
            self.status_text = "LISTENING FOR SNORES"
            self.log("Monitoring active.")
            threading.Thread(target=self.audio_loop, daemon=True).start()
        else:
            self.is_monitoring = False
            self.toggle_btn.text = "[b]START[/b]"
            self.toggle_btn.set_color("#2979FF") 
            self.status_text = "READY TO SLEEP"
            self.current_volume = 0
            self.log("Monitoring paused.")

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
                        
                        if self.nudge_enabled:
                            try:
                                vibrator = PythonActivity.mActivity.getSystemService(Context.VIBRATOR_SERVICE)
                                if vibrator.hasVibrator():
                                    try:
                                        VibrationEffect = autoclass('android.os.VibrationEffect')
                                        effect = VibrationEffect.createOneShot(800, VibrationEffect.DEFAULT_AMPLITUDE)
                                        vibrator.vibrate(effect)
                                    except:
                                        vibrator.vibrate(800)
                            except:
                                pass 

                        Clock.schedule_once(lambda dt: setattr(self, 'status_text', "RECORDING AUDIO"))
                        Clock.schedule_once(lambda dt: self.log("Snore captured."))

                    if is_recording:
                        audio_data.append(short_array)
                        
                        time_recording = time.time() - record_start_time
                        if release_frames >= frames_for_release or time_recording >= MAX_RECORD_TIME:
                            self.save_recording(audio_data)
                            is_recording = False
                            trigger_frames = 0
                            audio_data = []
                            Clock.schedule_once(lambda dt: setattr(self, 'status_text', "LISTENING FOR SNORES"))

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
                
        Clock.schedule_once(lambda dt: self.log(f"Saved recording successfully."))

    def on_stop(self):
        self.is_monitoring = False
        if self.current_playback:
            self.current_playback.stop()
        self.release_wakelock()

if __name__ == '__main__':
    SnoreRecorderApp().run()
