"""Small, dependency-free client for iFlytek's streaming TTS WebSocket API.

The application intentionally keeps iFlytek credentials on the server. This
module exposes validation, signing, a bounded in-memory cache and a small
WebSocket implementation so the deployment does not need a third-party
runtime package just for speech synthesis.
"""

from __future__ import annotations

import base64
import binascii
import email.utils
import hashlib
import hmac
import json
import os
import socket
import ssl
import struct
import threading
import time
from collections import OrderedDict, deque
from dataclasses import dataclass
from typing import Any, Callable, Mapping
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


DEFAULT_ENDPOINT = "wss://tts-api.xfyun.cn/v2/tts"
DEFAULT_VOICE = "x4_xiaoyan"
DEFAULT_FORMAT = "mp3"
DEFAULT_MAX_TEXT_BYTES = 7999  # The upstream contract says strictly less than 8000.


class TTSError(RuntimeError):
    """Base class for errors safe to handle at the HTTP boundary."""


class TTSConfigurationError(TTSError):
    pass


class TTSValidationError(TTSError, ValueError):
    pass


class TTSRateLimitError(TTSError):
    pass


class TTSTimeoutError(TTSError):
    pass


class TTSUpstreamError(TTSError):
    pass


class TTSProtocolError(TTSError):
    pass


@dataclass(frozen=True)
class TTSSettings:
    app_id: str = ""
    api_key: str = ""
    api_secret: str = ""
    api_password: str = ""
    endpoint: str = DEFAULT_ENDPOINT
    default_voice: str = DEFAULT_VOICE
    default_format: str = DEFAULT_FORMAT
    timeout_seconds: float = 30.0
    max_text_bytes: int = DEFAULT_MAX_TEXT_BYTES
    cache_ttl_seconds: float = 300.0
    cache_size: int = 128
    rate_limit: int = 30
    rate_window_seconds: float = 60.0
    max_audio_bytes: int = 12 * 1024 * 1024

    @property
    def signed_credentials_complete(self) -> bool:
        return bool(self.app_id and self.api_key and self.api_secret)

    @property
    def configured(self) -> bool:
        # APIPassword is an official alternative to the HMAC URL signature.
        # The request body still requires common.app_id for either auth mode.
        return bool(self.app_id and (self.api_password or self.signed_credentials_complete))

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> "TTSSettings":
        values = os.environ if env is None else env

        def text(name: str, default: str = "") -> str:
            return str(values.get(name, default) or "").strip()

        def number(name: str, default: float, minimum: float, integer: bool = False) -> float | int:
            raw = text(name, str(default))
            try:
                value = int(raw) if integer else float(raw)
            except (TypeError, ValueError) as exc:
                raise TTSConfigurationError(f"{name} must be numeric") from exc
            if value < minimum:
                raise TTSConfigurationError(f"{name} is below the minimum")
            return value

        endpoint = text("IFLYTEK_TTS_ENDPOINT", DEFAULT_ENDPOINT)
        parsed = urlsplit(endpoint)
        if parsed.scheme not in {"ws", "wss"} or not parsed.netloc or not parsed.path:
            raise TTSConfigurationError("IFLYTEK_TTS_ENDPOINT must be a ws(s) URL")
        audio_format = text("IFLYTEK_TTS_FORMAT", DEFAULT_FORMAT).lower()
        if audio_format not in {"mp3", "pcm"}:
            raise TTSConfigurationError("IFLYTEK_TTS_FORMAT must be mp3 or pcm")
        max_bytes = int(number("IFLYTEK_TTS_MAX_TEXT_BYTES", DEFAULT_MAX_TEXT_BYTES, 1, integer=True))
        if max_bytes >= 8000:
            raise TTSConfigurationError("IFLYTEK_TTS_MAX_TEXT_BYTES must be less than 8000")
        cache_size = int(number("IFLYTEK_TTS_CACHE_SIZE", 128, 0, integer=True))
        rate_limit = int(number("IFLYTEK_TTS_RATE_LIMIT", 30, 0, integer=True))
        return cls(
            app_id=text("IFLYTEK_TTS_APP_ID"),
            api_key=text("IFLYTEK_TTS_API_KEY"),
            api_secret=text("IFLYTEK_TTS_API_SECRET"),
            api_password=text("IFLYTEK_TTS_API_PASSWORD"),
            endpoint=endpoint,
            default_voice=text("IFLYTEK_TTS_DEFAULT_VOICE", DEFAULT_VOICE),
            default_format=audio_format,
            timeout_seconds=float(number("IFLYTEK_TTS_TIMEOUT", 30.0, 0.1)),
            max_text_bytes=max_bytes,
            cache_ttl_seconds=float(number("IFLYTEK_TTS_CACHE_TTL", 300.0, 0.0)),
            cache_size=cache_size,
            rate_limit=rate_limit,
            rate_window_seconds=float(number("IFLYTEK_TTS_RATE_WINDOW", 60.0, 0.1)),
            max_audio_bytes=int(number("IFLYTEK_TTS_MAX_AUDIO_BYTES", 12 * 1024 * 1024, 1024, integer=True)),
        )


