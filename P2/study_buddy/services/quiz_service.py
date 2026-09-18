"""
QuizService — quiz generation, answer checking, scoring, and persistence.

Persistence: data/quizzes.json, data/attempts.json
"""
from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .bob_client import BobClient

DATA_DIR = Path(__file__).parent.parent / "data"
QUIZZES_FILE = DATA_DIR / "quizzes.json"
ATTEMPTS_FILE = DATA_DIR / "attempts.json"

NUM_QUESTIONS = 5


class QuizService:
    """Generates multiple-choice quizzes, checks answers, and records scores."""

    def __init__(self, bob_client: BobClient | None = None) -> None:
        self._bob = bob_client or BobClient()
        DATA_DIR.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def generate_quiz(self, topic_name: str, topic_content: str) -> dict[str, Any]:
        """Generate a 5-question MCQ quiz for *topic_content*.

        Returns
        -------
        dict
            Quiz record with ``id``, ``topic``, and ``questions``.
            Each question has ``question``, ``options`` (list of 4),
            and ``answer`` (the correct option letter A-D).
        """
        prompt = self._build_prompt(topic_name, topic_content)
        raw = self._bob.generate(prompt, max_new_tokens=1200)
        questions = self._parse_questions(raw)
        record = {
            "id": str(uuid.uuid4()),
            "topic": topic_name,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "questions": questions,
        }
        self._save_quiz(record)
        return record

    def check_answer(self, question: dict[str, Any], user_answer: str) -> bool:
        """Return True if *user_answer* matches the correct answer letter."""
        return user_answer.strip().upper() == question["answer"].strip().upper()

    def save_attempt(
        self,
        quiz_id: str,
        topic: str,
        answers: list[str],
        score: int,
        total: int,
    ) -> dict[str, Any]:
        """Persist a completed quiz attempt and return the record."""
        record = {
            "id": str(uuid.uuid4()),
            "quiz_id": quiz_id,
            "topic": topic,
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "answers": answers,
            "score": score,
            "total": total,
        }
        attempts = self._load_json(ATTEMPTS_FILE)
        attempts.append(record)
        self._write_json(ATTEMPTS_FILE, attempts)
        return record

    def list_attempts(self) -> list[dict[str, Any]]:
        return self._load_json(ATTEMPTS_FILE)

    # ------------------------------------------------------------------
    # Prompt & parsing
    # ------------------------------------------------------------------

    def _build_prompt(self, topic_name: str, topic_content: str) -> str:
        snippet = topic_content[:3000].strip()
        return (
            f"You are a teacher creating a quiz. Based on the content below, "
            f"generate exactly {NUM_QUESTIONS} multiple-choice questions.\n\n"
            f"Format EACH question exactly like this (no extra text between questions):\n"
            f"Q1. <question text>\n"
            f"A) <option>\n"
            f"B) <option>\n"
            f"C) <option>\n"
            f"D) <option>\n"
            f"Answer: <letter>\n\n"
            f"Topic: {topic_name}\n\n"
            f"Content:\n{snippet}\n\n"
            f"Quiz:"
        )

    def _parse_questions(self, raw: str) -> list[dict[str, Any]]:
        """Parse the model output into a list of question dicts."""
        # Split on question markers Q1. Q2. … or numbered lines
        blocks = re.split(r"\n(?=Q\d+[\.\)])", raw.strip())
        questions: list[dict[str, Any]] = []

        for block in blocks:
            q = self._parse_single_question(block.strip())
            if q:
                questions.append(q)
            if len(questions) == NUM_QUESTIONS:
                break

        # If parsing failed to produce enough questions, fill with placeholders
        while len(questions) < NUM_QUESTIONS:
            idx = len(questions) + 1
            questions.append({
                "question": f"Question {idx} (could not be parsed)",
                "options": ["A) –", "B) –", "C) –", "D) –"],
                "answer": "A",
            })

        return questions[:NUM_QUESTIONS]

    def _parse_single_question(self, block: str) -> dict[str, Any] | None:
        lines = [l.strip() for l in block.splitlines() if l.strip()]
        if not lines:
            return None

        # Question text — first line, strip leading "Q1." etc.
        q_text = re.sub(r"^Q\d+[\.\)]\s*", "", lines[0]).strip()
        if not q_text:
            return None

        options: list[str] = []
        answer = "A"
        for line in lines[1:]:
            opt_match = re.match(r"^([A-D])[).]\s*(.+)", line, re.IGNORECASE)
            if opt_match:
                options.append(f"{opt_match.group(1).upper()}) {opt_match.group(2).strip()}")
            ans_match = re.match(r"^Answer:\s*([A-D])", line, re.IGNORECASE)
            if ans_match:
                answer = ans_match.group(1).upper()

        # Need at least 2 options to be a valid question
        if len(options) < 2:
            return None

        # Pad to 4 if needed
        while len(options) < 4:
            options.append(f"{chr(65 + len(options))}) –")

        return {"question": q_text, "options": options[:4], "answer": answer}

    # ------------------------------------------------------------------
    # Persistence helpers
    # ------------------------------------------------------------------

    def _save_quiz(self, record: dict[str, Any]) -> None:
        quizzes = self._load_json(QUIZZES_FILE)
        quizzes.append(record)
        self._write_json(QUIZZES_FILE, quizzes)

    def _load_json(self, path: Path) -> list[dict[str, Any]]:
        if not path.exists():
            return []
        try:
            with path.open("r", encoding="utf-8") as fh:
                data = json.load(fh)
            return data if isinstance(data, list) else []
        except (json.JSONDecodeError, OSError):
            return []

    def _write_json(self, path: Path, data: list[dict[str, Any]]) -> None:
        with path.open("w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2, ensure_ascii=False)
