# -*- coding: utf-8 -*-
"""
Ротація ключів Google AI Studio (Gemini): при 429/ліміті перемикаємось на наступний ключ.
Змінні в .env: GOOGLE_AI_KEYS=key1,key2,key3 (через кому) або GOOGLE_AI_KEY_1=, GOOGLE_AI_KEY_2=, ...
"""
import json
import urllib.request
import urllib.error


def get_google_keys_from_env(env_dict):
    """Повертає список ключів з env: GOOGLE_AI_KEYS або GOOGLE_AI_KEY_1, _2, ..."""
    keys = []
    raw = env_dict.get("GOOGLE_AI_KEYS", "").strip()
    if raw:
        keys = [k.strip() for k in raw.split(",") if k.strip()]
    if not keys:
        i = 1
        while True:
            k = env_dict.get(f"GOOGLE_AI_KEY_{i}", "").strip()
            if not k:
                break
            keys.append(k)
            i += 1
    return keys


def call_gemini_one_key(api_key, prompt_text, user_reply="", model="gemini-2.0-flash"):
    """Один виклик Gemini. При 429 кидає ResourceExhausted (для ротації)."""
    content = prompt_text
    if user_reply.strip():
        content = prompt_text + "\n\n--- Відповідь користувача ---\n\n" + user_reply
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
    body = {
        "contents": [{"parts": [{"text": content}]}],
        "generationConfig": {"max_output_tokens": 4096},
    }
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        body_err = e.read().decode() if e.fp else ""
        if e.code == 429:
            raise ResourceExhausted(body_err) from e
        raise RuntimeError(f"Gemini {e.code}: {body_err}") from e
    for c in data.get("candidates", []):
        for p in c.get("content", {}).get("parts", []):
            if "text" in p:
                return p["text"]
    return ""


class ResourceExhausted(Exception):
    """Ліміт по ключу (429). Переходимо на наступний ключ."""
    pass


def call_gemini_rotate(keys, prompt_text, user_reply="", model="gemini-2.0-flash"):
    """
    Викликає Gemini по черзі ключами. При 429 пробує наступний ключ.
    keys — список API-ключів Google AI Studio.
    """
    if not keys:
        raise ValueError("Немає ключів GOOGLE_AI_KEYS у .env")
    last_err = None
    for api_key in keys:
        try:
            return call_gemini_one_key(api_key, prompt_text, user_reply, model)
        except ResourceExhausted as e:
            last_err = e
            continue
    if last_err:
        raise RuntimeError("Усі ключі Google AI вичерпали ліміт (429). Спробуй пізніше.") from last_err
    raise RuntimeError("Не вдалося викликати Gemini.")
