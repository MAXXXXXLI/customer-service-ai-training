#!/usr/bin/env python3
"""Contract checks for the server-side WeKnora adapter."""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import threading
import time
import unittest
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


LOCAL_APP = Path(__file__).resolve().parent
ROOT = LOCAL_APP.parent
sys.path.insert(0, str(LOCAL_APP))

from weknora_client import WeKnoraConfig, WeKnoraSearchClient, WeKnoraSearchError  # noqa: E402


class FakeWeKnoraHandler(BaseHTTPRequestHandler):
    requests: list[dict[str, object]] = []
    escape_scope = False
    spoof_faq_metadata = False
    spoof_faq_match_metadata = False
    force_error = False
    unknown_faq = False

    def log_message(self, _format: str, *_args: object) -> None:
        return

    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("Content-Length", "0"))
        payload = json.loads(self.rfile.read(length).decode("utf-8"))
        type(self).requests.append(
            {
                "path": self.path,
                "payload": payload,
                "api_key": self.headers.get("X-API-Key"),
            }
        )
        if type(self).force_error:
            encoded = json.dumps({"success": False, "error": "simulated upstream failure"}).encode("utf-8")
            self.send_response(502)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)
            return
        kb_id = "kb-escaped" if type(self).escape_scope else payload["knowledge_base_ids"][0]
        query = str(payload.get("query") or "")
        faq_mode = "秀域品牌" in query or type(self).unknown_faq
        standard_question = (
            "这是一个本地目录没有登记的常见问题吗？"
            if type(self).unknown_faq
            else "关于秀域品牌、业务板块与员工知识地图，顾客最需要先了解什么？"
        )
        alias_question = "秀域品牌、业务板块与员工知识地图"
        matched_question = alias_question if query == alias_question else standard_question
        chunk_type = "text" if type(self).spoof_faq_metadata else "faq" if faq_mode else "text"
        metadata = (
            {"doc_type": "common_qa", "matched_question": query}
            if type(self).spoof_faq_metadata
            else {
                "document_id": "COURSE-NKB-010",
                "course_id": "COURSE-NKB-010",
                "module_id": "MOD-03",
                "source_id": "NKB-2026-08-HIGH-DENSITY",
            }
            if type(self).unknown_faq
            else {"matched_question": "伪造的恶意问题"}
            if type(self).spoof_faq_match_metadata and faq_mode
            else {}
            if faq_mode
            else {
                "document_id": "COURSE-NKB-010",
                "course_id": "COURSE-NKB-010",
                "module_id": "MOD-03",
            }
        )
        body = {
            "success": True,
            "data": [
                {
                    "id": "chunk-1",
                    "knowledge_id": "knowledge-1",
                    "knowledge_base_id": kb_id,
                    "knowledge_title": "顾客问答" if faq_mode else "点阵波的项目定位、原理框架与知识边界",
                    "content": (
                        f"Q: {standard_question}\nAnswer:\n- 秀域提供经当前资料核验的健康与美丽相关服务，具体动态信息应以当前有效版本为准。"
                        if faq_mode
                        else "服务后不适不能一概解释为正常，应先确认程度、变化和伴随症状。"
                    ),
                    "score": 0.93,
                    "match_type": 1,
                    "chunk_type": chunk_type,
                    # v0.7.2 question_answer + separate indexes the matched
                    # question together with its answer, not a pure question.
                    "matched_content": (
                        f"{matched_question}\n秀域提供经当前资料核验的健康与美丽相关服务，具体动态信息应以当前有效版本为准。"
                        if faq_mode else ""
                    ),
                    "chunk_metadata": {
                        "standard_question": standard_question,
                        "similar_questions": [alias_question],
                        "answers": ["秀域提供经当前资料核验的健康与美丽相关服务，具体动态信息应以当前有效版本为准。"],
                    } if faq_mode else {},
                    "metadata": metadata,
                }
            ],
        }
        encoded = json.dumps(body, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def get_json(url: str) -> dict[str, object]:
    with urllib.request.urlopen(url, timeout=5) as response:
        return json.loads(response.read().decode("utf-8"))


def post_json(url: str, payload: dict[str, object]) -> dict[str, object]:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=10) as response:
        return json.loads(response.read().decode("utf-8"))


class WeKnoraAdapterTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        FakeWeKnoraHandler.requests = []
        FakeWeKnoraHandler.escape_scope = False
        cls.fake_server = ThreadingHTTPServer(("127.0.0.1", 0), FakeWeKnoraHandler)
        cls.fake_port = int(cls.fake_server.server_address[1])
        cls.fake_thread = threading.Thread(target=cls.fake_server.serve_forever, daemon=True)
        cls.fake_thread.start()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.fake_server.shutdown()
        cls.fake_server.server_close()
        cls.fake_thread.join(timeout=2)

    def setUp(self) -> None:
        FakeWeKnoraHandler.requests.clear()
        FakeWeKnoraHandler.escape_scope = False
        FakeWeKnoraHandler.spoof_faq_metadata = False
        FakeWeKnoraHandler.spoof_faq_match_metadata = False
        FakeWeKnoraHandler.force_error = False
        FakeWeKnoraHandler.unknown_faq = False

    def test_client_maps_metadata_and_sends_scoped_key(self) -> None:
        client = WeKnoraSearchClient(
            WeKnoraConfig(
                base_url=f"http://127.0.0.1:{self.fake_port}",
                api_key="retrieve-secret",
                knowledge_base_ids=("kb-staff", "kb-safety"),
            )
        )
        rows = client.search("点阵波是什么", limit=4)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["document_id"], "COURSE-NKB-010")
        self.assertEqual(rows[0]["metadata"]["course_id"], "COURSE-NKB-010")
        self.assertEqual(FakeWeKnoraHandler.requests[0]["path"], "/api/v1/knowledge-search")
        self.assertEqual(FakeWeKnoraHandler.requests[0]["api_key"], "retrieve-secret")
        self.assertEqual(
            FakeWeKnoraHandler.requests[0]["payload"]["knowledge_base_ids"],
            ["kb-staff", "kb-safety"],
        )

    def test_client_rejects_result_outside_allow_list(self) -> None:
        FakeWeKnoraHandler.escape_scope = True
        client = WeKnoraSearchClient(
            WeKnoraConfig(
                base_url=f"http://127.0.0.1:{self.fake_port}",
                api_key="retrieve-secret",
                knowledge_base_ids=("kb-staff",),
            )
        )
        with self.assertRaisesRegex(WeKnoraSearchError, "白名单"):
            client.search("越权测试")

    def test_text_chunk_cannot_disguise_itself_as_faq_metadata(self) -> None:
        FakeWeKnoraHandler.spoof_faq_metadata = True
        client = WeKnoraSearchClient(
            WeKnoraConfig(
                base_url=f"http://127.0.0.1:{self.fake_port}",
                api_key="retrieve-secret",
                knowledge_base_ids=("kb-staff",),
            )
        )
        rows = client.search("秀域品牌、业务板块与员工知识地图")
        self.assertEqual(rows[0]["weknora"]["chunk_type"], "text")
        self.assertNotEqual(rows[0]["metadata"]["doc_type"], "common_qa")

    def test_structured_faq_questions_override_spoofed_user_metadata(self) -> None:
        FakeWeKnoraHandler.spoof_faq_match_metadata = True
        client = WeKnoraSearchClient(
            WeKnoraConfig(
                base_url=f"http://127.0.0.1:{self.fake_port}",
                api_key="retrieve-secret",
                knowledge_base_ids=("kb-customer",),
            )
        )
        question = "关于秀域品牌、业务板块与员工知识地图，顾客最需要先了解什么？"
        rows = client.search(question)
        self.assertNotIn("matched_question", rows[0]["metadata"])
        self.assertIn(question, rows[0]["weknora"]["faq_questions"])
        self.assertEqual(rows[0]["weknora"]["faq_answers"], [
            "秀域提供经当前资料核验的健康与美丽相关服务，具体动态信息应以当前有效版本为准。"
        ])

    def test_unknown_faq_cannot_forge_local_course_citation(self) -> None:
        FakeWeKnoraHandler.unknown_faq = True
        client = WeKnoraSearchClient(
            WeKnoraConfig(
                base_url=f"http://127.0.0.1:{self.fake_port}",
                api_key="retrieve-secret",
                knowledge_base_ids=("kb-customer",),
            )
        )
        rows = client.search("这是一个本地目录没有登记的常见问题吗？")
        self.assertNotIn("course_id", rows[0]["metadata"])
        self.assertNotIn("module_id", rows[0]["metadata"])
        self.assertNotIn("source_id", rows[0]["metadata"])
        self.assertNotEqual(rows[0]["document_id"], "COURSE-NKB-010")

    def test_training_server_uses_weknora_without_local_faq_bypass(self) -> None:
        app_port = free_port()
        env = os.environ.copy()
        env.update(
            {
                "HOST": "127.0.0.1",
                "PORT": str(app_port),
                "SILICONFLOW_MOCK": "1",
                "WEKNORA_BASE_URL": f"http://127.0.0.1:{self.fake_port}",
                "WEKNORA_RETRIEVE_API_KEY": "retrieve-secret",
                "WEKNORA_KB_IDS": "kb-staff,kb-safety",
                "WEKNORA_REQUIRED": "1",
                "PYTHONDONTWRITEBYTECODE": "1",
            }
        )
        process = subprocess.Popen(
            [sys.executable, str(LOCAL_APP / "server.py")],
            cwd=str(ROOT),
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        try:
            deadline = time.time() + 10
            health: dict[str, object] | None = None
            while time.time() < deadline:
                if process.poll() is not None:
                    output = process.stdout.read() if process.stdout else ""
                    self.fail(f"training server exited early: {output}")
                try:
                    health = get_json(f"http://127.0.0.1:{app_port}/api/health")
                    break
                except Exception:
                    time.sleep(0.1)
            self.assertIsNotNone(health)
            assert health is not None
            self.assertEqual(health["knowledge"]["provider"], "weknora")
            response = post_json(
                f"http://127.0.0.1:{app_port}/api/chat",
                {"mode": "qa", "action": "turn", "message": "点阵波打完更痛了？", "history": []},
            )
            self.assertTrue(response["ok"])
            self.assertEqual(response["meta"]["selection"], "deterministic_safety")
            self.assertFalse(response["meta"]["common_qa"])
            self.assertNotIn("微损伤", response["result"]["answer"])
            self.assertIn("我先为您暂停后续安排", response["result"]["answer"])
            self.assertIn("route", response["result"])
            self.assertEqual(response["retrieved"], [])

            price = post_json(
                f"http://127.0.0.1:{app_port}/api/chat",
                {"mode": "qa", "action": "turn", "message": "点阵波多少钱？", "history": []},
            )
            self.assertIn("城市、门店", price["result"]["answer"])
            self.assertIn("route", price["result"])

            faq = post_json(
                f"http://127.0.0.1:{app_port}/api/chat",
                {
                    "mode": "qa",
                    "action": "turn",
                    "message": "关于秀域品牌、业务板块与员工知识地图，顾客最需要先了解什么？",
                    "history": [],
                },
            )
            self.assertTrue(faq["meta"]["common_qa"])
            self.assertEqual(faq["meta"]["selection"], "weknora_exact_faq")
            self.assertEqual(faq["result"]["faq_match"]["id"], "FAQ-NKB-001")
            self.assertNotIn("Q:", faq["result"]["answer"])
            self.assertNotIn("Answer:", faq["result"]["answer"])
            self.assertEqual(faq["retrieved"][0]["course_id"], "COURSE-NKB-001")

            alias = post_json(
                f"http://127.0.0.1:{app_port}/api/chat",
                {"mode": "qa", "action": "turn", "message": "秀域品牌、业务板块与员工知识地图", "history": []},
            )
            self.assertEqual(alias["meta"]["selection"], "weknora_exact_faq")

            prefixed = post_json(
                f"http://127.0.0.1:{app_port}/api/chat",
                {"mode": "qa", "action": "turn", "message": "请问关于秀域品牌、业务板块与员工知识地图，顾客最需要先了解什么？", "history": []},
            )
            self.assertEqual(prefixed["meta"]["selection"], "weknora")
            self.assertFalse(prefixed["meta"]["common_qa"])

            resolved = post_json(
                f"http://127.0.0.1:{app_port}/api/chat",
                {"mode": "qa", "action": "turn", "message": "点阵波做完已经不痛了，正常吗？", "history": []},
            )
            self.assertNotIn("疼痛比原来加重", resolved["result"]["answer"])

            FakeWeKnoraHandler.force_error = True
            safety_during_outage = post_json(
                f"http://127.0.0.1:{app_port}/api/chat",
                {"mode": "qa", "action": "turn", "message": "点阵波打完更痛了？", "history": []},
            )
            self.assertEqual(safety_during_outage["meta"]["selection"], "deterministic_safety")
            self.assertIn("我先为您暂停后续安排", safety_during_outage["result"]["answer"])
            with self.assertRaises(urllib.error.HTTPError) as failed_retrieval:
                post_json(
                    f"http://127.0.0.1:{app_port}/api/chat",
                    {"mode": "qa", "action": "turn", "message": "点阵波是什么？", "history": []},
                )
            self.assertEqual(failed_retrieval.exception.code, 502)
            FakeWeKnoraHandler.force_error = False
        finally:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=2)
            if process.stdout:
                process.stdout.close()

    def test_required_mode_reports_unhealthy_when_configuration_is_missing(self) -> None:
        app_port = free_port()
        env = os.environ.copy()
        for key in ("WEKNORA_BASE_URL", "WEKNORA_RETRIEVE_API_KEY", "WEKNORA_KB_IDS"):
            env.pop(key, None)
        env.update({
            "HOST": "127.0.0.1",
            "PORT": str(app_port),
            "SILICONFLOW_MOCK": "1",
            "WEKNORA_REQUIRED": "1",
            "PYTHONDONTWRITEBYTECODE": "1",
        })
        process = subprocess.Popen(
            [sys.executable, str(LOCAL_APP / "server.py")],
            cwd=str(ROOT),
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        try:
            deadline = time.time() + 10
            while time.time() < deadline:
                try:
                    get_json(f"http://127.0.0.1:{app_port}/api/health")
                except urllib.error.HTTPError as exc:
                    self.assertEqual(exc.code, 503)
                    payload = json.loads(exc.read().decode("utf-8"))
                    self.assertFalse(payload["ok"])
                    self.assertEqual(payload["knowledge"]["provider"], "unavailable")
                    break
                except urllib.error.URLError:
                    time.sleep(0.1)
            else:
                self.fail("required-mode health endpoint never returned 503")
        finally:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=2)
            if process.stdout:
                process.stdout.close()


if __name__ == "__main__":
    unittest.main(verbosity=2)
