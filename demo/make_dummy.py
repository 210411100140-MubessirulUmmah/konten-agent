"""Bikin data DUMMY (video + transkrip) untuk mencoba pipeline tanpa rekaman asli
dan tanpa Whisper. Aman untuk portofolio: tidak ada data perusahaan/klien.

Pakai:  python demo/make_dummy.py
Lalu:   python -m podcast_ai demo/dummy_podcast.mp4 --transcript demo/dummy_transcript.json -o output_demo --no-llm
"""
import json
import subprocess
from pathlib import Path

HERE = Path(__file__).parent

# (kalimat, jeda sesudahnya dalam detik)
SCRIPT = [
    ("Selamat datang di podcast Top Business, hari ini kita bahas transformasi digital.", 1.8),
    ("Eee jadi menurut saya eee tantangan terbesar itu bukan teknologinya.", 0.4),
    ("Ternyata masalah utamanya ada di kebiasaan tim, dan itu penting sekali.", 2.2),
    ("Banyak perusahaan gagal karena strategi yang tidak jelas dari awal.", 1.0),
    ("Kami mulai dari satu proses kecil, yaitu penawaran program kepada klien.", 0.5),
    ("Hasilnya, waktu penyusunan turun dari tiga hari menjadi dua jam, sekitar 90 persen lebih cepat.", 2.6),
    ("Lalu apa pelajaran paling berharga dari proyek ini?", 0.9),
    ("Kuncinya adalah mulai kecil, ukur dampaknya, lalu skalakan pelan-pelan.", 1.5),
    ("Emm risikonya juga harus dipahami, terutama soal keamanan data klien.", 0.6),
    ("Terima kasih sudah menonton, sampai jumpa di episode berikutnya.", 1.0),
]
FILLER = {"eee", "emm"}


def main():
    t, segments, tone_windows = 1.0, [], []
    for sentence, pause in SCRIPT:
        words = sentence.split()
        dur = 0.38 * len(words)
        step = dur / len(words)
        segments.append({
            "start": round(t, 2), "end": round(t + dur, 2), "text": sentence,
            "words": [{"start": round(t + i * step, 2), "end": round(t + (i + 1) * step, 2), "word": w}
                      for i, w in enumerate(words)],
        })
        tone_windows.append((t, t + dur))
        t += dur + pause
    total = round(t + 0.5, 2)

    gate = "+".join(f"between(t,{a:.2f},{b:.2f})" for a, b in tone_windows)
    audio = f"aevalsrc='0.4*sin(2*PI*(180+40*sin(2*PI*0.7*t))*t)*({gate})':s=44100:d={total}"
    video = f"testsrc2=s=1280x720:r=25:d={total}"
    out = HERE / "dummy_podcast.mp4"
    subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
                    "-f", "lavfi", "-i", video, "-f", "lavfi", "-i", audio,
                    "-c:v", "libx264", "-crf", "38", "-preset", "veryfast", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", out], check=True)
    (HERE / "dummy_transcript.json").write_text(
        json.dumps({"language": "id", "duration": total, "segments": segments}, ensure_ascii=False, indent=2),
        encoding="utf-8")
    print(f"Dibuat: {out.name} ({total}s) dan dummy_transcript.json")


if __name__ == "__main__":
    main()
