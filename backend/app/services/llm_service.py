"""
Pluggable LLM client for material summary + milestone quiz generation.

Default: local Ollama (llama3.2). Configure via LLM_BASE_URL / LLM_MODEL.
"""
from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional


class LLMUnavailableError(Exception):
    """Raised when the LLM endpoint cannot be reached or returns an error."""


class LLMService:
    def __init__(
        self,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        timeout: float = 90.0,
    ):
        self.base_url = (base_url or os.environ.get("LLM_BASE_URL", "http://localhost:11434")).rstrip("/")
        self.model = model or os.environ.get("LLM_MODEL", "llama3.1:latest")
        self.timeout = timeout

    def generate_material_pack(
        self,
        description: str,
        title: Optional[str] = None,
        num_questions: int = 3,
    ) -> Dict[str, Any]:
        description = (description or "").strip()
        if not description:
            raise ValueError("description is required")

        prompt = self._build_prompt(description, title, num_questions)
        raw = self._chat(prompt)
        return self._parse_pack(raw, num_questions)

    def _build_prompt(self, description: str, title: Optional[str], num_questions: int) -> str:
        title_line = f'Title: "{title}"\n' if title else ""
        return (
            "You are an education assistant. Given study material notes from a teacher, "
            "produce a concise student-facing summary and multiple-choice checkpoint questions.\n"
            "Respond with ONLY valid JSON (no markdown fences) in this shape:\n"
            "{\n"
            '  "summary": "2-4 sentence summary for students",\n'
            '  "milestones": [\n'
            "    {\n"
            '      "question": "...",\n'
            '      "options": ["A", "B", "C", "D"],\n'
            '      "correct_option": 0,\n'
            '      "hint": "optional short hint"\n'
            "    }\n"
            "  ]\n"
            "}\n"
            f"Create exactly {num_questions} milestones. correct_option is a 0-based index.\n"
            f"{title_line}"
            f"Teacher description:\n{description}\n"
        )

    def _chat(self, prompt: str) -> str:
        url = f"{self.base_url}/api/chat"
        body = json.dumps(
            {
                "model": self.model,
                "stream": False,
                "format": "json",
                "messages": [
                    {"role": "user", "content": prompt},
                ],
            }
        ).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", errors="replace")[:300]
            raise LLMUnavailableError(f"LLM HTTP {e.code}: {detail}") from e
        except urllib.error.URLError as e:
            raise LLMUnavailableError(
                f"LLM unreachable at {self.base_url}. Is Ollama running? ({e.reason})"
            ) from e
        except TimeoutError as e:
            raise LLMUnavailableError("LLM request timed out") from e

        message = (payload.get("message") or {}).get("content") or payload.get("response") or ""
        if not str(message).strip():
            raise LLMUnavailableError("LLM returned an empty response")
        return str(message)

    def _parse_pack(self, raw: str, num_questions: int) -> Dict[str, Any]:
        text = raw.strip()
        # Strip accidental markdown fences
        fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
        if fence:
            text = fence.group(1).strip()
        try:
            data = json.loads(text)
        except json.JSONDecodeError as e:
            raise LLMUnavailableError(f"LLM returned non-JSON content: {e}") from e

        summary = str(data.get("summary") or "").strip()
        milestones_in = data.get("milestones") or []
        if not isinstance(milestones_in, list):
            milestones_in = []

        milestones: List[Dict[str, Any]] = []
        for i, item in enumerate(milestones_in[: max(1, num_questions)]):
            if not isinstance(item, dict):
                continue
            options = item.get("options") or []
            if not isinstance(options, list):
                options = []
            options = [str(o).strip() for o in options if str(o).strip()]
            while len(options) < 2:
                options.append(f"Option {len(options) + 1}")
            options = options[:4]
            try:
                correct = int(item.get("correct_option", 0))
            except (TypeError, ValueError):
                correct = 0
            correct = max(0, min(correct, len(options) - 1))
            question = str(item.get("question") or "").strip()
            if not question:
                continue
            milestones.append(
                {
                    "question": question,
                    "options": options,
                    "correct_option": correct,
                    "hint_text": str(item.get("hint") or item.get("hint_text") or "").strip() or None,
                    "sequence_order": i + 1,
                }
            )

        if not summary:
            summary = "Summary unavailable — please edit before saving."
        if not milestones:
            milestones = [
                {
                    "question": "What is the main idea of this material?",
                    "options": [
                        "The core concept explained in the notes",
                        "An unrelated topic",
                        "A homework deadline",
                        "None of the above",
                    ],
                    "correct_option": 0,
                    "hint_text": "Skim the summary for the key idea.",
                    "sequence_order": 1,
                }
            ]

        return {"summary": summary, "milestones": milestones}
