"""Helper umum: jalankan FFmpeg, probe media, baca/tulis JSON, format waktu."""
import json
import shutil
import subprocess
import sys
from pathlib import Path


def require_ffmpeg():
    for binary in ("ffmpeg", "ffprobe"):
        if shutil.which(binary) is None:
            sys.exit(
                f"'{binary}' tidak ditemukan. Install FFmpeg dulu "
                "(Windows: winget install Gyan.FFmpeg | Mac: brew install ffmpeg | Linux: apt install ffmpeg)."
            )


def run(cmd, cwd=None):
    cmd = [str(c) for c in cmd]
    p = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if p.returncode != 0:
        tail = (p.stderr or "").strip()[-700:]
        print("PERINTAH GAGAL:", " ".join(cmd), "\n", p.stderr[-2000:], file=sys.stderr)
        raise RuntimeError(f"{Path(cmd[0]).name} gagal (kode {p.returncode}): {tail or 'tanpa pesan error'}")
    return p


def probe(media):
    p = run([
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration:stream=codec_type,width,height",
        "-of", "json", media,
    ])
    data = json.loads(p.stdout)
    streams = data.get("streams", [])
    video = next((s for s in streams if s.get("codec_type") == "video"), None)
    return {
        "duration": float(data["format"]["duration"]),
        "has_video": video is not None,
        "has_audio": any(s.get("codec_type") == "audio" for s in streams),
        "width": (video or {}).get("width"),
        "height": (video or {}).get("height"),
    }


def load_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def save_json(obj, path):
    Path(path).write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


def fmt_clock(seconds):
    """83.4 -> '01:23' (atau '1:01:23' kalau lebih dari 1 jam), format chapter YouTube."""
    seconds = int(round(max(0, seconds)))
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


def merge_intervals(intervals, gap=0.0):
    intervals = sorted((a, b) for a, b in intervals if b > a)
    merged = []
    for a, b in intervals:
        if merged and a <= merged[-1][1] + gap:
            merged[-1] = (merged[-1][0], max(merged[-1][1], b))
        else:
            merged.append((a, b))
    return merged


def load_env(path=".env"):
    """Muat file .env sederhana (KEY=VALUE) tanpa paket tambahan. Variabel yang sudah diset di sistem tidak ditimpa."""
    import os

    f = Path(path)
    if not f.exists():
        return
    for line in f.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        value = value.strip().strip('"').strip("'")
        if value and key.strip() not in os.environ:
            os.environ[key.strip()] = value
