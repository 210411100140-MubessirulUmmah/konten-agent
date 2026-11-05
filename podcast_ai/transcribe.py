"""Transkripsi dengan faster-whisper (jalan lokal di CPU, tanpa Docker, tanpa GPU)."""
from .common import probe


def transcribe(media, model_size="small", language="id"):
    # Import di dalam fungsi supaya modul lain tetap bisa dipakai tanpa faster-whisper.
    from faster_whisper import WhisperModel

    # int8 di CPU = paling hemat RAM. Untuk laptop terbatas pakai model "base" atau "small".
    model = WhisperModel(model_size, device="cpu", compute_type="int8")
    segments, info = model.transcribe(
        str(media),
        language=language,
        word_timestamps=True,
        vad_filter=True,
        condition_on_previous_text=False,
    )
    out = []
    for seg in segments:
        out.append({
            "start": round(seg.start, 3),
            "end": round(seg.end, 3),
            "text": seg.text.strip(),
            "words": [
                {"start": round(w.start, 3), "end": round(w.end, 3), "word": w.word.strip()}
                for w in (seg.words or [])
            ],
        })
        print(f"  [{seg.start:7.1f}s] {seg.text.strip()[:70]}")
    return {
        "language": info.language,
        "duration": probe(media)["duration"],
        "segments": out,
    }


def ensure_words(transcript):
    """Kalau transkrip dari sumber lain tidak punya timestamp per kata, bagi rata per segmen."""
    for seg in transcript["segments"]:
        if seg.get("words"):
            continue
        tokens = seg["text"].split()
        if not tokens:
            seg["words"] = []
            continue
        step = (seg["end"] - seg["start"]) / len(tokens)
        seg["words"] = [
            {"start": round(seg["start"] + i * step, 3),
             "end": round(seg["start"] + (i + 1) * step, 3),
             "word": t}
            for i, t in enumerate(tokens)
        ]
    return transcript