def _safe_header_value(value: str) -> str:
    if "\r" in value or "\n" in value:
        raise TTSConfigurationError("header value contains a newline")
    try:
        value.encode("ascii")
    except UnicodeEncodeError as exc:
        raise TTSConfigurationError("header value must be ASCII") from exc
    return value


def build_signed_url(
    endpoint: str,
    api_key: str,
    api_secret: str,
    *,
    now: float | None = None,
) -> str:
    """Build the RFC1123/HMAC-SHA256 URL from the official API contract."""

    parsed = urlsplit(endpoint)
    if parsed.scheme not in {"ws", "wss"} or not parsed.netloc:
        raise TTSConfigurationError("TTS endpoint must be a ws(s) URL")
    if not api_key or not api_secret:
        raise TTSConfigurationError("signed TTS credentials are incomplete")
    if any(char in api_key for char in '",\r\n'):
        raise TTSConfigurationError("signed API key contains unsupported characters")
    host = _safe_header_value(parsed.netloc)
    path = parsed.path or "/"
    date = email.utils.formatdate(now if now is not None else time.time(), usegmt=True)
    request_line = f"GET {path} HTTP/1.1"
    signature_origin = f"host: {host}\ndate: {date}\n{request_line}"
    signature = base64.b64encode(
        hmac.new(api_secret.encode("utf-8"), signature_origin.encode("utf-8"), hashlib.sha256).digest()
    ).decode("ascii")
    authorization_origin = (
        f'api_key="{_safe_header_value(api_key)}", algorithm="hmac-sha256", '
        f'headers="host date request-line", signature="{signature}"'
    )
    authorization = base64.b64encode(authorization_origin.encode("utf-8")).decode("ascii")
    query = list(parse_qsl(parsed.query, keep_blank_values=True))
    query.extend([("authorization", authorization), ("date", date), ("host", host)])
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path or "/", urlencode(query), parsed.fragment))


def validate_text(text: Any, *, max_bytes: int = DEFAULT_MAX_TEXT_BYTES) -> str:
    if not isinstance(text, str):
        raise TTSValidationError("text must be a string")
    normalized = text.strip()
    if not normalized:
        raise TTSValidationError("text must not be empty")
    if "\x00" in normalized:
        raise TTSValidationError("text contains a NUL byte")
    if len(normalized.encode("utf-8")) > max_bytes:
        raise TTSValidationError(f"text must be shorter than {max_bytes + 1} UTF-8 bytes")
    return normalized


def validate_parameter(value: Any, name: str, default: int) -> int:
    if value is None:
        return default
    if isinstance(value, bool) or not isinstance(value, int):
        raise TTSValidationError(f"{name} must be an integer from 0 to 100")
    if not 0 <= value <= 100:
        raise TTSValidationError(f"{name} must be an integer from 0 to 100")
    return value


