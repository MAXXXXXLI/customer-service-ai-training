"""Server-side client for iFlytek's streaming voice-dictation WebSocket API.

The browser records microphone audio as mono PCM.  It sends the audio only to
this application, which signs and forwards it to iFlytek; API credentials are
never present in JavaScript or sent to a visitor.
"""

from __future__ import annotations

import base64
import binascii
import json
import os
import time
from dataclasses import dataclass
from typing import Any, Callable, Mapping

from iflytek_tts import (
    SlidingWindowLimiter,
    TTSTimeoutError,
    TTSProtocolError,
    TTSUpstreamError,
    _StdlibWebSocket,
    build_signed_url,
)


DEFAULT_ENDPOINT = "wss://iat-api.xfyun.cn/v2/iat"
DEFAULT_SAMPLE_RATE = 16000
DEFAULT_MAX_DURATION_SECONDS = 30
DEFAULT_FRAME_BYTES = 1280  # 40 ms of 16 kHz, mono, signed 16-bit PCM.


class ASRError(RuntimeError):
    """Base error that is safe to present through the HTTP boundary."""


class ASRConfigurationError(ASRError):
    pass


class ASRValidationError(ASRError, ValueError):
    pass


class ASRRateLimitError(ASRError):
    pass


class ASRTimeoutError(ASRError):
    pass


class ASRUpstreamError(ASRError):
    pass


class ASRProtocolError(ASRError):
    pass


@dataclass(frozen=True)
class ASRSettings:
    app_id: str = ""
    api_key: str = ""
    api_secret: str = ""
    endpoint: str = DEFAULT_ENDPOINT
    language: str = "zh_cn"
    accent: str = "mandarin"
    sample_rate: int = DEFAULT_SAMPLE_RATE
    max_duration_seconds: int = DEFAULT_MAX_DURATION_SECONDS
    max_audio_bytes: int = DEFAULT_SAMPLE_RATE * 2 * DEFAULT_MAX_DURATION_SECONDS
    frame_bytes: int = DEFAULT_FRAME_BYTES
    frame_interval_seconds: float = 0.04
    timeout_seconds: float = 45.0
    rate_limit: int = 20
    rate_window_seconds: float = 60.0

    @property
    def configured(self) -> bool:
        return bool(self.app_id and self.api_key and self.api_secret)

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> "ASRSettings":
        values = os.environ if env is None else env

        def text(name: str, default: str = "") -> str:
            return str(values.get(name, default) or "").strip()

        def inherited(name: str, legacy_name: str) -> str:
            return text(name) or text(legacy_name)

        def number(name: str, default: float, minimum: float, maximum: float, *, integer: bool = False) -> float | int:
            raw = text(name, str(default))
            try:
                value = int(raw) if integer else float(raw)
            except (TypeError, ValueError) as exc:
                raise ASRConfigurationError(f"{name} must be numeric") from exc
            if value < minimum or value > maximum:
                raise ASRConfigurationError(f"{name} is outside the allowed range")
            return value

        endpoint = text("IFLYTEK_IAT_ENDPOINT", DEFAULT_ENDPOINT)
        if not endpoint.startswith(("ws://", "wss://")) or "/" not in endpoint.removeprefix("wss://").removeprefix("ws://"):
            raise ASRConfigurationError("IFLYTEK_IAT_ENDPOINT must be a ws(s) URL")
        sample_rate = int(number("IFLYTEK_IAT_SAMPLE_RATE", DEFAULT_SAMPLE_RATE, 8000, 16000, integer=True))
        if sample_rate not in {8000, 16000}:
            raise ASRConfigurationError("IFLYTEK_IAT_SAMPLE_RATE must be 8000 or 16000")
        max_duration = int(number("IFLYTEK_IAT_MAX_DURATION_SECONDS", DEFAULT_MAX_DURATION_SECONDS, 1, 60, integer=True))
        max_audio = int(number("IFLYTEK_IAT_MAX_AUDIO_BYTES", sample_rate * 2 * max_duration, 320, sample_rate * 2 * 60, integer=True))
        frame_bytes = int(number("IFLYTEK_IAT_FRAME_BYTES", DEFAULT_FRAME_BYTES, 320, 9216, integer=True))
        if frame_bytes % 2:
            raise ASRConfigurationError("IFLYTEK_IAT_FRAME_BYTES must contain complete PCM samples")
        return cls(
            # A single iFlytek app can enable both TTS and voice dictation.
            # Explicit IAT variables win, otherwise reuse that app's HMAC credentials.
            app_id=inherited("IFLYTEK_IAT_APP_ID", "IFLYTEK_TTS_APP_ID"),
            api_key=inherited("IFLYTEK_IAT_API_KEY", "IFLYTEK_TTS_API_KEY"),
            api_secret=inherited("IFLYTEK_IAT_API_SECRET", "IFLYTEK_TTS_API_SECRET"),
            endpoint=endpoint,
            language=text("IFLYTEK_IAT_LANGUAGE", "zh_cn"),
            accent=text("IFLYTEK_IAT_ACCENT", "mandarin"),
            sample_rate=sample_rate,
            max_duration_seconds=max_duration,
            max_audio_bytes=max_audio,
            frame_bytes=frame_bytes,
            frame_interval_seconds=float(number("IFLYTEK_IAT_FRAME_INTERVAL_SECONDS", 0.04, 0.0, 0.2)),
            timeout_seconds=float(number("IFLYTEK_IAT_TIMEOUT", 45, 1, 90)),
            rate_limit=int(number("IFLYTEK_IAT_RATE_LIMIT", 20, 1, 120, integer=True)),
            rate_window_seconds=float(number("IFLYTEK_IAT_RATE_WINDOW", 60, 1, 3600)),
        )


