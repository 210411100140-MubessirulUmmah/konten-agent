import argparse

from .common import load_env
from .pipeline import run_pipeline


def main():
    load_env()
    p = argparse.ArgumentParser(
        prog="podcast_ai",
        description="Podcast AI Pipeline: transkrip, potong jeda/eee, klip pendek, subtitle, judul, thumbnail.",
    )
    p.add_argument("input", help="file video/audio podcast (mp4, mov, mkv, mp3, wav, ...)")
    p.add_argument("-o", "--out", default="output", help="folder hasil (default: output)")
    p.add_argument("--model", default="small", help="model Whisper: tiny/base/small/medium (default: small)")
    p.add_argument("--language", default="id", help="kode bahasa audio (default: id)")
    p.add_argument("--clips", type=int, default=3, help="jumlah klip pendek (default: 3)")
    p.add_argument("--transcript", help="pakai transkrip JSON yang sudah ada (lewati Whisper)")
    p.add_argument("--no-llm", action="store_true", help="paksa mode heuristik tanpa LLM apa pun")
    p.add_argument("--skip-clean", action="store_true", help="jangan render video bersih")
    p.add_argument("--skip-clips", action="store_true", help="jangan render klip pendek")
    p.add_argument("--silence-db", type=float, default=-35, help="ambang hening dalam dB (default: -35)")
    p.add_argument("--min-silence", type=float, default=0.7, help="jeda minimal yang dipotong, detik (default: 0.7)")
    p.add_argument("--font", default="Arial", help="font subtitle (default: Arial)")
    p.add_argument("--force", action="store_true", help="ulangi transkripsi walau sudah ada")
    run_pipeline(p.parse_args())
