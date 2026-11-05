"""Tes logika inti tanpa FFmpeg/Whisper/API. Jalankan: python -m unittest discover tests"""
import json
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from podcast_ai import cleanup, highlights, llm, metadata, subtitles  # noqa: E402

TRANSCRIPT = json.loads((Path(__file__).resolve().parents[1] / "demo" / "dummy_transcript.json").read_text(encoding="utf-8")) \
    if (Path(__file__).resolve().parents[1] / "demo" / "dummy_transcript.json").exists() else None


class TestCleanup(unittest.TestCase):
    def test_build_keep_removes_long_pause_but_keeps_rhythm(self):
        keep = cleanup.build_keep(10.0, silences=[(3.0, 5.0)], fillers=[])
        self.assertEqual(len(keep), 2)
        removed = 10.0 - sum(b - a for a, b in keep)
        self.assertAlmostEqual(removed, 2.0 - 0.3, places=2)  # sisakan 0.3 detik jeda

    def test_filler_removed(self):
        keep = cleanup.build_keep(10.0, silences=[], fillers=[(4.0, 4.5)])
        self.assertTrue(all(not (a < 4.2 < b) for a, b in keep))

    def test_remap_time(self):
        keep = [(0.0, 3.0), (5.0, 10.0)]
        self.assertAlmostEqual(cleanup.remap_time(2.0, keep), 2.0)
        self.assertAlmostEqual(cleanup.remap_time(6.0, keep), 4.0)   # 3 + (6-5)
        self.assertAlmostEqual(cleanup.remap_time(4.0, keep), 3.0)   # di area terpotong -> snap

    def test_is_filler(self):
        self.assertTrue(cleanup.is_filler("Eee,"))
        self.assertFalse(cleanup.is_filler("eksekusi"))


class TestSubtitles(unittest.TestCase):
    def test_cues_split_on_sentence_end(self):
        words = [{"word": w, "start": i * 0.3, "end": i * 0.3 + 0.25}
                 for i, w in enumerate(["bukan", "teknologinya.", "Ternyata", "masalahnya", "di", "tim"])]
        cues = subtitles.make_cues(words)
        self.assertEqual(cues[0][2], "bukan teknologinya.")

    def test_srt_time(self):
        self.assertEqual(subtitles.srt_time(3661.5), "01:01:01,500")


class TestHighlights(unittest.TestCase):
    SEGS = [{"start": float(i * 10), "end": float(i * 10 + 9), "text": f"kalimat {i}", "words": []} for i in range(12)]

    def test_llm_clips_snapped_and_overlap_dropped(self):
        fake = {"clips": [
            {"start": 11.3, "end": 52.1, "title": "A"},
            {"start": 30.0, "end": 70.0, "title": "B (tumpang tindih)"},
            {"start": 5.0, "end": 8.0, "title": "C (terlalu pendek)"},
        ]}
        with mock.patch.object(highlights, "ask_json", return_value=fake):
            clips = highlights.pick_highlights({"segments": self.SEGS, "duration": 120.0}, n=3, use_llm=True)
        self.assertEqual(len(clips), 1)
        self.assertEqual(clips[0]["start"], 10.0)  # snap ke awal segmen
        self.assertEqual(clips[0]["end"], 49.0)    # snap ke akhir segmen

    def test_llm_failure_falls_back_to_heuristic(self):
        with mock.patch.object(highlights, "ask_json", return_value=None):
            clips = highlights.pick_highlights({"segments": self.SEGS, "duration": 120.0}, n=2, use_llm=True)
        self.assertTrue(clips)


class TestLLMJson(unittest.TestCase):
    def test_extract_json_from_fenced_text(self):
        self.assertEqual(llm.extract_json('Ini hasilnya:\n```json\n{"a": 1}\n```'), {"a": 1})

    def test_no_key_returns_none(self):
        with mock.patch.dict("os.environ", {"LLM_PROVIDER": "none"}, clear=True):
            self.assertIsNone(llm.ask_json("s", "u"))


class TestMetadata(unittest.TestCase):
    def test_chapters_follow_clean_timeline(self):
        transcript = {"duration": 100.0, "segments": [{"start": 0.0, "end": 50.0, "text": "halo"},
                                                      {"start": 50.0, "end": 100.0, "text": "dunia"}]}
        keep = [(0.0, 20.0), (30.0, 100.0)]  # 10 detik dipotong
        fake = {"titles": ["T"], "description": "D", "hashtags": ["#x"], "instagram_caption": "i",
                "tiktok_caption": "t", "thumbnail_text": "X",
                "chapters": [{"start": 0, "title": "Awal"}, {"start": 60, "title": "Inti"}]}
        with mock.patch.object(metadata, "ask_json", return_value=fake):
            meta = metadata.generate_metadata(transcript, [], keep, use_llm=True)
        self.assertIn("00:50 Inti", meta["chapters_text"])  # 60 -> 50 setelah potongan 10 detik


if __name__ == "__main__":
    unittest.main()
