"""Orkestrasi seluruh alur: transkrip -> bersihkan -> highlight -> klip -> metadata -> thumbnail."""
from pathlib import Path

from . import cleanup
from .clips import render_clip
from .common import fmt_clock, load_json, probe, require_ffmpeg, save_json
from .highlights import pick_highlights
from .llm import llm_available, provider_label
from .metadata import generate_metadata
from .subtitles import srt_for_clean
from .thumbnail import make_thumbnail
from .transcribe import ensure_words, transcribe


_HOOK = None  # callback progres opsional (dipakai server web)


def step(msg):
    print(f"\n==> {msg}")
    if _HOOK:
        _HOOK(msg)


def run_pipeline(args, hook=None):
    global _HOOK
    _HOOK = hook
    require_ffmpeg()
    media = Path(args.input).resolve()
    out = Path(args.out).resolve()
    (out / "clips").mkdir(parents=True, exist_ok=True)
    info = probe(media)
    duration = info["duration"]
    use_llm = llm_available() and not args.no_llm
    print(f"Input : {media.name} ({fmt_clock(duration)}, video={info['has_video']})")
    print(f"Mode  : {('LLM: ' + provider_label()) if use_llm else 'heuristik (tanpa LLM)'}")

    # 1. Transkripsi
    step("1/6 Transkripsi")
    t_path = out / "transcript.json"
    if args.transcript:
        transcript = ensure_words(load_json(args.transcript))
        print(f"  pakai transkrip yang diberikan: {args.transcript}")
    elif t_path.exists() and not args.force:
        transcript = ensure_words(load_json(t_path))
        print("  pakai transkrip hasil run sebelumnya (--force untuk ulang)")
    else:
        transcript = transcribe(media, args.model, args.language)
    transcript.setdefault("duration", duration)
    save_json(transcript, t_path)

    # 2. Cleanup
    step("2/6 Potong jeda dan kata pengisi")
    silences = cleanup.detect_silences(media, args.silence_db, args.min_silence, duration)
    fillers = cleanup.find_filler_intervals(transcript)
    keep = cleanup.build_keep(duration, silences, fillers) if not args.skip_clean else [(0.0, duration)]
    clean_len = sum(b - a for a, b in keep)
    print(f"  jeda panjang: {len(silences)} | kata pengisi: {len(fillers)} | "
          f"{fmt_clock(duration)} -> {fmt_clock(clean_len)} (hemat {duration - clean_len:.1f} dtk)")
    if not args.skip_clean:
        ext = ".mp4" if info["has_video"] else ".m4a"
        cleanup.render_cleaned(media, keep, out / f"episode_clean{ext}", info["has_video"], out)
        n = srt_for_clean(transcript, keep, out / "episode_clean.srt")
        print(f"  video bersih + {n} baris subtitle tersimpan")

    # 3. Highlight
    step("3/6 Pilih momen menarik")
    clips = pick_highlights(transcript, args.clips, use_llm)
    for i, c in enumerate(clips, 1):
        print(f"  #{i} {fmt_clock(c['start'])}-{fmt_clock(c['end'])}  {c['title']}")

    # 4. Klip vertikal
    step("4/6 Render klip vertikal 9:16")
    if info["has_video"] and not args.skip_clips:
        for i, c in enumerate(clips, 1):
            path = render_clip(media, transcript, c, out / "clips", i, args.font)
            c["file"] = f"clips/{path.name}"
            print(f"  {path.name}")
    else:
        print("  dilewati")

    # 5. Metadata
    step("5/6 Judul, deskripsi, chapter, caption")
    meta = generate_metadata(transcript, clips, keep, use_llm)
    meta["clips"] = clips
    save_json(meta, out / "metadata.json")
    (out / "metadata.md").write_text(render_markdown(meta), encoding="utf-8")

    # 6. Thumbnail
    step("6/6 Thumbnail")
    if info["has_video"]:
        at = clips[0]["start"] + 2 if clips else duration * 0.1
        make_thumbnail(media, min(at, duration - 1), meta.get("thumbnail_text", ""), out / "thumbnail.jpg", out)
        print("  thumbnail.jpg")

    report = {
        "durasi_asli_detik": round(duration, 1),
        "durasi_bersih_detik": round(clean_len, 1),
        "jeda_dipotong": len(silences),
        "kata_pengisi_dipotong": len(fillers),
        "jumlah_klip": len(clips),
        "mode_metadata": meta.get("mode"),
    }
    save_json(report, out / "report.json")
    print(f"\nSelesai. Semua hasil ada di: {out}")
    return {"report": report, "metadata": meta}


def render_markdown(meta):
    lines = ["# Hasil Pipeline Podcast", "", "## Opsi judul YouTube"]
    lines += [f"{i}. {t}" for i, t in enumerate(meta["titles"], 1)]
    lines += ["", "## Deskripsi YouTube", "", meta["youtube_description"], "",
              "## Caption", "", f"**Instagram:** {meta['instagram_caption']}", "",
              f"**TikTok:** {meta['tiktok_caption']}", "", "## Klip pendek"]
    for i, c in enumerate(meta.get("clips", []), 1):
        lines += [f"### Klip {i}: {c['title']}",
                  f"- Waktu (video asli): {fmt_clock(c['start'])} - {fmt_clock(c['end'])}",
                  f"- Hook: {c['hook']}", f"- Alasan: {c['reason']}",
                  f"- Caption: {c['caption']}", f"- File: {c.get('file', '-')}", ""]
    return "\n".join(lines)
