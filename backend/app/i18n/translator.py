"""Auto-translation via Gemini Flash (OpenAI-compatible API).

Synchronous (httpx.Client) because Celery tasks run in sync workers.
"""

from __future__ import annotations

import json
import logging
import time

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = (
    "You are a professional translator. Translate the JSON object values from {src_lang} to {tgt_lang}. "
    "Keep all JSON keys unchanged. Return ONLY valid JSON, no markdown fences or extra text. "
    "Preserve placeholders like {{count}}, {{name}}, etc. exactly as-is."
)


def translate_batch(
    strings: dict[str, str],
    source_lang: str,
    target_lang: str,
    max_retries: int = 3,
) -> dict[str, str]:
    """Translate a batch of key→value strings. Returns translated dict.

    Raises on total failure after retries.
    """
    if not strings:
        return {}

    api_key = settings.gemini_api_key
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY not set — cannot auto-translate")

    base_url = settings.openai_base_url
    model = settings.auto_translate_model
    payload = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": _SYSTEM_PROMPT.format(src_lang=source_lang, tgt_lang=target_lang),
            },
            {
                "role": "user",
                "content": json.dumps(strings, ensure_ascii=False),
            },
        ],
        "temperature": 0.1,
        "max_tokens": 16000,
    }

    last_error: Exception | None = None
    for attempt in range(1, max_retries + 1):
        try:
            with httpx.Client(timeout=120) as client:
                resp = client.post(
                    f"{base_url}/chat/completions",
                    json=payload,
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                    },
                )

            if resp.status_code == 429:
                wait = min(2 ** attempt * 5, 60)
                logger.warning("Rate limited, retrying in %ds (attempt %d/%d)", wait, attempt, max_retries)
                time.sleep(wait)
                continue

            resp.raise_for_status()
            data = resp.json()
            content = data["choices"][0]["message"]["content"]

            content = content.strip()
            if content.startswith("```"):
                content = content.split("\n", 1)[1] if "\n" in content else content[3:]
                if content.endswith("```"):
                    content = content[:-3]
                content = content.strip()

            result = json.loads(content)

            if not isinstance(result, dict):
                raise ValueError(f"Expected dict, got {type(result).__name__}")
            if len(result) != len(strings):
                logger.warning(
                    "Translation count mismatch: expected %d, got %d",
                    len(strings), len(result),
                )

            return result

        except (httpx.HTTPStatusError, json.JSONDecodeError, KeyError, ValueError) as e:
            last_error = e
            wait = min(2 ** attempt * 2, 30)
            logger.warning(
                "Translation attempt %d/%d failed: %s — retrying in %ds",
                attempt, max_retries, str(e), wait,
            )
            time.sleep(wait)

    raise RuntimeError(f"Translation failed after {max_retries} attempts: {last_error}")
