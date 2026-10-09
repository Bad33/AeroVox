
import os
import sys
import time
import wave
import json
import math
import traceback
from collections import deque
from datetime import datetime

from jnius import autoclass

AudioRecord = autoclass("android.media.AudioRecord")
AudioFormat = autoclass("android.media.AudioFormat")
AudioSource = autoclass("android.media.MediaRecorder$AudioSource")

SAMPLE_RATE = 16000
CHANNELS = 1
BYTES_PER_SAMPLE = 2

PRE_ROLL = 2.0
TRIGGER_SECONDS = 0.4
RELEASE_SECONDS = 3.0
MAX_EVENT_SECONDS = 120.0


def save_wav(folder, chunks):
    if not chunks:
        return

    os.makedirs(folder, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    filename = os.path.join(folder, f"snore_{timestamp}.wav")

    with wave.open(filename, "wb") as wav:
        wav.setnchannels(CHANNELS)
        wav.setsampwidth(BYTES_PER_SAMPLE)
        wav.setframerate(SAMPLE_RATE)
        wav.writeframes(b"".join(chunks))


def calculate_rms(data):
    samples = memoryview(data).cast("h")
    if not samples:
        return 0.0

    return math.sqrt(
        sum(int(x) ** 2 for x in samples) / len(samples)
    )


def run(folder, stop_file):
    os.makedirs(folder, exist_ok=True)

    minimum = AudioRecord.getMinBufferSize(
        SAMPLE_RATE,
        AudioFormat.CHANNEL_IN_MONO,
        AudioFormat.ENCODING_PCM_16BIT
    )

    if minimum <= 0:
        raise RuntimeError("Unsupported microphone configuration")

    buffer_bytes = max(4096, minimum)
    if buffer_bytes % 2:
        buffer_bytes += 1

    recorder = AudioRecord(
        AudioSource.MIC,
        SAMPLE_RATE,
        AudioFormat.CHANNEL_IN_MONO,
        AudioFormat.ENCODING_PCM_16BIT,
        buffer_bytes
    )

    if recorder.getState() != AudioRecord.STATE_INITIALIZED:
        recorder.release()
        raise RuntimeError("AudioRecord initialization failed")

    pre_buffer = deque()
    pre_samples = 0
    pre_limit = int(PRE_ROLL * SAMPLE_RATE)

    noise_floor = 200.0
    trigger_time = 0.0
    quiet_time = 0.0

    recording = False
    chunks = []
    event_start = 0.0

    try:
        recorder.startRecording()

        if recorder.getRecordingState() != AudioRecord.RECORDSTATE_RECORDING:
            raise RuntimeError("Microphone did not start")

        while not os.path.exists(stop_file):
            raw = bytearray(buffer_bytes)
            count = recorder.read(raw, 0, buffer_bytes)

            if count < 0:
                raise RuntimeError(f"AudioRecord read failed: {count}")
            if count == 0:
                continue

            count -= count % 2
            if count == 0:
                continue

            data = bytes(raw[:count])
            sample_count = count // 2
            duration = sample_count / SAMPLE_RATE

            rms = calculate_rms(data)
            threshold = max(300.0, noise_floor * 2.5)
            loud = rms > threshold

            if not recording:
                # Slowly adapt to the background sound level
                if not loud:
                    noise_floor = 0.98 * noise_floor + 0.02 * rms

                # Preserve sound from before a trigger
                pre_buffer.append((data, sample_count))
                pre_samples += sample_count

                while pre_samples > pre_limit and len(pre_buffer) > 1:
                    _, removed = pre_buffer.popleft()
                    pre_samples -= removed

                trigger_time = trigger_time + duration if loud else 0.0

                if trigger_time >= TRIGGER_SECONDS:
                    recording = True
                    chunks = [piece for piece, _ in pre_buffer]
                    event_start = time.monotonic()
                    quiet_time = 0.0
                    pre_buffer.clear()
                    pre_samples = 0

            else:
                chunks.append(data)

                quiet_time = quiet_time + duration if not loud else 0.0

                elapsed = time.monotonic() - event_start

                if quiet_time >= RELEASE_SECONDS or elapsed >= MAX_EVENT_SECONDS:
                    save_wav(folder, chunks)
                    chunks = []
                    recording = False
                    trigger_time = 0.0
                    quiet_time = 0.0

    finally:
        # Preserve the final partial event
        try:
            if chunks:
                save_wav(folder, chunks)
        finally:
            try:
                recorder.stop()
            except Exception:
                pass
            recorder.release()


if __name__ == "__main__":
    args = json.loads(os.environ["PYTHON_SERVICE_ARGUMENT"])
    folder = args["folder"]
    stop_file = args["stop_file"]

    try:
        run(folder, stop_file)
    except Exception:
        os.makedirs(folder, exist_ok=True)
        with open(os.path.join(folder, "recorder_error.log"), "a") as log:
            log.write(
                f"\n{datetime.now().isoformat()}\n"
                + traceback.format_exc()
            )
    finally:
        # Service exits after recording ends
        try:
            Service = autoclass("org.kivy.android.PythonService")
            Service.mService.stopSelf()
        except Exception:
            pass
