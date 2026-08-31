#!/usr/bin/env python3
"""Regression and HTTP-contract tests for the server-side iFlytek ASR proxy."""

from __future__ import annotations

import base64
import json
import sys
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit


LOCAL_APP = Path(__file__).resolve().parent
sys.path.insert(0, str(LOCAL_APP))

from iflytek_asr import (  # noqa: E402
    ASRConfigurationError,
    ASRSettings,
    ASRUpstreamError,
    ASRValidationError,
    IflytekASRClient,
    decode_pcm_audio,
)
from iflytek_tts import TTSTimeoutError  # noqa: E402


class FakeWebSocket:
    def __init__(self, _url: str, _timeout: float, _headers=None, frames=None) -> None:
        self.url = _url
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


class IflytekASRUnitTests(unittest.TestCase):
    def make_client(self, frames, **overrides):
        settings = ASRSettings(
            app_id="appid-test",
            api_key="api-key-test",
            api_secret="api-secret-test",
            endpoint=overrides.pop("endpoint", "wss://iat-api.xfyun.cn/v2/iat"),
            frame_interval_seconds=overrides.pop("frame_interval_seconds", 0),
            rate_limit=overrides.pop("rate_limit", 20),
            timeout_seconds=overrides.pop("timeout_seconds", 2),
            **overrides,
        )
        sockets: list[FakeWebSocket] = []

        def factory(url, timeout, headers):
            socket = FakeWebSocket(url, timeout, headers, frames() if callable(frames) else frames)
            sockets.append(socket)
            return socket

        return IflytekASRClient(settings, ws_factory=factory, sleeper=lambda _seconds: None), sockets

    def test_settings_reuse_tts_hmac_credentials_but_never_password(self):
        settings = ASRSettings.from_env(
            {
                "IFLYTEK_TTS_APP_ID": "shared-app",
                "IFLYTEK_TTS_API_KEY": "shared-key",
                "IFLYTEK_TTS_API_SECRET": "shared-secret",
            }
        )
        self.assertTrue(settings.configured)
        self.assertEqual(settings.app_id, "shared-app")
        self.assertEqual(settings.endpoint, "wss://iat-api.xfyun.cn/v2/iat")
        self.assertEqual(settings.max_duration_seconds, 30)

    def test_audio_validation_rejects_bad_base64_sample_rate_and_overlong_input(self):
        settings = ASRSettings(max_audio_bytes=16, max_duration_seconds=30)
        with self.assertRaises(ASRValidationError):
            decode_pcm_audio("not base64!", sample_rate=16000, settings=settings)
        with self.assertRaises(ASRValidationError):
            decode_pcm_audio(base64.b64encode(b"\x00\x00").decode(), sample_rate=8000, settings=settings)
        with self.assertRaises(ASRValidationError):
            decode_pcm_audio(base64.b64encode(b"x" * 17).decode(), sample_rate=16000, settings=settings)

    def test_streaming_request_uses_iat_contract_and_collects_ordered_segments(self):
        frames = [
            json.dumps({"code": 0, "data": {"status": 1, "result": {"sn": 1, "ws": [{"cw": [{"w": "世界"}]}]}}}),
            json.dumps({"code": 0, "data": {"status": 2, "result": {"sn": 0, "ls": True, "ws": [{"cw": [{"w": "你好"}]}]}}}),
        ]
        client, sockets = self.make_client(frames, frame_bytes=4)
        audio = base64.b64encode(b"\x00\x00" * 5).decode()
        result = client.transcribe_result(audio, sample_rate=16000, rate_key="ip-a")
        self.assertEqual(result.text, "你好世界")
        self.assertEqual(result.duration_ms, 0)
        self.assertTrue(sockets[0].closed)
        self.assertNotIn("api-secret-test", sockets[0].sent[0])
        parsed_url = urlsplit(sockets[0].url)
        self.assertEqual(parsed_url.path, "/v2/iat")
        self.assertIn("authorization", parse_qs(parsed_url.query))
        self.assertNotIn("api-secret-test", sockets[0].url)
        first = json.loads(sockets[0].sent[0])
        middle = json.loads(sockets[0].sent[1])
        last = json.loads(sockets[0].sent[-1])
        self.assertEqual(first["common"], {"app_id": "appid-test"})
        self.assertEqual(first["business"], {"language": "zh_cn", "domain": "iat", "accent": "mandarin"})
        self.assertEqual(first["data"]["status"], 0)
        self.assertEqual(first["data"]["format"], "audio/L16;rate=16000")
        self.assertEqual(middle["data"]["status"], 1)
        self.assertEqual(last, {"data": {"status": 2}})

    def test_upstream_error_does_not_echo_upstream_message(self):
        secret = "private-details-must-not-leak"
        client, _ = self.make_client([json.dumps({"code": 11200, "message": secret, "data": {"status": 2}})])
        audio = base64.b64encode(b"\x00\x00").decode()
        with self.assertRaises(ASRUpstreamError) as caught:
            client.transcribe_result(audio, sample_rate=16000)
        self.assertNotIn(secret, str(caught.exception))

    def test_configuration_requires_hmac_triplet(self):
        client = IflytekASRClient(ASRSettings())
        self.assertFalse(client.configured)
        with self.assertRaises(ASRConfigurationError):
            client.transcribe_result(base64.b64encode(b"\x00\x00").decode(), sample_rate=16000)


class IflytekASRHttpTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import server

        cls.server_module = server
        cls.original_client = server.IFLYTEK_ASR
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        cls.thread = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()
        cls.thread.join(timeout=2)
        cls.server_module.IFLYTEK_ASR = cls.original_client

    def setUp(self):
        self.original_client = self.server_module.IFLYTEK_ASR

    def tearDown(self):
        self.server_module.IFLYTEK_ASR = self.original_client

    def request(self, path, payload=None):
        data = None if payload is None else json.dumps(payload, ensure_ascii=False).encode()
        request = urllib.request.Request(
            f"http://127.0.0.1:{self.httpd.server_port}{path}",
            data=data,
            headers={"Content-Type": "application/json"} if data else {},
            method="POST" if data else "GET",
        )
        try:
            with urllib.request.urlopen(request, timeout=5) as response:
                return response.status, dict(response.headers), response.read()
        except urllib.error.HTTPError as exc:
            return exc.code, dict(exc.headers), exc.read()

    def test_status_is_safe_when_asr_is_unconfigured(self):
        self.server_module.IFLYTEK_ASR = IflytekASRClient(ASRSettings())
        status, _headers, body = self.request("/api/asr/status")
        self.assertEqual(status, 503)
        data = json.loads(body)
        self.assertFalse(data["configured"])
        self.assertNotIn("api_key", data)
        self.assertNotIn("api_secret", data)

    def test_asr_endpoint_returns_transcript_and_sanitizes_configuration_error(self):
        frames = [
            json.dumps({"code": 0, "data": {"status": 2, "result": {"sn": 0, "ls": True, "ws": [{"cw": [{"w": "点阵波"}]}]}}})
        ]
        settings = ASRSettings(app_id="appid", api_key="key", api_secret="secret", frame_interval_seconds=0)
        self.server_module.IFLYTEK_ASR = IflytekASRClient(
            settings,
            ws_factory=lambda url, timeout, headers: FakeWebSocket(url, timeout, headers, frames),
            sleeper=lambda _seconds: None,
        )
        audio = base64.b64encode(b"\x00\x00" * 10).decode()
        status, _headers, body = self.request("/api/asr", {"audio_base64": audio, "sample_rate": 16000})
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)["text"], "点阵波")

        self.server_module.IFLYTEK_ASR = IflytekASRClient(ASRSettings())
        status, _headers, body = self.request("/api/asr", {"audio_base64": audio, "sample_rate": 16000})
        self.assertEqual(status, 503)
        self.assertNotIn("secret", body.decode())


if __name__ == "__main__":
    unittest.main(verbosity=2)
