"""Lapisan LLM yang bisa ganti-ganti penyedia. Hanya file ini yang menyentuh LLM.

Penyedia (pilih lewat LLM_PROVIDER, default "auto"):
  gemini    -> Google Gemini API, ada free tier (butuh GEMINI_API_KEY dari aistudio.google.com)
  ollama    -> model lokal gratis & offline (install Ollama, `ollama pull qwen2.5:3b`)
  anthropic -> Claude API (berbayar, butuh ANTHROPIC_API_KEY)
  none      -> tanpa LLM, pipeline pakai mode heuristik

"auto" memilih: anthropic (kalau ada key) -> gemini (kalau ada key) -> ollama (kalau jalan) -> none.
Semua panggilan memakai urllib bawaan Python, jadi tidak perlu paket tambahan.
"""
import json
import os
import re
import time
import urllib.error
import urllib.request

DEFAULT_MODELS = {
    "gemini": "gemini-flash-latest",  # alias; cek nama model terbaru di aistudio.google.com
    "ollama": "qwen2.5:3b",           # ringan untuk laptop terbatas; cek pilihan lain di ollama.com/library
    "anthropic": "claude-sonnet-5-5",
}
# Batas karakter transkrip yang dikirim. Model lokal kecil punya konteks pendek.
TEXT_LIMITS = {"gemini": 300_000, "anthropic": 150_000, "ollama": 14_000}


def _ollama_host():
    return os.getenv("OLLAMA_HOST", "http://localhost:11434").rstrip("/")


def _ollama_running():
    try:
        with urllib.request.urlopen(_ollama_host() + "/api/tags", timeout=1.5):
            return True
    except Exception:
        return False


def get_provider():
    choice = os.getenv("LLM_PROVIDER", "auto").lower()
    if choice != "auto":
        return None if choice == "none" else choice
    if os.getenv("ANTHROPIC_API_KEY"):
        return "anthropic"
    if os.getenv("GEMINI_API_KEY"):
        return "gemini"
    if _ollama_running():
        return "ollama"
    return None


def llm_available():
    return get_provider() is not None


def provider_label():
    p = get_provider()
    return f"{p} / {os.getenv('LLM_MODEL', DEFAULT_MODELS[p])}" if p else "tanpa LLM"


def extract_json(text):
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip(), flags=re.MULTILINE)
    starts = [i for i in (text.find("{"), text.find("[")) if i != -1]
    if not starts:
        raise ValueError("Tidak ada JSON di respons")
    start = min(starts)
    end = max(text.rfind("}"), text.rfind("]"))
    return json.loads(text[start:end + 1])


def _post(url, payload, headers=None, timeout=300, retries=2):
    data = json.dumps(payload).encode("utf-8")
    h = {"Content-Type": "application/json", **(headers or {})}
    for attempt in range(retries + 1):
        try:
            req = urllib.request.Request(url, data=data, headers=h, method="POST")
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code in (429, 503) and attempt < retries:  # kena batas kuota free tier: tunggu lalu coba lagi
                time.sleep(8 * (attempt + 1))
                continue
            raise RuntimeError(f"HTTP {e.code}: {e.read().decode('utf-8', 'ignore')[:300]}")


def _call_gemini(system, user, max_tokens, model):
    base = os.getenv("GEMINI_BASE_URL", "https://generativelanguage.googleapis.com/v1beta").rstrip("/")
    out = _post(
        f"{base}/models/{model}:generateContent",
        {
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": user}]}],
            "generationConfig": {"responseMimeType": "application/json", "maxOutputTokens": max_tokens},
        },
        headers={"x-goog-api-key": os.environ["GEMINI_API_KEY"]},
    )
    parts = out["candidates"][0]["content"]["parts"]
    return "".join(p.get("text", "") for p in parts)


def _call_ollama(system, user, max_tokens, model):
    out = _post(
        _ollama_host() + "/api/chat",
        {
            "model": model,
            "stream": False,
            "format": "json",
            "options": {"num_ctx": 8192, "temperature": 0.4, "num_predict": max_tokens},
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        },
        timeout=900,  # CPU laptop bisa lambat
        retries=0,
    )
    return out["message"]["content"]


def _call_anthropic(system, user, max_tokens, model):
    import anthropic  # opsional: pip install anthropic

    resp = anthropic.Anthropic().messages.create(
        model=model, max_tokens=max_tokens, system=system, messages=[{"role": "user", "content": user}]
    )
    return "".join(b.text for b in resp.content if getattr(b, "type", "") == "text")


CALLERS = {"gemini": _call_gemini, "ollama": _call_ollama, "anthropic": _call_anthropic}


def ask_json(system, user, max_tokens=3000):
    provider = get_provider()
    if not provider:
        return None
    model = os.getenv("LLM_MODEL", DEFAULT_MODELS[provider])
    try:
        return extract_json(CALLERS[provider](system, user, max_tokens, model))
    except Exception as e:  # jaringan, kuota, JSON rusak, paket belum ada: jangan matikan pipeline
        print(f"  [!] Panggilan LLM ({provider}) gagal: {type(e).__name__}: {e}. Pakai mode heuristik.")
        return None


def transcript_as_text(transcript, limit=None):
    """Transkrip ber-timestamp. Kalau kepanjangan, baris diambil merata di seluruh episode
    (bukan dipotong di akhir) supaya seluruh episode tetap terwakili."""
    limit = limit or TEXT_LIMITS.get(get_provider() or "", 150_000)
    lines = [f"[{s['start']:.1f}-{s['end']:.1f}] {s['text']}" for s in transcript["segments"]]
    text = "\n".join(lines)
    if len(text) <= limit:
        return text
    keep_ratio = limit / len(text)
    step = max(2, round(1 / keep_ratio))
    picked = [l for i, l in enumerate(lines) if i % step == 0]
    print(f"  [!] Transkrip panjang: dikirim ke LLM merata tiap {step} segmen (muat di konteks model).")
    return "\n".join(picked)[:limit]