def validate_voice(value: Any, default: str) -> str:
    voice = default if value is None else value
    if not isinstance(voice, str) or not voice.strip() or len(voice.strip()) > 64:
        raise TTSValidationError("voice must be a non-empty string no longer than 64 characters")
    voice = voice.strip()
    if any(ord(char) < 0x20 or ord(char) == 0x7F for char in voice):
        raise TTSValidationError("voice contains a control character")
    return voice


def validate_audio_format(value: Any, default: str) -> str:
    audio_format = default if value is None else value
    if not isinstance(audio_format, str) or audio_format.lower() not in {"mp3", "pcm"}:
        raise TTSValidationError("audio_format must be mp3 or pcm")
    return audio_format.lower()


class SlidingWindowLimiter:
    def __init__(self, limit: int, window_seconds: float, clock: Callable[[], float] = time.monotonic) -> None:
        self.limit = max(0, int(limit))
        self.window_seconds = max(0.001, float(window_seconds))
        self.clock = clock
        self._events: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    def allow(self, key: str) -> bool:
        if self.limit == 0:
            return False
        now = self.clock()
        with self._lock:
            events = self._events.setdefault(key or "anonymous", deque())
            cutoff = now - self.window_seconds
            while events and events[0] <= cutoff:
                events.popleft()
            if len(events) >= self.limit:
                return False
            events.append(now)
            # Keep unbounded client-IP cardinality from becoming a memory leak.
            if len(self._events) > 2048:
                oldest = min(self._events, key=lambda item: self._events[item][0] if self._events[item] else now)
                self._events.pop(oldest, None)
            return True


