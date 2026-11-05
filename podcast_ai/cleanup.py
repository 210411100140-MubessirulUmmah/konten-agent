"""Pembersihan: potong jeda panjang dan kata pengisi (eee, emm, ...), lalu render video bersih."""
import re
from pathlib import Path

from .common import merge_intervals, run

FILLERS = {"eee", "ee", "eeh", "eh", "ehm", "em", "emm", "hmm", "mmm", "uh", "uhh", "um", "umm", "aaa", "anu"}


def norm_word(w):
    return re.sub(r"[^\w]", "", w.lower())


def is_filler(word):
    return norm_word(word) in FILLERS


def detect_silences(media, noise_db=-35, min_dur=0.7, duration=None):
    p = run([
        "ffmpeg", "-hide_banner", "-nostats", "-i", media,
        "-af", f"silencedetect=noise={noise_db}dB:d={min_dur}",
        "-f", "null", "-",
    ])
    starts = [max(0.0, float(x)) for x in re.findall(r"silence_start: (-?[\d.]+)", p.stderr)]
    ends = [float(x) for x in re.findall(r"silence_end: ([\d.]+)", p.stderr)]
    if len(starts) > len(ends) and duration:  # hening sampai akhir file
        ends.append(duration)
    return list(zip(starts, ends))


def find_filler_intervals(transcript):
    out = []
    for seg in transcript["segments"]:
        for w in seg.get("words", []):
            if is_filler(w["word"]):
                out.append((w["start"], w["end"]))
    return out


def build_keep(duration, silences, fillers, keep_pause=0.3, margin=0.03, min_keep=0.2):
    """Hasilkan daftar interval yang DIPERTAHANKAN.

    - Jeda panjang tidak dihapus total: disisakan `keep_pause` detik supaya ritme bicara tetap natural.
    - Kata pengisi dihapus penuh (dengan margin kecil).
    """
    remove = []
    for s, e in silences:
        a, b = s + keep_pause / 2, e - keep_pause / 2
        if b - a > 0.05:
            remove.append((a, b))
    for s, e in fillers:
        remove.append((max(0.0, s - margin), min(duration, e + margin)))
    remove = merge_intervals(remove)

    keep, cur = [], 0.0
    for a, b in remove:
        if a - cur >= min_keep:
            keep.append((cur, a))
        cur = max(cur, b)
    if duration - cur >= min_keep:
        keep.append((cur, duration))
    return keep


def remap_time(t, keep):
    """Waktu di video asli -> waktu di video bersih."""
    acc = 0.0
    for a, b in keep:
        if t < a:
            return acc
        if t <= b:
            return acc + (t - a)
        acc += b - a
    return acc


def in_keep(t, keep):
    return any(a <= t <= b for a, b in keep)


def render_cleaned(media, keep, out_path, has_video=True, workdir=None):
    """Potong + gabung semua interval `keep` lewat satu filter_complex_script FFmpeg."""
    lines, labels = [], ""
    for i, (a, b) in enumerate(keep):
        if has_video:
            lines.append(f"[0:v]trim=start={a:.3f}:end={b:.3f},setpts=PTS-STARTPTS[v{i}];")
            labels += f"[v{i}]"
        lines.append(f"[0:a]atrim=start={a:.3f}:end={b:.3f},asetpts=PTS-STARTPTS[a{i}];")
        labels += f"[a{i}]"
    n = len(keep)
    if has_video:
        lines.append(f"{labels}concat=n={n}:v=1:a=1[outv][outa]")
        maps = ["-map", "[outv]", "-map", "[outa]",
                "-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-pix_fmt", "yuv420p"]
    else:
        lines.append(f"{labels}concat=n={n}:v=0:a=1[outa]")
        maps = ["-map", "[outa]"]

    script = Path(workdir or Path(out_path).parent) / "_filter.txt"
    script.write_text("\n".join(lines), encoding="utf-8")
    base = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", media]
    tail = [*maps, "-c:a", "aac", "-b:a", "160k", out_path]
    try:
        # FFmpeg >= 7: "-/filter_complex <file>"; opsi lama -filter_complex_script dihapus di FFmpeg 8.
        try:
            run([*base, "-/filter_complex", script, *tail])
        except RuntimeError as e:
            if "Unrecognized option" not in str(e) and "Option not found" not in str(e):
                raise
            run([*base, "-filter_complex_script", script, *tail])  # FFmpeg lama (< 7)
    finally:
        script.unlink(missing_ok=True)
