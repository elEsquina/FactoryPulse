from __future__ import annotations

import json
import logging
import re
from typing import Any

logger = logging.getLogger(__name__)


class LLMService:
    """Gemini-backed LLM service with deterministic fallback for offline mode."""

    def __init__(self, api_key: str, model: str, timeout_seconds: int = 45) -> None:
        self._api_key = api_key
        self._model = model
        self._timeout_seconds = timeout_seconds
        self._client = None

        if api_key:
            try:
                from google import genai

                self._client = genai.Client(api_key=api_key)
            except Exception as exc:
                logger.warning("Failed to initialize Gemini client: %s", exc)
                self._client = None

    @property
    def available(self) -> bool:
        return self._client is not None

    def generate(self, prompt: str) -> str:
        if not self._client:
            return self._offline_summary(prompt)

        try:
            response = self._client.models.generate_content(
                model=self._model,
                contents=prompt,
            )
            text = (response.text or "").strip()
            if not text:
                return "No answer was generated."
            return text
        except Exception as exc:
            logger.warning("LLM generation failed, using fallback: %s", exc)
            return self._offline_summary(prompt)

    def generate_json(self, prompt: str) -> dict[str, Any] | None:
        text = self.generate(prompt)
        try:
            cleaned = re.sub(r"```json|```", "", text).strip()
            return json.loads(cleaned)
        except Exception:
            return None

    def _offline_summary(self, prompt: str) -> str:
        # Lightweight fallback so the app still works without API keys.
        snippet = prompt.strip().replace("\n", " ")
        if len(snippet) > 500:
            snippet = snippet[:500] + "..."
        return (
            "LLM offline fallback: A deterministic response was returned because no Gemini API key was available. "
            f"Prompt snippet: {snippet}"
        )
