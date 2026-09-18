"""
RevisionService — revision plan generation and persistence.

Persistence: data/revision_plans.json
"""
from __future__ import annotations

import json
import uuid
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from .bob_client import BobClient

DATA_DIR = Path(__file__).parent.parent / "data"
REVISION_PLANS_FILE = DATA_DIR / "revision_plans.json"


class RevisionValidationError(ValueError):
    """Raised for invalid revision plan inputs."""


class RevisionService:
    """Generates day-by-day revision plans and persists them."""

    def __init__(self, bob_client: BobClient | None = None) -> None:
        self._bob = bob_client or BobClient()
        DATA_DIR.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def generate_plan(
        self,
        exam_date: date,
        topics: list[str],
        document_title: str = "",
    ) -> dict[str, Any]:
        """Generate a revision plan up to *exam_date* covering *topics*.

        Parameters
        ----------
        exam_date:
            The date of the exam. Must be strictly in the future.
        topics:
            Non-empty list of topic names to cover.
        document_title:
            Optional title for context (e.g. document filename).

        Returns
        -------
        dict
            Revision plan record with ``id``, ``exam_date``, ``topics``,
            ``plan_text``, and ``created_at``.

        Raises
        ------
        RevisionValidationError
            If *exam_date* is today or in the past, or *topics* is empty.
        """
        self._validate(exam_date, topics)
        prompt = self._build_prompt(exam_date, topics, document_title)
        plan_text = self._bob.generate(prompt, max_new_tokens=1024)
        record = {
            "id": str(uuid.uuid4()),
            "exam_date": exam_date.isoformat(),
            "document_title": document_title,
            "topics": topics,
            "plan_text": plan_text,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        self._save(record)
        return record

    def list_plans(self) -> list[dict[str, Any]]:
        """Return all persisted revision plans."""
        return self._load_all()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _validate(self, exam_date: date, topics: list[str]) -> None:
        today = date.today()
        if exam_date <= today:
            raise RevisionValidationError(
                f"Exam date must be in the future. You entered {exam_date.isoformat()} "
                f"but today is {today.isoformat()}."
            )
        if not topics:
            raise RevisionValidationError("Please select at least one topic for the revision plan.")

    def _build_prompt(
        self, exam_date: date, topics: list[str], document_title: str
    ) -> str:
        today = date.today()
        days_left = (exam_date - today).days
        topic_list = "\n".join(f"- {t}" for t in topics)
        title_line = f"Subject / Document: {document_title}\n" if document_title else ""
        return (
            f"You are a study coach. Create a detailed, day-by-day revision plan.\n\n"
            f"{title_line}"
            f"Exam date: {exam_date.isoformat()} ({days_left} days from today)\n"
            f"Topics to cover:\n{topic_list}\n\n"
            f"Guidelines:\n"
            f"- Spread topics evenly across the available days.\n"
            f"- Keep the last 1-2 days for full review and rest.\n"
            f"- Be specific: mention which topic to study on which day.\n"
            f"- Include short daily study goals (1-2 sentences each).\n\n"
            f"Revision Plan:"
        )

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _load_all(self) -> list[dict[str, Any]]:
        if not REVISION_PLANS_FILE.exists():
            return []
        try:
            with REVISION_PLANS_FILE.open("r", encoding="utf-8") as fh:
                data = json.load(fh)
            return data if isinstance(data, list) else []
        except (json.JSONDecodeError, OSError):
            return []

    def _save(self, record: dict[str, Any]) -> None:
        records = self._load_all()
        records.append(record)
        with REVISION_PLANS_FILE.open("w", encoding="utf-8") as fh:
            json.dump(records, fh, indent=2, ensure_ascii=False)
