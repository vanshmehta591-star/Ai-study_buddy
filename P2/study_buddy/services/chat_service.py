"""
ChatService — doubt-solving chat grounded in uploaded document content.
"""
from __future__ import annotations

from .bob_client import BobClient

# Number of most-relevant topic snippets to include in context
TOP_K_TOPICS = 3
# Max characters per topic snippet sent to the model
SNIPPET_LENGTH = 1500


class ChatValidationError(ValueError):
    """Raised for empty or invalid chat queries."""


class ChatService:
    """Answers user questions grounded in the document's topic content."""

    def __init__(self, bob_client: BobClient | None = None) -> None:
        self._bob = bob_client or BobClient()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def answer(
        self,
        query: str,
        topics: list[dict[str, str]],
        chat_history: list[dict[str, str]] | None = None,
    ) -> str:
        """Answer *query* using relevant excerpts from *topics*.

        Parameters
        ----------
        query:
            The student's question. Must be non-empty.
        topics:
            List of topic dicts with ``name`` and ``content`` keys.
        chat_history:
            Optional list of prior turns: ``[{"role": "user"|"assistant", "content": "..."}]``.

        Returns
        -------
        str
            The model's answer. Contains a clear disclaimer when the
            answer cannot be found in the provided material.

        Raises
        ------
        ChatValidationError
            If *query* is empty or whitespace-only.
        """
        if not query or not query.strip():
            raise ChatValidationError("Please enter a question before submitting.")

        relevant_snippets = self._retrieve_relevant(query, topics)
        prompt = self._build_prompt(query, relevant_snippets, chat_history or [])
        return self._bob.generate(prompt, max_new_tokens=600)

    # ------------------------------------------------------------------
    # Retrieval (simple keyword overlap)
    # ------------------------------------------------------------------

    def _retrieve_relevant(
        self, query: str, topics: list[dict[str, str]]
    ) -> list[dict[str, str]]:
        """Return the TOP_K most query-relevant topic snippets."""
        if not topics:
            return []

        query_words = set(query.lower().split())

        def score(topic: dict[str, str]) -> int:
            text = (topic.get("name", "") + " " + topic.get("content", "")).lower()
            return sum(1 for w in query_words if w in text)

        ranked = sorted(topics, key=score, reverse=True)
        return ranked[:TOP_K_TOPICS]

    # ------------------------------------------------------------------
    # Prompt
    # ------------------------------------------------------------------

    def _build_prompt(
        self,
        query: str,
        snippets: list[dict[str, str]],
        history: list[dict[str, str]],
    ) -> str:
        context_parts: list[str] = []
        for s in snippets:
            name = s.get("name", "Topic")
            content = s.get("content", "")[:SNIPPET_LENGTH]
            context_parts.append(f"[{name}]\n{content}")
        context = "\n\n---\n\n".join(context_parts) if context_parts else "(no document content available)"

        history_text = ""
        if history:
            lines = []
            for turn in history[-6:]:  # last 3 exchanges
                role = "Student" if turn.get("role") == "user" else "Tutor"
                lines.append(f"{role}: {turn.get('content', '')}")
            history_text = "\n".join(lines) + "\n\n"

        return (
            f"You are a helpful study tutor. Answer the student's question using ONLY "
            f"the document excerpts provided below. "
            f"If the answer is not present in the excerpts, say clearly: "
            f"'I could not find information about this in the uploaded material.'\n\n"
            f"Document Excerpts:\n{context}\n\n"
            f"{history_text}"
            f"Student: {query.strip()}\n"
            f"Tutor:"
        )
