"""Pilih bagian paling menarik untuk dijadikan klip pendek (Reels/TikTok/Shorts)."""
import re
import textwrap

from .llm import ask_json, transcript_as_text

MIN_LEN, MAX_LEN, TARGET_LEN = 20.0, 90.0, 45.0

SYSTEM = (
    "Kamu editor video podcast bisnis berbahasa Indonesia untuk media Top Business dan ItWorks. "
    "Tugasmu memilih momen paling menarik untuk klip pendek vertikal. "
    "Balas HANYA dengan JSON valid, tanpa teks lain."
)

KEYWORDS = [
    "penting", "rahasia", "kunci", "tantangan", "strategi", "ternyata", "masalah", "solusi",
    "gagal", "berhasil", "pelajaran", "peluang", "risiko", "paling", "pertama", "sebenarnya",
    "tips", "kesalahan", "hasilnya", "dampak", "transformasi", "inovasi", "digital",
]


def _snap(segments, start, end):
    """Rapikan batas klip supaya mulai dan berakhir tepat di batas kalimat/segmen."""
    s = min(segments, key=lambda g: abs(g["start"] - start))["start"]
    e = min(segments, key=lambda g: abs(g["end"] - end))["end"]
    if e - s > MAX_LEN:
        cand = [g["end"] for g in segments if s + MIN_LEN <= g["end"] <= s + MAX_LEN]
        e = cand[-1] if cand else s + MAX_LEN
    return s, e


def _valid(clips, segments, duration, n):
    out = []
    for c in clips:
        try:
            s, e = _snap(segments, float(c["start"]), float(c["end"]))
        except (KeyError, TypeError, ValueError):
            continue
        e = min(e, duration)
        if e - s < MIN_LEN:
            continue
        if any(not (e <= o["start"] or s >= o["end"]) for o in out):  # tumpang tindih
            continue
        out.append({
            "start": round(s, 2), "end": round(e, 2),
            "title": str(c.get("title", "")).strip() or "Klip podcast",
            "hook": str(c.get("hook", "")).strip(),
            "reason": str(c.get("reason", "")).strip(),
            "caption": str(c.get("caption", "")).strip(),
        })
    return out[:n]


def _heuristic(segments, duration, n):
    """Mode tanpa LLM: skor jendela ~45 detik berdasarkan kata kunci, angka, pertanyaan, dan kepadatan bicara."""
    cands = []
    for i, first in enumerate(segments):
        j, text = i, ""
        while j < len(segments) and segments[j]["end"] - first["start"] < TARGET_LEN:
            text += " " + segments[j]["text"]
            j += 1
        if j >= len(segments):
            j = len(segments) - 1
            text += " " + segments[j]["text"]
        end = segments[j]["end"]
        length = end - first["start"]
        if length < MIN_LEN or length > MAX_LEN:
            continue
        low = text.lower()
        score = sum(low.count(k) for k in KEYWORDS) * 2
        score += low.count("?") * 2 + len(re.findall(r"\d+", low)) * 0.5
        score += min(len(low.split()) / length, 4)  # kata per detik
        cands.append((score, first["start"], end, text.strip()))
    cands.sort(reverse=True)
    out = []
    for score, s, e, text in cands:
        if any(not (e <= o["start"] or s >= o["end"]) for o in out):
            continue
        first_sentence = textwrap.shorten(re.split(r"(?<=[.?!])\s", text)[0], width=70, placeholder="...")
        out.append({"start": round(s, 2), "end": round(e, 2), "title": first_sentence,
                    "hook": first_sentence, "reason": f"skor heuristik {score:.1f}", "caption": first_sentence})
        if len(out) == n:
            break
    return sorted(out, key=lambda c: c["start"])


def pick_highlights(transcript, n=3, use_llm=True):
    segments = transcript["segments"]
    duration = transcript.get("duration") or segments[-1]["end"]
    if not segments:
        return []
    if use_llm:
        user = (
            f"Transkrip podcast (format [mulai-selesai detik] teks):\n{transcript_as_text(transcript)}\n\n"
            f"Pilih {n} momen terbaik untuk klip {int(MIN_LEN)}-{int(MAX_LEN)} detik. Kriteria: ada hook kuat "
            "di 3 detik pertama, ide utuh (tidak terpotong), emosional/insight/kontroversial, "
            "bisa dipahami tanpa konteks. Waktu mulai dan selesai harus mengikuti batas segmen transkrip, "
            "tidak saling tumpang tindih.\n"
            'Format: {"clips":[{"start":detik,"end":detik,"title":"judul pendek <=60 karakter",'
            '"hook":"kalimat pembuka untuk teks overlay","reason":"kenapa menarik","caption":"caption IG/TikTok + 3 hashtag"}]}'
        )
        data = ask_json(SYSTEM, user)
        if data:
            clips = _valid(data.get("clips", []), segments, duration, n)
            if clips:
                return clips
    return _heuristic(segments, duration, n)
