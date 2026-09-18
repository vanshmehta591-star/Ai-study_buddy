"""
ExplanationService — "Explain like I'm 10" topic explanations via Bob.
"""
from __future__ import annotations

from .bob_client import BobClient


class ExplanationService:
    """Generates simplified explanations for a given topic."""

    def __init__(self, bob_client: BobClient | None = None) -> None:
        self._bob = bob_client or BobClient()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def explain(self, topic_name: str, topic_content: str) -> str:
        """Return an ELI-10 explanation of *topic_content*.

        Parameters
        ----------
        topic_name:
            The display name of the topic (used in the prompt).
        topic_content:
            The raw text of the topic to explain.

        Returns
        -------
        str
            The simplified explanation from the model.

        Raises
        ------
        RuntimeError
            Propagated from BobClient on API failure.
        """
        prompt = self._build_prompt(topic_name, topic_content)
        return self._bob.generate(prompt, max_new_tokens=512)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_prompt(self, topic_name: str, topic_content: str) -> str:
        # Truncate content to keep prompt within model limits (~3000 chars)
        content_snippet = topic_content[:3000].strip()
        return (
            f"You are a friendly tutor explaining concepts to a 10-year-old child.\n"
            f"Explain the following topic in very simple language. "
            f"Avoid jargon. Use analogies and short sentences.\n\n"
            f"Topic: {topic_name}\n\n"
            f"Content:\n{content_snippet}\n\n"
            f"Explanation (write for a 10-year-old):"
        )
