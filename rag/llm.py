"""
Minimal LLM client. No extra packages: plain HTTPS through urllib.

Configure in .env (copy .env.example; .env is git-ignored):
    LLM_PROVIDER=gemini            # gemini | openai_compatible
    LLM_API_KEY=...
    LLM_MODEL=gemini-3.8-flash
    LLM_BASE_URL=                  # only for openai_compatible (Groq, DeepSeek, ...), e.g. https://api.groq.com/openai/v1

What it gives the rest of the code
  - get_config()      -> Config, or None when no key/model is set (the app then falls back to template answers)
  - generate_json()   -> the model's reply text, asked to be JSON. Retries on rate limits (429) / 5xx,
                         and caches replies on disk (.llm_cache/) so re-running the eval costs no free quota.
  - Everything network-related goes through `transport`, so tests can fake it without internet.
"""
import hashlib
import json
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CACHE_DIR = ROOT / ".llm_cache"
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"


class LLMError(Exception):
    """Anything that stops us getting an answer from the model. Never contains the API key."""


@dataclass
class Config:
    provider: str
    api_key: str
    model: str
    base_url: str = ""


def load_env(path=None):
    """Read KEY=VALUE lines from .env into os.environ (existing environment variables win)."""
    path = Path(path) if path else ROOT / ".env"
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k, v = k.strip(), v.strip().strip('"').strip("'")
        if k and v and k not in os.environ:
            os.environ[k] = v


def get_config():
    """Config from .env / environment, or None if the LLM is not set up."""
    load_env()
    provider = os.environ.get("LLM_PROVIDER", "gemini").strip().lower()
    key = os.environ.get("LLM_API_KEY", "").strip()
    model = os.environ.get("LLM_MODEL", "").strip()
    base = os.environ.get("LLM_BASE_URL", "").strip().rstrip("/")
    if not key or not model or provider not in ("gemini", "openai_compatible"):
        return None
    if provider == "openai_compatible" and not base:
        return None
    return Config(provider, key, model, base)


def _request_parts(cfg, system, user, temperature):
    """-> (url, headers, body dict) for the chosen provider."""
    if cfg.provider == "gemini":
        return (
            GEMINI_URL.format(model=cfg.model),
            {"Content-Type": "application/json", "x-goog-api-key": cfg.api_key},
            {"system_instruction": {"parts": [{"text": system}]},
             "contents": [{"role": "user", "parts": [{"text": user}]}],
             "generationConfig": {"temperature": temperature, "responseMimeType": "application/json"}},
        )
    return (
        f"{cfg.base_url}/chat/completions",
        {"Content-Type": "application/json", "Authorization": f"Bearer {cfg.api_key}"},
        {"model": cfg.model, "temperature": temperature,
         "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
         "response_format": {"type": "json_object"}},
    )


def _extract_text(cfg, data):
    """Pull the reply text out of the provider's JSON."""
    if cfg.provider == "gemini":
        block = (data.get("promptFeedback") or {}).get("blockReason")
        if block:
            raise LLMError(f"the model blocked the prompt ({block})")
        cands = data.get("candidates") or []
        if not cands:
            raise LLMError("the model returned no candidates")
        parts = (cands[0].get("content") or {}).get("parts") or []
        text = "".join(p.get("text", "") for p in parts if not p.get("thought"))
        if not text:
            raise LLMError(f"empty reply (finishReason={cands[0].get('finishReason')})")
        return text
    try:
        return data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError):
        raise LLMError("unexpected reply format from the provider") from None


def _http_transport(url, headers, body, timeout=60):
    """Real network call. Returns (status_code, response_text)."""
    req = urllib.request.Request(url, data=json.dumps(body).encode("utf-8"), headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", errors="replace")
    except Exception as e:  # noqa: BLE001  (timeouts, DNS, TLS ...)
        raise LLMError(f"could not reach the provider: {type(e).__name__}") from None


_HINTS = {
    400: "bad request - often a wrong model name or an unsupported option",
    401: "the API key was rejected - check LLM_API_KEY in .env",
    403: "the key is not allowed to use this model/region - check the key and model",
    404: "model not found - check LLM_MODEL (copy the exact id from AI Studio)",
    429: "rate limit reached - wait a minute, or use a lighter model (gemini-3.5-flash-lite)",
}


def generate_json(system, user, *, config=None, transport=None, use_cache=True,
                  max_retries=3, temperature=0.0, sleep=time.sleep):
    """Ask the model for a JSON reply and return its text. Raises LLMError on failure."""
    cfg = config or get_config()
    if cfg is None:
        raise LLMError("the LLM is not configured (set LLM_API_KEY and LLM_MODEL in .env)")
    transport = transport or _http_transport

    cache_key = hashlib.sha256(json.dumps([cfg.provider, cfg.model, system, user, temperature],
                                          ensure_ascii=False).encode("utf-8")).hexdigest()
    cache_file = CACHE_DIR / f"{cache_key}.json"
    if use_cache and cache_file.exists():
        return json.loads(cache_file.read_text(encoding="utf-8"))["text"]

    url, headers, body = _request_parts(cfg, system, user, temperature)
    last = ""
    for attempt in range(max_retries):
        status, text = transport(url, headers, body)
        if status == 200:
            try:
                reply = _extract_text(cfg, json.loads(text))
            except json.JSONDecodeError:
                raise LLMError("the provider did not return valid JSON") from None
            if use_cache:
                CACHE_DIR.mkdir(exist_ok=True)
                cache_file.write_text(json.dumps({"model": cfg.model, "text": reply}, ensure_ascii=False),
                                      encoding="utf-8")
            return reply
        last = f"HTTP {status}: {_HINTS.get(status, 'provider error')}"
        if status in (429, 500, 502, 503, 504) and attempt < max_retries - 1:
            sleep(4 * (attempt + 1))
            continue
        break
    raise LLMError(last)
