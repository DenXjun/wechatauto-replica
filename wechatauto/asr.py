"""OpenAI-compatible speech-to-text support.

The WeChat media database stores voice messages as SILK.  This module decodes
that data to a temporary WAV file and sends it to an OpenAI-compatible
``/audio/transcriptions`` endpoint.
"""

from __future__ import annotations

import json
import mimetypes
import os
import tempfile
import uuid
import wave
from typing import Optional
from urllib import error, request


class ASRError(RuntimeError):
    """Raised when audio conversion or an ASR request fails."""


class OpenAICompatibleASR:
    """Client for OpenAI-compatible audio transcription services.

    ``base_url`` may be either a host URL or a URL ending in ``/v1``.  When
    omitted, values are read from ``WECHAT_ASR_BASE_URL``,
    ``WECHAT_ASR_API_KEY`` and ``WECHAT_ASR_MODEL``.
    """

    def __init__(self, base_url: Optional[str] = None,
                 api_key: Optional[str] = None,
                 model: Optional[str] = None,
                 timeout: float = 120.0):
        self.base_url = (base_url or os.getenv("WECHAT_ASR_BASE_URL", "")).rstrip("/")
        if not self.base_url:
            raise ASRError("未配置 ASR 服务地址，请传入 base_url 或设置 WECHAT_ASR_BASE_URL")
        if not self.base_url.endswith("/v1"):
            self.base_url += "/v1"
        self.api_key = api_key if api_key is not None else os.getenv("WECHAT_ASR_API_KEY", "")
        self.model = model or os.getenv("WECHAT_ASR_MODEL", "")
        if not self.model:
            raise ASRError("未配置 ASR 模型，请传入 model 或设置 WECHAT_ASR_MODEL")
        self.timeout = timeout

    @staticmethod
    def silk_to_wav(silk_path: str, wav_path: Optional[str] = None,
                    sample_rate: int = 24000) -> str:
        """Decode a WeChat SILK file to a mono 16-bit PCM WAV file."""
        try:
            import pysilk
        except ImportError as exc:
            raise ASRError(
                "SILK 解码需要可选依赖 pysilk，请安装 wechatauto[asr]"
            ) from exc
        if not os.path.isfile(silk_path):
            raise ASRError("语音文件不存在：%s" % silk_path)
        if sample_rate not in (8000, 12000, 16000, 24000):
            raise ASRError("SILK 采样率必须是 8000/12000/16000/24000")
        if wav_path is None:
            fd, wav_path = tempfile.mkstemp(suffix=".wav", prefix="wechatauto_asr_")
            os.close(fd)
        try:
            with open(silk_path, "rb") as source, tempfile.SpooledTemporaryFile() as pcm:
                pysilk.decode(source, pcm, sample_rate)
                pcm.seek(0)
                with wave.open(wav_path, "wb") as wav:
                    wav.setnchannels(1)
                    wav.setsampwidth(2)
                    wav.setframerate(sample_rate)
                    wav.writeframes(pcm.read())
        except Exception as exc:
            if wav_path and os.path.exists(wav_path):
                try:
                    os.remove(wav_path)
                except OSError:
                    pass
            if isinstance(exc, ASRError):
                raise
            raise ASRError("SILK 解码失败：%s" % exc) from exc
        return wav_path

    def transcribe_file(self, audio_path: str,
                        filename: Optional[str] = None) -> str:
        """Transcribe a WAV/MP3/etc. file using ``audio/transcriptions``."""
        if not os.path.isfile(audio_path):
            raise ASRError("音频文件不存在：%s" % audio_path)
        filename = filename or os.path.basename(audio_path)
        content_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
        boundary = "----WechatautoASR" + uuid.uuid4().hex

        def field(name: str, value: str) -> bytes:
            return ("--%s\r\nContent-Disposition: form-data; name=\"%s\"\r\n\r\n%s\r\n"
                    % (boundary, name, value)).encode("utf-8")

        with open(audio_path, "rb") as source:
            audio = source.read()
        body = (
            field("model", self.model)
            + ("--%s\r\nContent-Disposition: form-data; name=\"file\"; "
               "filename=\"%s\"\r\nContent-Type: %s\r\n\r\n"
               % (boundary, filename, content_type)).encode("utf-8")
            + audio + b"\r\n"
            + ("--%s--\r\n" % boundary).encode("ascii")
        )
        headers = {"Content-Type": "multipart/form-data; boundary=%s" % boundary}
        if self.api_key:
            headers["Authorization"] = "Bearer %s" % self.api_key
        req = request.Request(
            self.base_url + "/audio/transcriptions",
            data=body,
            headers=headers,
            method="POST",
        )
        try:
            with request.urlopen(req, timeout=self.timeout) as response:
                raw = response.read()
        except error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")
            raise ASRError("ASR 服务返回 HTTP %s：%s" % (exc.code, detail)) from exc
        except (error.URLError, TimeoutError, OSError) as exc:
            raise ASRError("ASR 服务请求失败：%s" % exc) from exc

        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ASRError("ASR 服务返回的 JSON 无法解析") from exc
        text = payload.get("text") if isinstance(payload, dict) else None
        if not isinstance(text, str):
            raise ASRError("ASR 服务返回中没有 text 字段")
        return text.strip()

    def transcribe_silk(self, silk_path: str, sample_rate: int = 24000) -> str:
        """Decode one WeChat SILK file and transcribe it."""
        wav_path = self.silk_to_wav(silk_path, sample_rate=sample_rate)
        try:
            return self.transcribe_file(wav_path)
        finally:
            try:
                os.remove(wav_path)
            except OSError:
                pass


__all__ = ["ASRError", "OpenAICompatibleASR"]
