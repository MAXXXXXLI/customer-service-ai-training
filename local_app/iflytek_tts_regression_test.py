#!/usr/bin/env python3
"""Regression and contract tests for the server-side iFlytek TTS integration."""

from __future__ import annotations

import base64
import hashlib
import json
import sys
import threading
import unittest
import urllib.error
import urllib.request
from unittest.mock import patch
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit


LOCAL_APP = Path(__file__).resolve().parent
sys.path.insert(0, str(LOCAL_APP))

from iflytek_tts import (  # noqa: E402
    IflytekTTSClient,
    TTSConfigurationError,
    TTSRateLimitError,
    TTSSettings,
    TTSUpstreamError,
    TTSValidationError,
    TTSTimeoutError,
    build_signed_url,
)


class FakeWebSocket:
    def __init__(self, _url: str, _timeout: float, headers=None, frames=None) -> None:
        self.headers = dict(headers or {})
        self.frames = list(frames or [])
        self.sent: list[str] = []
        self.closed = False

    def send_text(self, value: str) -> None:
        self.sent.append(value)

    def recv_text(self) -> str:
        if not self.frames:
            raise TTSTimeoutError("fake timeout")
        frame = self.frames.pop(0)
        if isinstance(frame, BaseException):
            raise frame
        return frame

    def close(self) -> None:
        self.closed = True


