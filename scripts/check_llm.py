"""Check the configured LLM provider and, for Gemini, list usable free models.

Usage:
    python scripts/check_llm.py

Reads GEMINI_API_KEY / GROQ_API_KEY from the environment or
.streamlit/secrets.toml, sends one tiny prompt, and prints the result.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import requests  # noqa: E402

from src.llm import LLMClient  # noqa: E402


def list_gemini_models(key: str) -> None:
    response = requests.get(
        "https://generativelanguage.googleapis.com/v1beta/models",
        params={"key": key},
        timeout=30,
    )
    if response.status_code >= 400:
        print(f"  (could not list models: HTTP {response.status_code})")
        return
    names = [
        model["name"].split("/")[-1]
        for model in response.json().get("models", [])
        if "generateContent" in model.get("supportedGenerationMethods", [])
    ]
    print("  Models available to your key that support generateContent:")
    for name in sorted(names)[:30]:
        print(f"    - {name}")


def main() -> None:
    client = LLMClient()
    print(f"Provider: {client.provider or 'NONE (no API key found)'}")
    if client.provider == "gemini":
        print(f"Gemini model in use: {client.gemini_model}")
        list_gemini_models(client.gemini_key or "")
    elif client.provider == "groq":
        print(f"Groq model in use: {client.groq_model}")
    else:
        print("Set GEMINI_API_KEY or GROQ_API_KEY in .streamlit/secrets.toml first.")
        raise SystemExit(1)

    print("\nSending a test prompt…")
    answer = client.complete("You reply with a single word.", "Reply with: ready")
    if answer is None:
        print(f"FAILED: {client.last_error}")
        raise SystemExit(2)
    print(f"OK — model replied: {answer.strip()[:80]}")


if __name__ == "__main__":
    main()
