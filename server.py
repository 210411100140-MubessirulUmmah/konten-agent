"""Server web lokal untuk Podcast AI Studio.
Jalankan:  uvicorn server:app --port 8000   lalu buka http://localhost:8000
Satu job diproses sekali waktu (laptop terbatas); job lain antre."""
import os
import re
import shutil
import threading
import time
import uuid
from pathlib import Path
from types import SimpleNamespace

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from podcast_ai import pipeline
from podcast_ai.common import load_env, probe
from podcast_ai.llm import provider_label

load_env()
ROOT = Path(os.getenv("DATA_DIR", "jobs")).resolve()
ROOT.mkdir(parents=True, exist_ok=True)
MAX_MB = int(os.getenv("MAX_UPLOAD_MB", "2000"))
MAX_MIN = int(os.getenv("MAX_MINUTES", "60"))
MODEL = os.getenv("WHISPER_MODEL", "small")
FONT = os.getenv("FONT", "Arial" if os.name == "nt" or os.uname().sysname == "Darwin" else "DejaVu Sans")
TTL = 6 * 3600
EXTS = {".mp4", ".mov", ".mkv", ".webm", ".mp3", ".wav", ".m4a", ".aac", ".ogg"}
YT = re.compile(r"^https?://(www\.|m\.)?(youtube\.com|youtu\.be)/", re.I)
JOBS, GATE = {}, threading.Semaphore(1)

app = FastAPI(title="Podcast AI Studio")
app.add_middleware(CORSMiddleware, allow_origins=os.getenv("CORS_ORIGINS", "*").split(","),
                   allow_methods=["*"], allow_headers=["*"])


@app.middleware("http")
async def private_network(request: Request, call_next):
    # Chrome meminta izin ini saat situs publik (Vercel) memanggil server di localhost.
    resp = await call_next(request)
    resp.headers["Access-Control-Allow-Private-Network"] = "true"
    return resp


def purge():
    for jid, j in list(JOBS.items()):
        if j["status"] in ("done", "error") and time.time() - j["created"] > TTL:
            shutil.rmtree(ROOT / jid, ignore_errors=True)
            JOBS.pop(jid, None)


def download_youtube(url, dest):
    import yt_dlp
    opts = {"outtmpl": str(dest / "input.%(ext)s"), "noplaylist": True, "quiet": True,
            "format": "bv*[height<=720]+ba/b[height<=720]/b", "merge_output_format": "mp4",
            "max_filesize": MAX_MB * 1024 * 1024,
            "match_filter": yt_dlp.utils.match_filter_func(f"duration <= {MAX_MIN * 60}")}
    with yt_dlp.YoutubeDL(opts) as y:
        y.download([url])
    files = list(dest.glob("input.*"))
    if not files:
        raise RuntimeError("Video tidak terunduh (mungkin melebihi batas durasi/ukuran, atau YouTube menolak).")
    return files[0]


def run_job(jid, media, opts):
    job, out = JOBS[jid], ROOT / jid / "out"
    with GATE:
        job["status"] = "running"
        backup = os.environ.get("GEMINI_API_KEY")
        try:
            if opts["key"]:
                os.environ["GEMINI_API_KEY"] = opts["key"]  # hanya selama job ini, tidak disimpan
            if media is None:
                job["message"] = "Mengunduh video dari YouTube..."
                media = download_youtube(opts["url"], ROOT / jid)
            info = probe(media)
            if info["duration"] > MAX_MIN * 60:
                raise RuntimeError(f"Durasi {info['duration'] / 60:.0f} menit melebihi batas {MAX_MIN} menit.")

            def hook(msg):
                m = re.match(r"(\d)/6", msg)
                if m:
                    job["step"], job["progress"] = int(m[1]), (int(m[1]) - 1) / 6
                job["message"] = msg

            args = SimpleNamespace(input=str(media), out=str(out), model=MODEL, language=opts["lang"],
                                   clips=opts["clips"], transcript=None, no_llm=False, skip_clean=False,
                                   skip_clips=False, silence_db=-35, min_silence=0.7, font=FONT, force=True)
            res = pipeline.run_pipeline(args, hook)
            m = res["metadata"]
            job["result"] = {
                "report": res["report"], "mode": m.get("mode"), "titles": m["titles"],
                "youtube_description": m["youtube_description"], "instagram_caption": m["instagram_caption"],
                "tiktok_caption": m["tiktok_caption"], "clips": m.get("clips", []),
                "clean_video": next((f.name for f in out.glob("episode_clean.*") if f.suffix != ".srt"), None),
                "has_srt": (out / "episode_clean.srt").exists(),
                "thumbnail": "thumbnail.jpg" if (out / "thumbnail.jpg").exists() else None,
            }
            job.update(status="done", progress=1.0, message="Selesai")
        except (Exception, SystemExit) as e:
            job.update(status="error", message=str(e)[:900] or type(e).__name__)
        finally:
            if backup is None:
                os.environ.pop("GEMINI_API_KEY", None)
            else:
                os.environ["GEMINI_API_KEY"] = backup