class IflytekTTSUnitTests(unittest.TestCase):
    def make_client(self, frames, **overrides):
        settings = TTSSettings(
            app_id="appid-test",
            api_key="api-key-test",
            api_secret="api-secret-test",
            api_password=overrides.pop("api_password", ""),
            endpoint=overrides.pop("endpoint", "wss://tts-api.xfyun.cn/v2/tts"),
            cache_ttl_seconds=overrides.pop("cache_ttl_seconds", 300),
            cache_size=overrides.pop("cache_size", 8),
            rate_limit=overrides.pop("rate_limit", 30),
            rate_window_seconds=overrides.pop("rate_window_seconds", 60),
            timeout_seconds=overrides.pop("timeout_seconds", 2),
            **overrides,
        )
        sockets: list[FakeWebSocket] = []

        def factory(url, timeout, headers):
            socket = FakeWebSocket(url, timeout, headers, frames() if callable(frames) else frames)
            sockets.append(socket)
            return socket

        return IflytekTTSClient(settings, ws_factory=factory), sockets

    def test_signed_url_matches_documented_hmac_contract_without_exposing_secret(self):
        url = build_signed_url(
            "wss://tts-api.xfyun.cn/v2/tts",
            "api-key-test",
            "api-secret-test",
            now=1564624401,
        )
        parsed = urlsplit(url)
        query = parse_qs(parsed.query)
        self.assertEqual(parsed.path, "/v2/tts")
        self.assertEqual(query["host"], ["tts-api.xfyun.cn"])
        self.assertEqual(query["date"], ["Thu, 01 Aug 2019 01:53:21 GMT"])
        authorization = base64.b64decode(query["authorization"][0]).decode("utf-8")
        self.assertIn('api_key="api-key-test"', authorization)
        self.assertIn('algorithm="hmac-sha256"', authorization)
        self.assertIn('headers="host date request-line"', authorization)
        self.assertNotIn("api-secret-test", url)
        self.assertNotIn("api-secret-test", authorization)

    def test_password_auth_uses_header_and_streams_audio_until_status_two(self):
        frames = [
            json.dumps({"code": 0, "data": {"audio": base64.b64encode(b"ID3").decode(), "status": 1}}),
            json.dumps({"code": 0, "data": {"audio": base64.b64encode(b"END").decode(), "status": 2}}),
        ]
        client, sockets = self.make_client(frames, api_password="password-test")
        result = client.synthesize_result("  你好，欢迎来到秀域。  ", voice="x4_xiaoyan", speed=42)
        self.assertEqual(result.audio, b"ID3END")
        self.assertFalse(result.cache_hit)
        self.assertEqual(sockets[0].headers, {"X-Api-Key": "password-test"})
        request = json.loads(sockets[0].sent[0])
        self.assertEqual(request["common"], {"app_id": "appid-test"})
        self.assertEqual(request["business"]["aue"], "lame")
        self.assertEqual(request["business"]["sfl"], 1)
        self.assertEqual(request["business"]["speed"], 42)
        self.assertEqual(request["data"]["status"], 2)
        self.assertEqual(
            base64.b64decode(request["data"]["text"]).decode("utf-8"),
            "你好，欢迎来到秀域。",
        )
        self.assertTrue(sockets[0].closed)

    def test_pcm_request_and_cache_do_not_call_upstream_twice(self):
        frames = [
            json.dumps({"code": 0, "data": {"audio": base64.b64encode(b"PCM").decode(), "status": 2}})
        ]
        client, sockets = self.make_client(frames, api_password="password-test")
        first = client.synthesize_result("同一句", audio_format="pcm")
        second = client.synthesize_result("同一句", audio_format="pcm")
        self.assertEqual(first.audio, b"PCM")
        self.assertFalse(first.cache_hit)
        self.assertTrue(second.cache_hit)
        self.assertEqual(second.audio, b"PCM")
        self.assertEqual(len(sockets), 1)
        request = json.loads(sockets[0].sent[0])
        self.assertEqual(request["business"]["aue"], "raw")
        self.assertEqual(request["business"]["auf"], "audio/L16;rate=16000")
        self.assertNotIn("sfl", request["business"])

    def test_validation_rejects_empty_oversized_and_invalid_parameters(self):
        client, _ = self.make_client([], api_password="password-test")
        with self.assertRaises(TTSValidationError):
            client.synthesize("")
        with self.assertRaises(TTSValidationError):
            client.synthesize("x" * 8000)
        with self.assertRaises(TTSValidationError):
            client.synthesize("ok", speed=True)
        with self.assertRaises(TTSValidationError):
            client.synthesize("ok", volume=101)
        with self.assertRaises(TTSValidationError):
            client.synthesize("ok", audio_format="wav")
        with self.assertRaises(TTSValidationError):
            client.synthesize("ok\x00bad")

    def test_upstream_error_and_timeout_are_sanitized(self):
        secret = "password-that-must-never-leak"
        error_frames = [json.dumps({"code": 11200, "message": secret, "data": {"status": 2}})]
        client, _ = self.make_client(error_frames, api_password=secret)
        with self.assertRaises(TTSUpstreamError) as caught:
            client.synthesize("hello")
        self.assertNotIn(secret, str(caught.exception))

        timeout_client, _ = self.make_client([TTSTimeoutError("upstream details")], api_password=secret)
        with self.assertRaises(TTSTimeoutError):
            timeout_client.synthesize("hello")

    def test_rate_limit_is_per_key_and_cache_hits_do_not_consume_quota(self):
        frames = [
            json.dumps({"code": 0, "data": {"audio": base64.b64encode(b"A").decode(), "status": 2}})
        ]
        client, sockets = self.make_client(frames, api_password="password-test", rate_limit=1)
        client.synthesize_result("cached", rate_key="ip-a")
        client.synthesize_result("cached", rate_key="ip-a")
        with self.assertRaises(TTSRateLimitError):
            client.synthesize_result("different", rate_key="ip-a")
        self.assertEqual(len(sockets), 1)
        client.synthesize_result("different", rate_key="ip-b")
        self.assertEqual(len(sockets), 2)

    def test_configuration_requires_a_complete_auth_mode(self):
        client, _ = self.make_client([], api_password="")
        client.settings = TTSSettings()
        self.assertFalse(client.configured)
        with self.assertRaises(TTSConfigurationError):
            client.synthesize("hello")

        with self.assertRaises(TTSConfigurationError):
            TTSSettings.from_env({"IFLYTEK_TTS_ENDPOINT": "https://example.test/tts"})

    def test_stdlib_websocket_validates_handshake_and_preserves_coalesced_first_frame(self):
        import iflytek_tts

        class Socket:
            def __init__(self):
                self.sent = []
                self.chunks = []
                self.closed = False

            def settimeout(self, _value):
                return

            def sendall(self, value):
                self.sent.append(value)
                if len(self.sent) == 1:
                    request = value.decode("ascii")
                    key = next(
                        line.split(":", 1)[1].strip()
                        for line in request.split("\r\n")
                        if line.lower().startswith("sec-websocket-key:")
                    )
                    accept = base64.b64encode(
                        hashlib.sha1(
                            (key + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11").encode("ascii")
                        ).digest()
                    ).decode("ascii")
                    frame = b'\x81\x0b{"ok":true}'
                    self.chunks.append(
                        (
                            "HTTP/1.1 101 Switching Protocols\r\n"
                            "Upgrade: websocket\r\n"
                            "Connection: Upgrade\r\n"
                            f"Sec-WebSocket-Accept: {accept}\r\n\r\n"
                        ).encode("ascii")
                        + frame
                    )

            def recv(self, size):
                if not self.chunks:
                    return b""
                chunk = self.chunks[0][:size]
                self.chunks[0] = self.chunks[0][size:]
                if not self.chunks[0]:
                    self.chunks.pop(0)
                return chunk

            def shutdown(self, _how):
                return

            def close(self):
                self.closed = True

        fake_socket = Socket()
        with patch.object(iflytek_tts.socket, "create_connection", return_value=fake_socket):
            ws = iflytek_tts._StdlibWebSocket("ws://127.0.0.1/v2/tts", 1, {"X-Api-Key": "test"})
            self.assertEqual(ws.recv_text(), '{"ok":true}')
            ws.close()
        self.assertTrue(fake_socket.closed)


class IflytekTTSHttpTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import server

        cls.server_module = server
        cls.original_client = server.IFLYTEK_TTS
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        cls.thread = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()
        cls.thread.join(timeout=2)
        cls.server_module.IFLYTEK_TTS = cls.original_client

    def setUp(self):
        self.original_client = self.server_module.IFLYTEK_TTS

    def tearDown(self):
        self.server_module.IFLYTEK_TTS = self.original_client

    def url(self, path):
        return f"http://127.0.0.1:{self.httpd.server_port}{path}"

    def request(self, path, payload=None):
        data = None if payload is None else json.dumps(payload, ensure_ascii=False).encode()
        request = urllib.request.Request(
            self.url(path),
            data=data,
            headers={"Content-Type": "application/json"} if data is not None else {},
            method="POST" if data is not None else "GET",
        )
        try:
            with urllib.request.urlopen(request, timeout=5) as response:
                return response.status, dict(response.headers), response.read()
        except urllib.error.HTTPError as exc:
            return exc.code, dict(exc.headers), exc.read()

    def test_status_is_structured_and_never_returns_credentials(self):
        self.server_module.IFLYTEK_TTS = IflytekTTSClient(TTSSettings())
        status, _headers, body = self.request("/api/tts/status")
        self.assertEqual(status, 503)
        data = json.loads(body)
        self.assertFalse(data["configured"])
        self.assertNotIn("api_key", data)
        self.assertNotIn("api_secret", data)
        self.assertNotIn("api_password", data)

    def test_tts_returns_audio_and_uses_binary_contract(self):
        frames = [
            json.dumps({"code": 0, "data": {"audio": base64.b64encode(b"audio").decode(), "status": 2}})
        ]
        settings = TTSSettings(
            app_id="appid-test",
            api_key="key-test",
            api_secret="secret-test",
            api_password="password-test",
            rate_limit=10,
        )
        self.server_module.IFLYTEK_TTS = IflytekTTSClient(
            settings,
            ws_factory=lambda url, timeout, headers: FakeWebSocket(url, timeout, headers, frames),
        )
        status, headers, body = self.request("/api/tts", {"text": "你好"})
        self.assertEqual(status, 200)
        self.assertEqual(body, b"audio")
        self.assertEqual(headers["Content-Type"], "audio/mpeg")
        self.assertEqual(headers["X-TTS-Provider"], "iflytek")
        self.assertEqual(headers["X-TTS-Format"], "mp3")
        self.assertEqual(headers["X-TTS-Cache"], "miss")

    def test_tts_errors_are_json_and_do_not_leak_upstream_details(self):
        self.server_module.IFLYTEK_TTS = IflytekTTSClient(TTSSettings())
        status, headers, body = self.request("/api/tts", {"text": "hello"})
        self.assertEqual(status, 503)
        self.assertIn("application/json", headers["Content-Type"])
        self.assertEqual(json.loads(body)["ok"], False)
        self.assertNotIn("secret", body.decode())

        frames = [json.dumps({"code": 11200, "message": "secret-api-key", "data": {"status": 2}})]
        settings = TTSSettings(app_id="appid-test", api_password="password-test")
        self.server_module.IFLYTEK_TTS = IflytekTTSClient(
            settings,
            ws_factory=lambda url, timeout, headers: FakeWebSocket(url, timeout, headers, frames),
        )
        status, _headers, body = self.request("/api/tts", {"text": "hello"})
        self.assertEqual(status, 502)
        self.assertNotIn("secret-api-key", body.decode())

        status, _headers, body = self.request("/api/tts", {"text": "x" * 8000})
        self.assertEqual(status, 400)
        self.assertIn("text", json.loads(body)["error"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
