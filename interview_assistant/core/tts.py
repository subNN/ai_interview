from __future__ import annotations

import threading


class SpeechService:
    def __init__(self):
        self._lock = threading.Lock()
        self._engine = None

    def _get_engine(self):
        if self._engine is None:
            import pyttsx3

            self._engine = pyttsx3.init()
            self._engine.setProperty("rate", 190)
            self._engine.setProperty("volume", 0.9)
        return self._engine

    def speak_async(self, text_value: str):
        if not text_value.strip():
            return
        threading.Thread(
            target=self._speak,
            args=(text_value,),
            name="tts-speaker",
            daemon=True,
        ).start()

    def _speak(self, text_value: str):
        with self._lock:
            try:
                engine = self._get_engine()
                engine.stop()
                engine.say(text_value)
                engine.runAndWait()
            except Exception:
                pass

    def stop(self):
        if self._engine is not None:
            try:
                self._engine.stop()
            except Exception:
                pass
