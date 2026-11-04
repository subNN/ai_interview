from __future__ import annotations

import threading
import time
from collections import deque
from queue import Full, Queue
from typing import Callable, Optional

import numpy as np
import sounddevice as sd

from ..models import AppSettings


SAMPLE_RATE = 16000
FRAME_DURATION_MS = 30
BLOCK_SIZE = 1024


def list_input_devices() -> list[dict]:
    devices: list[dict] = []
    try:
        for index, device in enumerate(sd.query_devices()):
            if int(device.get("max_input_channels", 0)) > 0:
                devices.append(
                    {
                        "index": index,
                        "name": str(device.get("name", f"设备 {index}")),
                        "channels": int(device.get("max_input_channels", 0)),
                    }
                )
    except Exception:
        pass
    return devices


class AudioCapture:
    STREAM_START = object()
    STREAM_END = object()

    def __init__(
        self,
        settings: AppSettings,
        on_level: Optional[Callable[[float], None]] = None,
        on_status: Optional[Callable[[str], None]] = None,
    ):
        self.settings = settings
        self.on_level = on_level
        self.on_status = on_status
        self.frame_samples = int(SAMPLE_RATE * FRAME_DURATION_MS / 1000)
        self.frame_bytes = self.frame_samples * 2
        self.energy_threshold = float(settings.vad_threshold)
        self.noise_floor = 3.0
        self.silence_frames = max(1, int(settings.silence_seconds * 1000 / FRAME_DURATION_MS))
        self.min_frames = max(1, int(settings.min_speech_seconds * 1000 / FRAME_DURATION_MS))
        ring_seconds = max(2.0, settings.min_speech_seconds + 1.0)
        max_blocks = max(1, int(ring_seconds * SAMPLE_RATE / BLOCK_SIZE))

        self.ring_buffer: deque[bytes] = deque(maxlen=max_blocks)
        self.segment_queue: Queue[bytes] = Queue(maxsize=30)
        self.stream_queue: Queue[object] = Queue(maxsize=3000)
        self.is_speaking = False
        self.speech_buffer: list[bytes] = []
        self.silence_count = 0
        self.speech_count = 0
        self._noise_buffer: list[float] = []
        self._calibrated = settings.vad_threshold > 0
        self._leftover = b""
        self._stream = None
        self._pa = None
        self._loopback_running = False
        self._loopback_thread: Optional[threading.Thread] = None
        self._last_level_emit = 0.0

    @staticmethod
    def rms(frame_bytes: bytes) -> float:
        values = np.frombuffer(frame_bytes, dtype=np.int16).astype(np.float64)
        return float(np.sqrt(np.mean(values**2))) if values.size else 0.0

    def _emit_level(self, rms_value: float):
        now = time.monotonic()
        if self.on_level and now - self._last_level_emit >= 0.15:
            self._last_level_emit = now
            self.on_level(min(100.0, max(0.0, rms_value / 100.0)))

    def _is_speech(self, frame_bytes: bytes) -> bool:
        rms_value = self.rms(frame_bytes)
        self._emit_level(rms_value)
        if not self._calibrated and len(self._noise_buffer) < 300:
            self._noise_buffer.append(rms_value)
            if len(self._noise_buffer) == 300:
                self.noise_floor = max(float(np.mean(self._noise_buffer)), 1.0)
                factor = 2.0 if self.settings.vad_adaptive else 2.5
                self.energy_threshold = max(self.settings.vad_threshold, self.noise_floor * factor)
                self._calibrated = True
                if self.on_status:
                    self.on_status(f"VAD 校准完成，阈值 {self.energy_threshold:.0f}")
            return False
        if self.settings.vad_adaptive and self._calibrated:
            self.noise_floor = self.noise_floor * 0.98 + rms_value * 0.02
            self.energy_threshold = max(1.0, self.noise_floor * 2.0)
        return rms_value > self.energy_threshold

    def _callback(self, indata, frames, time_info, status):
        if status and status.input_overflow:
            return
        audio_int16 = (indata[:, 0] * 32767).clip(-32768, 32767).astype(np.int16).tobytes()
        self.ring_buffer.append(audio_int16)
        data = self._leftover + audio_int16
        offset = 0
        while offset + self.frame_bytes <= len(data):
            frame = data[offset : offset + self.frame_bytes]
            offset += self.frame_bytes
            if self._is_speech(frame):
                self.speech_count += 1
                if self.speech_count >= 3 and not self.is_speaking:
                    self.is_speaking = True
                    self._put_stream(self.STREAM_START)
                    for block in list(self.ring_buffer)[-4:-1]:
                        self.speech_buffer.append(block)
                        self._put_stream(block)
                if self.is_speaking:
                    self.speech_buffer.append(frame)
                    self._put_stream(frame)
                self.silence_count = 0
            elif self.is_speaking:
                self.speech_buffer.append(frame)
                self._put_stream(frame)
                self.silence_count += 1
                if self.silence_count >= self.silence_frames:
                    self._put_stream(self.STREAM_END)
                    self._finish_segment()
            else:
                self.speech_count = 0
        self._leftover = data[offset:]

    def _put_stream(self, item):
        try:
            self.stream_queue.put_nowait(item)
        except Full:
            try:
                self.stream_queue.get_nowait()
            except Exception:
                pass
            try:
                self.stream_queue.put_nowait(item)
            except Full:
                pass

    def _put_segment(self, audio_bytes: bytes):
        try:
            self.segment_queue.put_nowait(audio_bytes)
        except Full:
            try:
                self.segment_queue.get_nowait()
            except Exception:
                pass
            try:
                self.segment_queue.put_nowait(audio_bytes)
            except Full:
                pass
    def _finish_segment(self):
        if len(self.speech_buffer) >= self.min_frames:
            self._put_segment(b"".join(self.speech_buffer))
        self.speech_buffer.clear()
        self.is_speaking = False
        self.silence_count = 0
        self.speech_count = 0

    def start(self):
        if self.settings.audio_source == "loopback":
            self._start_loopback()
        else:
            self._start_microphone()

    def _start_microphone(self):
        self._stream = sd.InputStream(
            samplerate=SAMPLE_RATE,
            channels=1,
            device=self.settings.audio_device,
            blocksize=BLOCK_SIZE,
            callback=self._callback,
            dtype=np.float32,
        )
        self._stream.start()

    def _start_loopback(self):
        import pyaudiowpatch as pyaudio

        self._pa = pyaudio.PyAudio()
        loopback = self._pa.get_default_wasapi_loopback()
        self._loopback_rate = int(loopback["defaultSampleRate"])
        self._loopback_channels = int(loopback["maxInputChannels"])
        self._loopback_frames = max(320, int(self._loopback_rate * 0.04))
        self._loopback_running = True

        def read_loopback():
            with self._pa.open(
                format=pyaudio.paInt16,
                channels=self._loopback_channels,
                rate=self._loopback_rate,
                frames_per_buffer=self._loopback_frames,
                input=True,
                input_device_index=loopback["index"],
            ) as stream:
                while self._loopback_running:
                    try:
                        data = stream.read(self._loopback_frames, exception_on_overflow=False)
                    except Exception:
                        if not self._loopback_running:
                            break
                        continue
                    self._process_loopback(data)

        self._loopback_thread = threading.Thread(
            target=read_loopback,
            name="audio-loopback",
            daemon=True,
        )
        self._loopback_thread.start()
        if self.on_status:
            self.on_status(f"正在采集系统声音：{loopback['name']}")

    def _process_loopback(self, data: bytes):
        values = np.frombuffer(data, dtype=np.int16).astype(np.float64)
        if not values.size:
            return
        values = values.reshape(-1, self._loopback_channels)
        mono = values.mean(axis=1)
        duration = len(mono) / self._loopback_rate
        output_count = int(duration * SAMPLE_RATE)
        if output_count < 1:
            return
        x_in = np.linspace(0, duration, len(mono), endpoint=False)
        x_out = np.linspace(0, duration, output_count, endpoint=False)
        resampled = np.interp(x_out, x_in, mono)
        self._callback(
            resampled.reshape(-1, 1).astype(np.float32) / 32768.0,
            len(resampled),
            None,
            None,
        )

    def stop(self):
        self._loopback_running = False
        if self._stream is not None:
            try:
                self._stream.stop()
                self._stream.close()
            finally:
                self._stream = None
        if self._pa is not None:
            try:
                self._pa.terminate()
            except Exception:
                pass
            self._pa = None
        if self._loopback_thread and self._loopback_thread.is_alive():
            self._loopback_thread.join(timeout=0.8)
        self._put_stream(self.STREAM_END)

    def get_recent(self, seconds: float = 5.0) -> bytes:
        needed_blocks = max(1, int(seconds * SAMPLE_RATE / BLOCK_SIZE))
        return b"".join(list(self.ring_buffer)[-needed_blocks:])