@app.get("/api/health")
def health():
    return {"ok": True, "model": MODEL, "llm": provider_label(), "max_minutes": MAX_MIN}


@app.post("/api/jobs")
async def create_job(file: UploadFile = File(None), url: str = Form(""), clips: int = Form(3),
                     language: str = Form("id"), gemini_key: str = Form("")):
    purge()
    url = url.strip()
    if bool(file and file.filename) == bool(url):
        raise HTTPException(400, "Kirim tepat satu: file video ATAU link YouTube.")
    jid = uuid.uuid4().hex[:12]
    (ROOT / jid).mkdir(parents=True)
    media = None
    if url:
        if not YT.match(url):
            raise HTTPException(400, "Link harus dari youtube.com atau youtu.be.")
    else:
        ext = Path(file.filename).suffix.lower()
        if ext not in EXTS:
            raise HTTPException(400, f"Format {ext or '?'} tidak didukung. Pakai: {', '.join(sorted(EXTS))}")
        media, size = ROOT / jid / f"input{ext}", 0
        with open(media, "wb") as f:
            while chunk := await file.read(1024 * 1024):
                size += len(chunk)
                if size > MAX_MB * 1024 * 1024:
                    f.close(); shutil.rmtree(ROOT / jid, ignore_errors=True)
                    raise HTTPException(413, f"File melebihi {MAX_MB} MB.")
                f.write(chunk)
    JOBS[jid] = {"id": jid, "status": "queued", "step": 0, "progress": 0.0, "message": "Mengantre...",
                 "created": time.time(), "result": None}
    opts = {"url": url, "clips": max(1, min(5, clips)), "lang": language if language in ("id", "en") else "id",
            "key": gemini_key.strip()}
    threading.Thread(target=run_job, args=(jid, media, opts), daemon=True).start()
    return {"id": jid}


@app.get("/api/jobs/{jid}")
def get_job(jid: str):
    job = JOBS.get(jid)
    if not job:
        raise HTTPException(404, "Job tidak ditemukan (mungkin sudah kedaluwarsa).")
    return {k: v for k, v in job.items() if k != "created"}


@app.get("/api/jobs/{jid}/files/{path:path}")
def get_file(jid: str, path: str):
    if jid not in JOBS:
        raise HTTPException(404)
    base = (ROOT / jid / "out").resolve()
    f = (base / path).resolve()
    if base not in f.parents or not f.is_file():
        raise HTTPException(404)
    return FileResponse(f)


@app.get("/api/jobs/{jid}/zip")
def get_zip(jid: str):
    if jid not in JOBS or JOBS[jid]["status"] != "done":
        raise HTTPException(404)
    z = shutil.make_archive(str(ROOT / jid / "hasil"), "zip", ROOT / jid / "out")
    return FileResponse(z, filename="hasil-podcast-ai.zip")


if (Path(__file__).parent / "web").exists():
    app.mount("/", StaticFiles(directory=Path(__file__).parent / "web", html=True), name="web")
