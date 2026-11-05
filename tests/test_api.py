"""Uji API server end-to-end dengan data dummy (Whisper diganti transkrip dummy)."""
import json
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ["DATA_DIR"] = tempfile.mkdtemp()
os.environ["LLM_PROVIDER"] = "none"

from fastapi.testclient import TestClient  # noqa: E402
import server  # noqa: E402
from podcast_ai import pipeline  # noqa: E402

DUMMY = ROOT / "demo" / "dummy_podcast.mp4"
TRANSCRIPT = json.loads((ROOT / "demo" / "dummy_transcript.json").read_text(encoding="utf-8"))


class TestAPI(unittest.TestCase):
    def setUp(self):
        self.c = TestClient(server.app)

    def wait(self, jid):
        for _ in range(120):
            j = self.c.get(f"/api/jobs/{jid}").json()
            if j["status"] in ("done", "error"):
                return j
            time.sleep(1)
        self.fail("timeout")

    def test_upload_flow(self):
        with mock.patch.object(pipeline, "transcribe", return_value=TRANSCRIPT):
            with open(DUMMY, "rb") as f:
                r = self.c.post("/api/jobs", files={"file": ("ep.mp4", f, "video/mp4")}, data={"clips": "2"})
            self.assertEqual(r.status_code, 200)
            jid = r.json()["id"]
            job = self.wait(jid)
        self.assertEqual(job["status"], "done", job["message"])
        res = job["result"]
        self.assertTrue(res["clips"] and res["titles"] and res["thumbnail"])
        self.assertEqual(self.c.get(f"/api/jobs/{jid}/files/{res['clean_video']}").status_code, 200)
        self.assertEqual(self.c.get(f"/api/jobs/{jid}/files/thumbnail.jpg").status_code, 200)
        self.assertEqual(self.c.get(f"/api/jobs/{jid}/zip").status_code, 200)
        self.assertEqual(self.c.get(f"/api/jobs/{jid}/files/../../server.py").status_code, 404)  # path traversal

    def test_validation(self):
        self.assertEqual(self.c.post("/api/jobs", data={}).status_code, 400)                       # kosong
        self.assertEqual(self.c.post("/api/jobs", data={"url": "https://evil.com/x"}).status_code, 400)
        r = self.c.post("/api/jobs", files={"file": ("a.exe", b"x", "application/octet-stream")})
        self.assertEqual(r.status_code, 400)
        self.assertEqual(self.c.get("/api/jobs/nope").status_code, 404)

    def test_health_and_pna_header(self):
        r = self.c.get("/api/health")
        self.assertTrue(r.json()["ok"])
        self.assertEqual(r.headers["access-control-allow-private-network"], "true")


if __name__ == "__main__":
    unittest.main()
