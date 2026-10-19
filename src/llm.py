"""Minimal LLM client (Gemini or Groq) used for merchant classification and the SQL copilot.

Both providers have free tiers; the app works without any key and simply
degrades to rules-based behaviour. Keys are read from environment variables
first, then from Streamlit secrets (``.streamlit/secrets.toml``).

Set ``SPENDLYTICS_DISABLE_LLM=1`` to force offline mode (used by tests so they
never spend API quota).
"""

from __future__ import annotations

import os
from typing import Any

import requests

_TIMEOUT = 40
_GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
_GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"

DEFAULT_GEMINI_MODEL = "gemini-3.5-flash-lite"
DEFAULT_GROQ_MODEL = "openai/gpt-oss-120b"


_SECRET_ERRORS: list[str] = []


def _setting(name: str) -> str | None:
    """Read a setting from the environment, falling back to Streamlit secrets."""
    value = os.getenv(name)
    if value:
        return value.strip()
    try:  # st.secrets only exists inside a Streamlit runtime
        import streamlit as st

        if name in st.secrets:
            return str(st.secrets[name]).strip()
    except Exception as exc:  # noqa: BLE001 - record for diagnostics
        note = f"{type(exc).__name__}: {exc}"
        if note not in _SECRET_ERRORS:
            _SECRET_ERRORS.append(note)
    return None


def secrets_diagnostics() -> str:
    """Describe what the runtime sees of the configuration — never values."""
    parts: list[str] = []
    env_names = ("GEMINI_API_KEY", "GROQ_API_KEY", "GEMINI_MODEL", "GROQ_MODEL")
    envs = [n for n in env_names if os.getenv(n)]
    parts.append("env: " + (", ".join(envs) if envs else "none"))
    try:
        import streamlit as st

        keys = [str(k) for k in st.secrets.keys()]
        parts.append("secret keys: " + (", ".join(keys) if keys else "none"))
        if "GEMINI_API_KEY" in keys:
            value = str(st.secrets["GEMINI_API_KEY"])
            has_newline = "\n" in value or "\r" in value
            parts.append(
                "GEMINI_API_KEY "
                f"len={len(value)} newline={has_newline} "
                f"trimmed={value == value.strip()} prefix_ok={value.startswith('AQ.')}"
            )
    except Exception as exc:  # noqa: BLE001 - this IS the diagnostic path
        parts.append(f"secrets error: {type(exc).__name__}: {exc}")
    if _SECRET_ERRORS:
        parts.append("notes: " + " | ".join(_SECRET_ERRORS[-3:]))
    return " · ".join(parts)


class LLMClient:
    """Thin wrapper that talks to whichever provider has a key configured."""

    def __init__(self) -> None:
        disabled = bool(os.getenv("SPENDLYTICS_DISABLE_LLM"))
        self.gemini_key = None if disabled else _setting("GEMINI_API_KEY")
        self.groq_key = None if disabled else _setting("GROQ_API_KEY")
        self.gemini_model = _setting("GEMINI_MODEL") or DEFAULT_GEMINI_MODEL
        self.groq_model = _setting("GROQ_MODEL") or DEFAULT_GROQ_MODEL
        self.last_error: str | None = None

    # ------------------------------------------------------------- public

    @property
    def provider(self) -> str | None:
        if self.gemini_key:
            return "gemini"
        if self.groq_key:
            return "groq"
        return None

    def available(self) -> bool:
        return self.provider is not None

    def complete(
        self,
        system: str,
        prompt: str,
        *,
        json_mode: bool = False,
        temperature: float = 0.2,
    ) -> str | None:
        """Return the model's text response, or ``None`` when unavailable."""
        if self.provider is None:
            self.last_error = "No API key configured."
            return None
        try:
            if self.provider == "gemini":
                return self._gemini(system, prompt, json_mode, temperature)
            return self._groq(system, prompt, json_mode, temperature)
        except requests.RequestException as exc:
            self.last_error = f"Network error: {exc}"
            return None
        except Exception as exc:  # noqa: BLE001 — an LLM hiccup must never crash the UI
            self.last_error = str(exc)
            return None

    # ------------------------------------------------------------ private

    def _gemini(self, system: str, prompt: str, json_mode: bool, temperature: float) -> str | None:
        generation_config: dict[str, Any] = {"temperature": temperature}
        if json_mode:
            generation_config["responseMimeType"] = "application/json"
        body: dict[str, Any] = {
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": generation_config,
        }
        response = requests.post(
            _GEMINI_URL.format(model=self.gemini_model),
            params={"key": self.gemini_key},
            json=body,
            timeout=_TIMEOUT,
        )
        if response.status_code >= 400:
            self.last_error = _gemini_error(response)
            return None
        data = response.json()
        candidates = data.get("candidates") or []
        if not candidates:
            self.last_error = "Empty response from Gemini."
            return None
        parts = candidates[0].get("content", {}).get("parts", [])
        text = "".join(part.get("text", "") for part in parts)
        return text or None

    def _groq(self, system: str, prompt: str, json_mode: bool, temperature: float) -> str | None:
        body: dict[str, Any] = {
            "model": self.groq_model,
            "temperature": temperature,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
        }
        if json_mode:
            body["response_format"] = {"type": "json_object"}
        response = requests.post(
            _GROQ_URL,
            headers={"Authorization": f"Bearer {self.groq_key}"},
            json=body,
            timeout=_TIMEOUT,
        )
        if response.status_code >= 400:
            self.last_error = _groq_error(response)
            return None
        data = response.json()
        try:
            return data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError):
            self.last_error = "Unexpected response shape from Groq."
            return None


def _gemini_error(response: requests.Response) -> str:
    try:
        message = response.json().get("error", {}).get("message", response.text[:200])
    except Exception:
        message = response.text[:200]
    hint = ""
    if response.status_code == 404:
        hint = " (model not found — set GEMINI_MODEL to a free model from AI Studio)"
    elif response.status_code in (403, 429):
        hint = " (quota or access issue — try another free model, or wait a minute)"
    return f"Gemini API error {response.status_code}: {message}{hint}"


def _groq_error(response: requests.Response) -> str:
    try:
        message = response.json().get("error", {}).get("message", response.text[:200])
    except Exception:
        message = response.text[:200]
    return f"Groq API error {response.status_code}: {message}"
