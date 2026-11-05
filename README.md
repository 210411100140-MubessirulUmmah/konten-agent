# Podcast AI Studio

Website untuk mengubah **rekaman podcast** (unggah file atau link YouTube) menjadi video bersih
(tanpa jeda panjang dan "eee"), klip vertikal 9:16 bersubtitle, judul, deskripsi YouTube dengan chapter,
caption Instagram/TikTok, dan thumbnail.

## Arsitektur (100% gratis)

```
Browser  --->  web/index.html  (statis; bisa di Vercel atau dibuka dari server lokal)
   |
   v  fetch /api/...
server.py  (FastAPI, jalan di laptop)  --->  podcast_ai/ (faster-whisper + FFmpeg + LLM opsional)
```

Kenapa server tidak di Vercel? Vercel membatasi request (sekitar 4,5 MB), waktu fungsi pendek, dan tidak
punya FFmpeg/Whisper. Jadi Vercel hanya menyajikan tampilan; pemrosesan berat jalan di laptop sendiri.
Dokumentasi Hugging Face saat ini juga menyebut Space bertipe Docker memerlukan paket berbayar,
jadi tidak dipakai di sini.

## Jalankan di laptop

1. Install Python 3.10+ dan FFmpeg (Windows: `winget install Gyan.FFmpeg`).
2. ```
   python -m venv .venv
   .venv\Scripts\activate           # Mac/Linux: source .venv/bin/activate
   pip install -r requirements.txt
   ```
3. (Opsional) salin `.env.example` jadi `.env` untuk LLM gratis (Gemini atau Ollama), lihat `README` bagian "Pilihan LLM" di bawah.
4. ```
   uvicorn server:app --port 8000
   ```
5. Buka **http://localhost:8000**. Server ini menyajikan website sekaligus API-nya.

Pengaturan opsional (variabel lingkungan): `WHISPER_MODEL` (default `small`; pakai `base` kalau laptop berat),
`MAX_MINUTES` (default 60), `MAX_UPLOAD_MB` (default 2000), `CORS_ORIGINS` (default `*`).

## Pasang tampilan di GitHub + Vercel (untuk portofolio)

1. Push seluruh folder ini ke GitHub (`.env` dan folder `jobs/` sudah ada di `.gitignore`).
2. Di vercel.com: **Add New > Project**, pilih repo, atur **Root Directory = `web`**, Framework Preset = Other, lalu Deploy. Tidak ada build step.
3. Buka situs Vercel-nya. Halaman otomatis mencari server di `http://localhost:8000`. Jalankan server di laptop (langkah di atas) lalu muat ulang; badge di kanan atas akan berubah jadi "Server terhubung". Alamat server bisa diganti lewat tombol **Pengaturan**.

Catatan: Chrome bisa menampilkan izin "akses ke perangkat lokal" saat situs Vercel memanggil `localhost`; pilih Izinkan.
Safari memblokir panggilan HTTPS ke HTTP lokal; pakai Chrome atau Firefox, atau buka langsung `http://localhost:8000`.
Pengunjung portofolio tidak bisa memproses video karena servernya di laptopmu, jadi sertakan video rekaman layar demo di README GitHub.

## Pilihan LLM (opsional, gratis)

| Penyedia | Cara aktifkan |
|---|---|
| Gemini (free tier) | key dari aistudio.google.com, isi di kolom web atau `GEMINI_API_KEY` di `.env` |
| Ollama (lokal) | install Ollama, `ollama pull qwen2.5:3b`, biarkan berjalan |
| Tanpa LLM | tidak perlu apa-apa; highlight dan judul dibuat heuristik |

Free tier Gemini boleh dipakai Google untuk memperbaiki produknya: jangan kirim materi rahasia/belum tayang.

## Coba tanpa rekaman asli

```
python demo/make_dummy.py
```
lalu unggah `demo/dummy_podcast.mp4` lewat website. (Tanpa Whisper asli, jalankan CLI dengan
`python -m podcast_ai demo/dummy_podcast.mp4 --transcript demo/dummy_transcript.json -o output_demo --no-llm`.)

## CLI

Mesinnya tetap bisa dipakai tanpa website: `python -m podcast_ai episode.mp4 -o hasil` (opsi lengkap: `--help`).

## Tes

```
python -m unittest discover tests
```

## Batasan

- Satu video diproses sekali waktu; yang lain antre. Hasil dihapus otomatis setelah 6 jam.
- Unduh YouTube memakai yt-dlp: bisa gagal untuk video tertentu atau karena perubahan di YouTube. Gunakan hanya untuk konten milik sendiri/berizin.
- Crop vertikal di tengah (belum face tracking), belum ada pembeda pembicara dan upload otomatis ke platform.
