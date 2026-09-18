"""
Tests for ExplanationService — ELI-10 explanation generation.
All BobClient calls are mocked.
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from services.explanation_service import ExplanationService


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

MOCK_EXPLANATION = (
    "Photosynthesis is like a cooking recipe for plants. "
    "They use sunlight as their oven, water as an ingredient, "
    "and air (CO2) to make their own food (sugar)!"
)


@pytest.fixture
def mock_bob():
    bob = MagicMock()
    bob.generate.return_value = MOCK_EXPLANATION
    return bob


@pytest.fixture
def svc(mock_bob):
    return ExplanationService(bob_client=mock_bob)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestExplanationService:
    def test_returns_bob_output(self, svc):
        result = svc.explain("Photosynthesis", "Photosynthesis is the process by which…")
        assert result == MOCK_EXPLANATION

    def test_bob_generate_called_once(self, svc, mock_bob):
        svc.explain("Topic", "content")
        mock_bob.generate.assert_called_once()

    def test_prompt_contains_topic_name(self, svc, mock_bob):
        svc.explain("Mitosis", "Mitosis is cell division…")
        prompt = mock_bob.generate.call_args[0][0]
        assert "Mitosis" in prompt

    def test_prompt_contains_eli10_instruction(self, svc, mock_bob):
        svc.explain("Topic", "content")
        prompt = mock_bob.generate.call_args[0][0]
        assert "10" in prompt  # "10-year-old" or similar

    def test_prompt_contains_content_snippet(self, svc, mock_bob):
        content = "This is the content to explain."
        svc.explain("Topic", content)
        prompt = mock_bob.generate.call_args[0][0]
        assert "This is the content" in prompt

    def test_long_content_is_truncated_in_prompt(self, svc, mock_bob):
        long_content = "word " * 2000  # ~10000 chars
        svc.explain("Big Topic", long_content)
        prompt = mock_bob.generate.call_args[0][0]
        # The prompt itself should not be enormous
        assert len(prompt) < 5000

    def test_runtime_error_propagated(self, mock_bob):
        mock_bob.generate.side_effect = RuntimeError("API error")
        svc = ExplanationService(bob_client=mock_bob)
        with pytest.raises(RuntimeError, match="API error"):
            svc.explain("Topic", "content")

    def test_max_new_tokens_passed(self, svc, mock_bob):
        svc.explain("Topic", "content")
        call_kwargs = mock_bob.generate.call_args
        # max_new_tokens should be passed as keyword arg
        assert call_kwargs[1].get("max_new_tokens") == 512 or (
            len(call_kwargs[0]) > 1 and call_kwargs[0][1] == 512
        )
