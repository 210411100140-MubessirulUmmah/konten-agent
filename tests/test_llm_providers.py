"""Uji penyedia LLM gratis (Gemini, Ollama) memakai server palsu lokal: tanpa internet, tanpa key asli."""
import json
import os
import sys
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from podcast_ai import llm  # noqa: E402

SEEN = {}


class Fake(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):  # Ollama health check
        self.send_response(200); self.end_headers(); self.wfile.write(b'{"models":[]}')

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        SEEN["path"], SEEN["body"], SEEN["key"] = self.path, body, self.headers.get("x-goog-api-key")
        if "generateContent" in self.path:   # format Gemini
            out = {"candidates": [{"content": {"parts": [{"text": '```json\n{"ok": "gemini"}\n```'}]}}]}
        else:                                 # format Ollama
            out = {"message": {"content": '{"ok": "ollama"}'}}
        raw = json.dumps(out).encode()
        self.send_response(200); self.send_header("Content-Type", "application/json"); self.end_headers()
        self.wfile.write(raw)


class TestProviders(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.srv = HTTPServer(("127.0.0.1", 0), Fake)
        cls.url = f"http://127.0.0.1:{cls.srv.server_port}"
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()

    def test_gemini(self):
        env = {"GEMINI_API_KEY": "kunci-palsu", "GEMINI_BASE_URL": self.url, "LLM_PROVIDER": "gemini"}
        with mock.patch.dict(os.environ, env, clear=True):
            self.assertEqual(llm.ask_json("sistem", "user"), {"ok": "gemini"})
        self.assertIn("generateContent", SEEN["path"])
        self.assertEqual(SEEN["key"], "kunci-palsu")
        self.assertEqual(SEEN["body"]["generationConfig"]["responseMimeType"], "application/json")

    def test_ollama(self):
        env = {"OLLAMA_HOST": self.url, "LLM_PROVIDER": "ollama"}
        with mock.patch.dict(os.environ, env, clear=True):
            self.assertEqual(llm.ask_json("sistem", "user"), {"ok": "ollama"})
        self.assertEqual(SEEN["body"]["model"], "qwen2.5:3b")
        self.assertFalse(SEEN["body"]["stream"])

    def test_auto_detects_ollama_then_none(self):
        with mock.patch.dict(os.environ, {"OLLAMA_HOST": self.url}, clear=True):
            self.assertEqual(llm.get_provider(), "ollama")
        with mock.patch.dict(os.environ, {"OLLAMA_HOST": "http://127.0.0.1:9"}, clear=True):
            self.assertIsNone(llm.get_provider())

    def test_auto_prefers_keys(self):
        with mock.patch.dict(os.environ, {"GEMINI_API_KEY": "x"}, clear=True):
            self.assertEqual(llm.get_provider(), "gemini")

    def test_failure_returns_none_not_crash(self):
        env = {"GEMINI_API_KEY": "x", "GEMINI_BASE_URL": "http://127.0.0.1:9", "LLM_PROVIDER": "gemini"}
        with mock.patch.dict(os.environ, env, clear=True):
            self.assertIsNone(llm.ask_json("s", "u"))

    def test_long_transcript_sampled_evenly(self):
        segs = [{"start": i, "end": i + 1, "text": "kata " * 20} for i in range(500)]
        text = llm.transcript_as_text({"segments": segs}, limit=3000)
        self.assertLessEqual(len(text), 3000)
        self.assertIn("[0.0-1.0]", text)
        last_start = float(text.splitlines()[-1].split("-")[0][1:])
        self.assertGreater(last_start, 300)  # akhir episode tetap terwakili


class TestEnvLoader(unittest.TestCase):
    def test_load_env(self):
        import tempfile
        from podcast_ai.common import load_env
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / ".env"
            f.write_text('# komentar\nGEMINI_API_KEY="abc123"\nKOSONG=\n', encoding="utf-8")
            with mock.patch.dict(os.environ, {}, clear=True):
                load_env(f)
                self.assertEqual(os.environ["GEMINI_API_KEY"], "abc123")
                self.assertNotIn("KOSONG", os.environ)


if __name__ == "__main__":
    unittest.main()
