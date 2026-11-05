"""Bikin subtitle SRT dari timestamp per kata."""
from pathlib import Path

from .cleanup import in_keep, is_filler, remap_time


def srt_time(t):
    t = max(0.0, t)
    ms = int(round(t * 1000))
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def all_words(transcript):
    return [w for seg in transcript["segments"] for w in seg.get("words", [])]


def make_cues(words, max_words=6, max_dur=2.8, max_gap=0.6):
    """words: list {start,end,word} dengan waktu relatif ke video tujuan."""
    cues, cur = [], []

    def flush():
        if cur:
            cues.append((cur[0]["start"], cur[-1]["end"], " ".join(w["word"] for w in cur)))
            cur.clear()

    for w in words:
        if cur:
            too_long = len(cur) >= max_words or (w["end"] - cur[0]["start"]) > max_dur
            gap = w["start"] - cur[-1]["end"] > max_gap
            if too_long or gap:
                flush()
        cur.append(w)
        if w["word"].rstrip().endswith((".", "?", "!")) and len(cur) >= 2:
            flush()
    flush()
    return cues


def write_srt(cues, path):
    blocks = []
    for i, (a, b, text) in enumerate(cues, 1):
        blocks.append(f"{i}\n{srt_time(a)} --> {srt_time(b)}\n{text}\n")
    Path(path).write_text("\n".join(blocks), encoding="utf-8")


def srt_for_clip(transcript, start, end, path):
    """Subtitle untuk klip [start, end] di video asli. Waktu digeser supaya mulai dari 0."""
    words = []
    for w in all_words(transcript):
        mid = (w["start"] + w["end"]) / 2
        if start <= mid <= end and not is_filler(w["word"]):
            words.append({"word": w["word"],
                          "start": max(0.0, w["start"] - start),
                          "end": min(end - start, w["end"] - start)})
    cues = make_cues(words)
    write_srt(cues, path)
    return len(cues)


def srt_for_clean(transcript, keep, path):
    """Subtitle untuk video bersih: waktu dipetakan ulang, kata di bagian yang dipotong dibuang."""
    words = []
    for w in all_words(transcript):
        mid = (w["start"] + w["end"]) / 2
        if in_keep(mid, keep) and not is_filler(w["word"]):
            words.append({"word": w["word"],
                          "start": remap_time(w["start"], keep),
                          "end": remap_time(w["end"], keep)})
    cues = make_cues(words)
    write_srt(cues, path)
    return len(cues)
