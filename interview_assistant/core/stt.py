from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import tempfile
import threading
import time
import wave
from queue import Empty, Queue
from typing import Callable, Optional
from urllib.parse import urlencode

from openai import OpenAI

from ..models import AppSettings, Secrets
from .audio import SAMPLE_RATE


class SttError(RuntimeError):
    pass


class SttEngine:
    def __init__(self, settings: AppSettings, secrets: Secrets):
        self.settings = settings
        self.secrets = secrets
        self._openai = None
        self._local_model = None

    def transcribe(self, audio_bytes: bytes) -> str:
        if self.settings.stt_provider == "xunfei":
            return self._transcribe_xunfei_batch(audio_bytes)
        if self.settings.stt_provider == "local":
            return self._transcribe_local(audio_bytes)
        return self._transcribe_openai(audio_bytes)

    def _write_wav(self, audio_bytes: bytes) -> str:
        fd, path = tempfile.mkstemp(suffix=".wav")
        os.close(fd)
        with wave.open(path, "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(SAMPLE_RATE)
            wav.writeframes(audio_bytes)
        return path

    def _get_openai(self) -> OpenAI:
        key = self.secrets.openai_api_key.strip()
        if not key:
            raise SttError("未配置 OpenAI API Key")
        if self._openai is None:
            self._openai = OpenAI(api_key=key)
        return self._openai

    def _transcribe_openai(self, audio_bytes: bytes) -> str:
        path = self._write_wav(audio_bytes)
        try:
            with open(path, "rb") as audio_file:
                result = self._get_openai().audio.transcriptions.create(
                    model=self.settings.stt_model,
                    file=audio_file,
                    language=self.settings.stt_language or None,
                    timeout=30,
                )
            return result.text.strip()
        except Exception as exc:
            raise SttError(f"OpenAI 语音识别失败：{exc}") from exc
        finally:
            try:
                os.unlink(path)
            except OSError:
                pass

    def _transcribe_local(self, audio_bytes: bytes) -> str:
        try:
            from faster_whisper import WhisperModel
        except ImportError as exc:
            raise SttError("本地识别需要 faster-whisper") from exc
        if self._local_model is None:
            compute_type = "int8" if self.settings.local_whisper_device == "cpu" else "float16"
            self._local_model = WhisperModel(
                self.settings.local_whisper_model,
                device=self.settings.local_whisper_device,
                compute_type=compute_type,
            )
        path = self._write_wav(audio_bytes)
        try:
            segments, _ = self._local_model.transcribe(
                path,
                language=self.settings.stt_language or None,
            )
            return " ".join(segment.text.strip() for segment in segments).strip()
        except Exception as exc:
            raise SttError(f"本地语音识别失败：{exc}") from exc
        finally:
            try:
                os.unlink(path)
            except OSError:
                pass

    def _transcribe_xunfei_batch(self, audio_bytes: bytes) -> str:
        import websocket

        if not audio_bytes:
            return ""
        ws = websocket.create_connection(self._xunfei_url(), timeout=15)
        chunk_size = 1280
        chunks = [
            audio_bytes[offset : offset + chunk_size]
            for offset in range(0, len(audio_bytes), chunk_size)
        ]
        if not chunks:
            ws.close()
            return ""
        data_format = "audio/L16;rate=16000"
        try:
            for index, chunk in enumerate(chunks):
                status = 0 if index == 0 else (2 if index == len(chunks) - 1 else 1)
                payload = {
                    "data": {
                        "status": status,
                        "format": data_format,
                        "encoding": "raw",
                        "audio": base64.b64encode(chunk).decode("ascii"),
                    }
                }
                if index == 0:
                    payload["common"] = {"app_id": self.secrets.iflytek_app_id}
                    payload["business"] = {
                        "domain": "iat",
                        "language": "en_us" if self.settings.stt_language == "en" else "zh_cn",
                        "accent": "mandarin",
                        "ptt": 1,
                        "vad_eos": 2000,
                    }
                ws.send(json.dumps(payload))
                if status != 2:
                    time.sleep(chunk_size / (SAMPLE_RATE * 2))

            parts = []
            last_text = ""
            while True:
                message = json.loads(ws.recv())
                if message.get("code", 0) != 0:
                    raise SttError(
                        f"\u8baf\u98de\u8bc6\u522b\u5931\u8d25\uff1a{message.get('code')} {message.get('message', '')}"
                    )
                data = message.get("data", {})
                result = data.get("result", {})
                current = "".join(
                    word.get("w", "")
                    for group in result.get("ws", [])
                    for word in group.get("cw", [])
                )
                if current:
                    new_part = (
                        current[len(last_text) :]
                        if current.startswith(last_text)
                        else current
                    )
                    if new_part:
                        parts.append(new_part)
                    last_text = current
                if data.get("status") == 2:
                    break
            return ("".join(parts) if parts else last_text).strip()
        finally:
            try:
                ws.close()
            except Exception:
                pass

    def _xunfei_url(self) -> str:
        from wsgiref.handlers import format_date_time

        if not all(
            (
                self.secrets.iflytek_app_id,
                self.secrets.iflytek_api_key,
                self.secrets.iflytek_api_secret,
            )
        ):
            raise SttError("讯飞语音听写凭证不完整")
        host = "ws-api.xfyun.cn"
        url = f"wss://{host}/v2/iat"
        date = format_date_time(time.time())
        signature_origin = f"host: {host}\ndate: {date}\nGET /v2/iat HTTP/1.1"
        digest = hmac.new(
            self.secrets.iflytek_api_secret.encode("utf-8"),
            signature_origin.encode("utf-8"),
            digestmod=hashlib.sha256,
        ).digest()
        signature = base64.b64encode(digest).decode("utf-8")
        auth_origin = (
            f'api_key="{self.secrets.iflytek_api_key}", algorithm="hmac-sha256", '
            f'headers="host date request-line", signature="{signature}"'
        )
        authorization = base64.b64encode(auth_origin.encode("utf-8")).decode("utf-8")
        return f"{url}?{urlencode({'authorization': authorization, 'date': date, 'host': host})}"

    def transcribe_streaming(
        self,
        audio_queue: Queue,
        started: bool = False,
        on_partial: Optional[Callable[[str], None]] = None,
        stop_event: Optional[threading.Event] = None,
    ) -> str:
        import websocket

        from .audio import AudioCapture

        if not started:
            while not (stop_event and stop_event.is_set()):
                try:
                    if audio_queue.get(timeout=0.2) is AudioCapture.STREAM_START:
                        break
                except Empty:
                    continue

        try:
            ws = websocket.create_connection(self._xunfei_url(), timeout=10)
        except Exception as exc:
            raise SttError(f"讯飞连接失败：{exc}") from exc

        accumulator = bytearray()
        first_sent = False
        ended = False
        fragments: list[str] = []
        last_text = ""
        chunk_size = 1280
        chunk_delay = chunk_size / (SAMPLE_RATE * 2)
        data_format = "audio/L16;rate=16000"

        try:
            while not ended and not (stop_event and stop_event.is_set()):
                got_end = False
                while len(accumulator) < chunk_size:
                    try:
                        item = audio_queue.get(timeout=0.03)
                    except Empty:
                        break
                    if item is AudioCapture.STREAM_END:
                        got_end = True
                        break
                    if item is not AudioCapture.STREAM_START:
                        accumulator.extend(item)
                chunk = bytes(accumulator)
                if not first_sent and chunk:
                    ws.send(
                        json.dumps(
                            {
                                "common": {"app_id": self.secrets.iflytek_app_id},
                                "business": {
                                    "domain": "iat",
                                    "language": "en_us" if self.settings.stt_language == "en" else "zh_cn",
                                    "accent": "mandarin",
                                    "ptt": 1,
                                    "vad_eos": 2000,
                                },
                                "data": {
                                    "status": 0,
                                    "format": data_format,
                                    "encoding": "raw",
                                    "audio": base64.b64encode(chunk).decode("ascii"),
                                },
                            }
                        )
                    )
                    accumulator.clear()
                    first_sent = True
                    if got_end:
                        ws.send(json.dumps({"data": {"status": 2}}))
                        ended = True
                    else:
                        time.sleep(chunk_delay)
                elif first_sent and (got_end or len(chunk) >= chunk_size):
                    payload = {
                        "status": 2 if got_end else 1,
                        "format": data_format,
                        "encoding": "raw",
                        "audio": base64.b64encode(chunk).decode("ascii"),
                    }
                    ws.send(json.dumps({"data": payload}))
                    accumulator.clear()
                    if got_end:
                        ended = True
                    else:
                        time.sleep(chunk_delay)
                elif got_end:
                    ws.send(json.dumps({"data": {"status": 2}}))
                    ended = True

                old_timeout = ws.gettimeout()
                ws.settimeout(0.03)
                try:
                    while True:
                        try:
                            message = json.loads(ws.recv())
                        except websocket.WebSocketTimeoutException:
                            break
                        except Exception:
                            ended = True
                            break
                        if message.get("code", 0) != 0:
                            raise SttError(
                                f"讯飞识别失败：{message.get('code')} {message.get('message', '')}"
                            )
                        result = message.get("data", {}).get("result", {})
                        current = "".join(
                            word.get("w", "")
                            for group in result.get("ws", [])
                            for word in group.get("cw", [])
                        )
                        if not current:
                            continue
                        new_part = (
                            current[len(last_text) :]
                            if current.startswith(last_text)
                            else current
                        )
                        if new_part:
                            fragments.append(new_part)
                            if on_partial:
                                on_partial(new_part)
                        last_text = current
                finally:
                    try:
                        ws.settimeout(old_timeout)
                    except Exception:
                        pass
        finally:
            try:
                ws.close()
            except Exception:
                pass

        return "".join(fragments) if fragments else last_text
