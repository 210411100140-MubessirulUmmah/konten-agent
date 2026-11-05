"""Judul, deskripsi YouTube (lengkap dengan chapter), hashtag, dan caption IG/TikTok."""
import re
from collections import Counter

from .cleanup import remap_time
from .common import fmt_clock
from .llm import ask_json, transcript_as_text

SYSTEM = (
    "Kamu content strategist media bisnis Indonesia (Top Business, ItWorks). "
    "Tulis dalam bahasa Indonesia yang profesional namun mudah dipahami. "
    "Jangan mengarang fakta di luar transkrip. Balas HANYA dengan JSON valid."
)

STOPWORDS = set("""yang dan di ke dari untuk dengan ini itu pada adalah juga karena tidak akan kita kami saya anda
mereka bisa ada sudah lebih sangat seperti atau jadi kalau dalam saat para oleh agar supaya yaitu bahwa
tapi namun jika sama banyak sebagai nya kan lah dong deh sih ya nah terus gitu begitu gimana bagaimana apa
hari mulai kecil pelan selamat datang terima kasih sampai jumpa episode berikutnya menonton mau harus sekarang dulu masih belum bukan hanya semua setiap antara setelah sebelum maka lalu kemudian""".split())


def _keywords(text, n=5):
    words = [w for w in re.findall(r"[a-zA-Z]{4,}", text.lower()) if w not in STOPWORDS]
    return [w for w, _ in Counter(words).most_common(n)]


def _fallback(transcript, clips):
    segs = transcript["segments"]
    full = " ".join(s["text"] for s in segs)
    kw = _keywords(full, 5) or ["podcast"]
    n_ch = min(6, max(2, int(transcript["duration"] // 300) or 2))
    step = len(segs) / n_ch
    chapters = []
    for i in range(n_ch):
        part = segs[int(i * step): max(int(i * step) + 1, int((i + 1) * step))]
        k = _keywords(" ".join(s["text"] for s in part), 2) or kw[:1]
        chapters.append({"start": part[0]["start"] if i else 0, "title": " & ".join(k).title()})
    return {
        "titles": [f"Podcast: Membahas {', '.join(kw[:3]).title()}",
                   f"Obrolan Lengkap Tentang {kw[0].title()}",
                   f"{kw[0].title()} dan {kw[1].title() if len(kw) > 1 else 'Strategi'}: Apa yang Perlu Diketahui?"],
        "description": f"Dalam episode ini kami membahas {', '.join(kw[:4])}. Simak obrolan lengkapnya.",
        "chapters": chapters,
        "hashtags": [f"#{k}" for k in kw[:4]] + ["#podcast", "#bisnis"],
        "instagram_caption": f"Obrolan seru soal {kw[0]}! Tonton versi lengkapnya di YouTube. #podcast #bisnis",
        "tiktok_caption": f"{kw[0].title()} itu penting banget. #podcast #bisnis #fyp",
        "thumbnail_text": " ".join(kw[:3]).upper(),
        "keywords": kw,
        "mode": "heuristik",
    }


def generate_metadata(transcript, clips, keep, use_llm=True, brand="MSI Group"):
    data = None
    if use_llm:
        user = (
            f"Transkrip episode:\n{transcript_as_text(transcript)}\n\n"
            "Buat metadata publikasi. Format JSON:\n"
            '{"titles":["3 opsi judul YouTube, maks 70 karakter, kuat tapi tidak clickbait berlebihan"],'
            '"description":"2-3 paragraf ringkasan untuk deskripsi YouTube",'
            '"chapters":[{"start":detik_di_transkrip,"title":"judul chapter singkat"}] (5-8 chapter, pertama mulai di 0),'
            '"hashtags":["#..." maks 8],'
            '"instagram_caption":"caption untuk postingan IG, maks 3 baris + hashtag",'
            '"tiktok_caption":"caption TikTok singkat + hashtag",'
            '"thumbnail_text":"teks thumbnail maks 5 kata, huruf kapital",'
            '"keywords":["5-8 kata kunci SEO"]}'
        )
        data = ask_json(SYSTEM, user, max_tokens=3500)
        if data:
            data["mode"] = "llm"
    if not data:
        data = _fallback(transcript, clips)

    # Chapter harus mengikuti waktu video bersih (setelah dipotong), bukan video asli.
    chapters = sorted(data.get("chapters", []), key=lambda c: c["start"])
    lines, last = [], -999
    for i, c in enumerate(chapters):
        t = 0.0 if i == 0 else remap_time(float(c["start"]), keep)
        if t - last < 10 and i:  # YouTube minimal 10 detik antar chapter
            continue
        lines.append(f"{fmt_clock(t)} {c['title']}")
        last = t
    data["chapters_text"] = "\n".join(lines)
    tags = " ".join(data.get("hashtags", []))
    data["youtube_description"] = (
        f"{data.get('description', '')}\n\nChapter:\n{data['chapters_text']}\n\n{tags}\n\n{brand}"
    ).strip()
    return data