class _StdlibWebSocket:
    """Minimal RFC6455 client for text frames used by the TTS API."""

    def __init__(self, url: str, timeout: float, headers: Mapping[str, str] | None = None) -> None:
        parsed = urlsplit(url)
        if parsed.scheme not in {"ws", "wss"} or not parsed.hostname:
            raise TTSConfigurationError("TTS endpoint must be a ws(s) URL")
        self._closed = False
        self._read_buffer = b""
        port = parsed.port or (443 if parsed.scheme == "wss" else 80)
        raw_socket = socket.create_connection((parsed.hostname, port), timeout=timeout)
        if parsed.scheme == "wss":
            context = ssl.create_default_context()
            self._socket = context.wrap_socket(raw_socket, server_hostname=parsed.hostname)
        else:
            self._socket = raw_socket
        self._socket.settimeout(timeout)
        key = base64.b64encode(os.urandom(16)).decode("ascii")
        target = parsed.path or "/"
        if parsed.query:
            target += "?" + parsed.query
        request_headers = {
            "Host": parsed.netloc,
            "Upgrade": "websocket",
            "Connection": "Upgrade",
            "Sec-WebSocket-Key": key,
            "Sec-WebSocket-Version": "13",
        }
        for name, value in (headers or {}).items():
            request_headers[_safe_header_value(str(name))] = _safe_header_value(str(value))
        request = "GET " + target + " HTTP/1.1\r\n" + "".join(
            f"{name}: {value}\r\n" for name, value in request_headers.items()
        ) + "\r\n"
        try:
            self._socket.sendall(request.encode("ascii"))
            response = self._read_until(b"\r\n\r\n", 65536)
        except (socket.timeout, TimeoutError) as exc:
            self.close()
            raise TTSTimeoutError("讯飞 WebSocket 握手超时") from exc
        status_line = response.split(b"\r\n", 1)[0]
        if not status_line.startswith(b"HTTP/1.1 101 "):
            self.close()
            # Deliberately do not include the upstream body: it can echo auth data.
            raise TTSUpstreamError("讯飞 WebSocket 握手失败")
        response_headers: dict[str, str] = {}
        for line in response.split(b"\r\n")[1:]:
            if not line:
                continue
            try:
                name, value = line.decode("latin-1").split(":", 1)
            except ValueError as exc:
                self.close()
                raise TTSProtocolError("讯飞 WebSocket 握手响应格式错误") from exc
            response_headers[name.strip().lower()] = value.strip()
        expected_accept = base64.b64encode(
            hashlib.sha1((key + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11").encode("ascii")).digest()
        ).decode("ascii")
        if response_headers.get("sec-websocket-accept") != expected_accept:
            self.close()
            raise TTSProtocolError("讯飞 WebSocket 握手校验失败")

    def _read_until(self, marker: bytes, maximum: int) -> bytes:
        buffer = bytearray()
        while marker not in buffer:
            if len(buffer) >= maximum:
                raise TTSProtocolError("WebSocket handshake headers are too large")
            chunk = self._socket.recv(min(4096, maximum - len(buffer)))
            if not chunk:
                raise TTSProtocolError("WebSocket closed during handshake")
            buffer.extend(chunk)
        boundary = buffer.index(marker) + len(marker)
        self._read_buffer = bytes(buffer[boundary:])
        return bytes(buffer[:boundary])

    def _recv_exact(self, size: int) -> bytes:
        buffer = bytearray()
        if self._read_buffer:
            buffered = self._read_buffer[:size]
            buffer.extend(buffered)
            self._read_buffer = self._read_buffer[len(buffered):]
        while len(buffer) < size:
            chunk = self._socket.recv(size - len(buffer))
            if not chunk:
                raise TTSProtocolError("WebSocket closed while reading a frame")
            buffer.extend(chunk)
        return bytes(buffer)

    def _frame(self, opcode: int, payload: bytes) -> bytes:
        first = 0x80 | (opcode & 0x0F)
        length = len(payload)
        if length < 126:
            header = bytes((first, 0x80 | length))
        elif length <= 0xFFFF:
            header = bytes((first, 0x80 | 126)) + struct.pack("!H", length)
        else:
            header = bytes((first, 0x80 | 127)) + struct.pack("!Q", length)
        mask = os.urandom(4)
        masked = bytes(byte ^ mask[index % 4] for index, byte in enumerate(payload))
        return header + mask + masked

    def send_text(self, value: str) -> None:
        if self._closed:
            raise TTSProtocolError("WebSocket is closed")
        self._socket.sendall(self._frame(0x1, value.encode("utf-8")))

    def recv_text(self) -> str:
        fragments: list[bytes] = []
        message_opcode: int | None = None
        while True:
            try:
                header = self._recv_exact(2)
            except socket.timeout as exc:
                raise TTSTimeoutError("讯飞语音合成响应超时") from exc
            first, second = header
            opcode = first & 0x0F
            masked = bool(second & 0x80)
            length = second & 0x7F
            if length == 126:
                length = struct.unpack("!H", self._recv_exact(2))[0]
            elif length == 127:
                length = struct.unpack("!Q", self._recv_exact(8))[0]
            if length > 16 * 1024 * 1024:
                raise TTSProtocolError("WebSocket frame is too large")
            mask = self._recv_exact(4) if masked else b""
            payload = self._recv_exact(length)
            if masked:
                payload = bytes(byte ^ mask[index % 4] for index, byte in enumerate(payload))
            if opcode == 0x8:
                raise TTSProtocolError("讯飞在合成完成前关闭了 WebSocket")
            if opcode == 0x9:
                self._socket.sendall(self._frame(0xA, payload))
                continue
            if opcode == 0xA:
                continue
            if opcode in {0x1, 0x2}:
                message_opcode = opcode
                fragments = [payload]
            elif opcode == 0x0 and message_opcode is not None:
                fragments.append(payload)
            else:
                raise TTSProtocolError("讯飞返回了不支持的 WebSocket 帧")
            if first & 0x80:
                if message_opcode != 0x1:
                    raise TTSProtocolError("讯飞返回了非文本 TTS 帧")
                try:
                    return b"".join(fragments).decode("utf-8")
                except UnicodeDecodeError as exc:
                    raise TTSProtocolError("讯飞返回了无效的 UTF-8 JSON 帧") from exc

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        try:
            self._socket.sendall(self._frame(0x8, struct.pack("!H", 1000)))
        except Exception:
            pass
        try:
            self._socket.shutdown(socket.SHUT_RDWR)
        except Exception:
            pass
        try:
            self._socket.close()
        except Exception:
            pass


@dataclass(frozen=True)
class SynthesisResult:
    audio: bytes
    audio_format: str
    cache_hit: bool


class IflytekTTSClient:
    def __init__(
        self,
        settings: TTSSettings,
        *,
        ws_factory: Callable[[str, float, Mapping[str, str] | None], Any] | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.settings = settings
        self._ws_factory = ws_factory or (lambda url, timeout, headers=None: _StdlibWebSocket(url, timeout, headers))
        self._clock = clock
        self._cache: OrderedDict[tuple[Any, ...], tuple[float, bytes]] = OrderedDict()
        self._cache_lock = threading.Lock()
        self._limiter = SlidingWindowLimiter(settings.rate_limit, settings.rate_window_seconds, clock)

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> "IflytekTTSClient":
        return cls(TTSSettings.from_env(env))

    @property
    def configured(self) -> bool:
        return self.settings.configured

    def _request_url_and_headers(self) -> tuple[str, dict[str, str]]:
        if self.settings.api_password:
            return self.settings.endpoint, {"X-Api-Key": self.settings.api_password}
        if self.settings.signed_credentials_complete:
            return build_signed_url(self.settings.endpoint, self.settings.api_key, self.settings.api_secret), {}
        raise TTSConfigurationError("讯飞 TTS 尚未配置完整凭据")

    def _cache_key(self, text: str, voice: str, speed: int, volume: int, pitch: int, audio_format: str) -> tuple[Any, ...]:
        digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
        return digest, len(text), voice, speed, volume, pitch, audio_format

    def _cache_get(self, key: tuple[Any, ...]) -> bytes | None:
        if self.settings.cache_size <= 0 or self.settings.cache_ttl_seconds <= 0:
            return None
        now = self._clock()
        with self._cache_lock:
            item = self._cache.get(key)
            if item is None:
                return None
            expires, audio = item
            if expires <= now:
                self._cache.pop(key, None)
                return None
            self._cache.move_to_end(key)
            return audio

    def _cache_put(self, key: tuple[Any, ...], audio: bytes) -> None:
        if self.settings.cache_size <= 0 or self.settings.cache_ttl_seconds <= 0:
            return
        with self._cache_lock:
            self._cache[key] = (self._clock() + self.settings.cache_ttl_seconds, audio)
            self._cache.move_to_end(key)
            while len(self._cache) > self.settings.cache_size:
                self._cache.popitem(last=False)

    def synthesize_result(
        self,
        text: Any,
        *,
        voice: Any = None,
        speed: Any = None,
        volume: Any = None,
        pitch: Any = None,
        audio_format: Any = None,
        rate_key: str = "global",
    ) -> SynthesisResult:
        if not self.configured:
            raise TTSConfigurationError("讯飞 TTS 尚未配置完整凭据")
        normalized_text = validate_text(text, max_bytes=self.settings.max_text_bytes)
        normalized_voice = validate_voice(voice, self.settings.default_voice)
        normalized_speed = validate_parameter(speed, "speed", 50)
        normalized_volume = validate_parameter(volume, "volume", 50)
        normalized_pitch = validate_parameter(pitch, "pitch", 50)
        normalized_format = validate_audio_format(audio_format, self.settings.default_format)
        key = self._cache_key(normalized_text, normalized_voice, normalized_speed, normalized_volume, normalized_pitch, normalized_format)
        cached = self._cache_get(key)
        if cached is not None:
            return SynthesisResult(cached, normalized_format, True)
        if not self._limiter.allow(rate_key):
            raise TTSRateLimitError("语音合成请求过于频繁，请稍后再试")
        url, headers = self._request_url_and_headers()
        business: dict[str, Any] = {
            "aue": "lame" if normalized_format == "mp3" else "raw",
            "vcn": normalized_voice,
            "speed": normalized_speed,
            "volume": normalized_volume,
            "pitch": normalized_pitch,
            "tte": "UTF8",
            "bgs": 0,
            "reg": "0",
            "rdn": "0",
        }
        if normalized_format == "mp3":
            business["sfl"] = 1
        else:
            business["auf"] = "audio/L16;rate=16000"
        payload = {
            "common": {"app_id": self.settings.app_id},
            "business": business,
            "data": {
                "status": 2,
                "text": base64.b64encode(normalized_text.encode("utf-8")).decode("ascii"),
                "encoding": "UTF8",
            },
        }
        ws = None
        audio = bytearray()
        finished = False
        deadline = self._clock() + self.settings.timeout_seconds
        try:
            ws = self._ws_factory(url, self.settings.timeout_seconds, headers)
            ws.send_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))
            while self._clock() <= deadline:
                frame = ws.recv_text()
                try:
                    response = json.loads(frame)
                except (TypeError, json.JSONDecodeError) as exc:
                    raise TTSProtocolError("讯飞返回了无效 JSON") from exc
                if not isinstance(response, dict):
                    raise TTSProtocolError("讯飞返回的 JSON 不是对象")
                try:
                    code = int(response.get("code", 0))
                except (TypeError, ValueError) as exc:
                    raise TTSProtocolError("讯飞返回了无效错误码") from exc
                if code != 0:
                    raise TTSUpstreamError(f"讯飞语音合成失败（错误码 {code}）")
                data = response.get("data") if isinstance(response.get("data"), dict) else {}
                encoded_audio = data.get("audio", "")
                if encoded_audio:
                    if not isinstance(encoded_audio, str):
                        raise TTSProtocolError("讯飞音频字段格式错误")
                    try:
                        audio.extend(base64.b64decode(encoded_audio, validate=True))
                    except (ValueError, binascii.Error) as exc:
                        raise TTSProtocolError("讯飞返回了无效音频数据") from exc
                    if len(audio) > self.settings.max_audio_bytes:
                        raise TTSProtocolError("讯飞返回音频超过服务端上限")
                try:
                    status = int(data.get("status", 1))
                except (TypeError, ValueError) as exc:
                    raise TTSProtocolError("讯飞返回了无效完成状态") from exc
                if status not in {1, 2}:
                    raise TTSProtocolError("讯飞返回了未知完成状态")
                if status == 2:
                    finished = True
                    break
            if not finished:
                raise TTSTimeoutError("讯飞语音合成响应超时")
            if not audio:
                raise TTSUpstreamError("讯飞未返回音频")
        except TTSError:
            raise
        except (socket.timeout, TimeoutError) as exc:
            raise TTSTimeoutError("讯飞语音合成响应超时") from exc
        except (OSError, ssl.SSLError) as exc:
            raise TTSUpstreamError("无法连接讯飞语音合成服务") from exc
        finally:
            if ws is not None:
                try:
                    ws.close()
                except Exception:
                    pass
        result = bytes(audio)
        self._cache_put(key, result)
        return SynthesisResult(result, normalized_format, False)

    def synthesize(self, text: Any, **kwargs: Any) -> bytes:
        return self.synthesize_result(text, **kwargs).audio


__all__ = [
    "DEFAULT_ENDPOINT",
    "DEFAULT_FORMAT",
    "DEFAULT_MAX_TEXT_BYTES",
    "DEFAULT_VOICE",
    "IflytekTTSClient",
    "SynthesisResult",
    "TTSConfigurationError",
    "TTSProtocolError",
    "TTSRateLimitError",
    "TTSError",
    "TTSTimeoutError",
    "TTSUpstreamError",
    "TTSValidationError",
    "TTSSettings",
    "SlidingWindowLimiter",
    "build_signed_url",
    "validate_audio_format",
    "validate_parameter",
    "validate_text",
    "validate_voice",
]