@dataclass(frozen=True)
class TranscriptionResult:
    text: str
    duration_ms: int


def decode_pcm_audio(value: Any, *, sample_rate: Any, settings: ASRSettings) -> bytes:
    if not isinstance(value, str) or not value.strip():
        raise ASRValidationError("audio_base64 must be a non-empty base64 string")
    if isinstance(sample_rate, bool) or not isinstance(sample_rate, int) or sample_rate != settings.sample_rate:
        raise ASRValidationError(f"sample_rate must be {settings.sample_rate}")
    try:
        audio = base64.b64decode(value, validate=True)
    except (ValueError, binascii.Error) as exc:
        raise ASRValidationError("audio_base64 is invalid") from exc
    if not audio or len(audio) % 2:
        raise ASRValidationError("audio must be non-empty 16-bit PCM")
    if len(audio) > settings.max_audio_bytes:
        raise ASRValidationError("recording is too long")
    duration_seconds = len(audio) / (settings.sample_rate * 2)
    if duration_seconds > settings.max_duration_seconds:
        raise ASRValidationError("recording exceeds the duration limit")
    return audio


def result_text(result: Any) -> str:
    if not isinstance(result, dict):
        return ""
    words = result.get("ws")
    if not isinstance(words, list):
        return ""
    pieces: list[str] = []
    for item in words:
        if not isinstance(item, dict):
            continue
        candidates = item.get("cw")
        if not isinstance(candidates, list) or not candidates:
            continue
        candidate = candidates[0]
        if isinstance(candidate, dict) and isinstance(candidate.get("w"), str):
            pieces.append(candidate["w"])
    return "".join(pieces).strip()


class IflytekASRClient:
    def __init__(
        self,
        settings: ASRSettings,
        *,
        ws_factory: Callable[[str, float, Mapping[str, str] | None], Any] | None = None,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        self.settings = settings
        self._ws_factory = ws_factory or (lambda url, timeout, headers=None: _StdlibWebSocket(url, timeout, headers))
        self._sleeper = sleeper
        self._limiter = SlidingWindowLimiter(settings.rate_limit, settings.rate_window_seconds)

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> "IflytekASRClient":
        return cls(ASRSettings.from_env(env))

    @property
    def configured(self) -> bool:
        return self.settings.configured

    def transcribe_result(self, audio_base64: Any, *, sample_rate: Any, rate_key: str = "global") -> TranscriptionResult:
        if not self.configured:
            raise ASRConfigurationError("讯飞语音识别尚未配置完整凭据")
        audio = decode_pcm_audio(audio_base64, sample_rate=sample_rate, settings=self.settings)
        if not self._limiter.allow(rate_key):
            raise ASRRateLimitError("语音识别请求过于频繁，请稍后再试")

        url = build_signed_url(self.settings.endpoint, self.settings.api_key, self.settings.api_secret)
        business = {"language": self.settings.language, "domain": "iat", "accent": self.settings.accent}
        chunks = [audio[index:index + self.settings.frame_bytes] for index in range(0, len(audio), self.settings.frame_bytes)]
        ws = None
        segments: dict[int, str] = {}
        final_seen = False
        try:
            ws = self._ws_factory(url, self.settings.timeout_seconds, None)
            for index, chunk in enumerate(chunks):
                payload: dict[str, Any] = {
                    "data": {
                        "status": 0 if index == 0 else 1,
                        "format": f"audio/L16;rate={self.settings.sample_rate}",
                        "encoding": "raw",
                        "audio": base64.b64encode(chunk).decode("ascii"),
                    }
                }
                if index == 0:
                    payload["common"] = {"app_id": self.settings.app_id}
                    payload["business"] = business
                ws.send_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))
                if index < len(chunks) - 1 and self.settings.frame_interval_seconds:
                    self._sleeper(self.settings.frame_interval_seconds)
            ws.send_text(json.dumps({"data": {"status": 2}}, separators=(",", ":")))

            while not final_seen:
                try:
                    response = json.loads(ws.recv_text())
                except (TypeError, json.JSONDecodeError) as exc:
                    raise ASRProtocolError("讯飞返回了无效 JSON") from exc
                if not isinstance(response, dict):
                    raise ASRProtocolError("讯飞返回的 JSON 不是对象")
                try:
                    code = int(response.get("code", 0))
                except (TypeError, ValueError) as exc:
                    raise ASRProtocolError("讯飞返回了无效错误码") from exc
                if code != 0:
                    raise ASRUpstreamError(f"讯飞语音识别失败（错误码 {code}）")
                data = response.get("data") if isinstance(response.get("data"), dict) else {}
                result = data.get("result") if isinstance(data.get("result"), dict) else {}
                piece = result_text(result)
                if piece:
                    try:
                        serial = int(result.get("sn", len(segments)))
                    except (TypeError, ValueError):
                        serial = len(segments)
                    segments[serial] = piece
                final_seen = int(data.get("status", 0)) == 2 or bool(result.get("ls"))
            transcript = "".join(segments[index] for index in sorted(segments)).strip()
            if not transcript:
                raise ASRUpstreamError("未识别到清晰语音，请再试一次")
            return TranscriptionResult(transcript, round(len(audio) * 1000 / (self.settings.sample_rate * 2)))
        except TTSTimeoutError as exc:
            raise ASRTimeoutError("讯飞语音识别响应超时") from exc
        except TTSUpstreamError as exc:
            raise ASRUpstreamError("讯飞语音识别连接失败") from exc
        except TTSProtocolError as exc:
            raise ASRProtocolError("讯飞语音识别协议异常") from exc
        finally:
            if ws is not None:
                try:
                    ws.close()
                except Exception:
                    pass
