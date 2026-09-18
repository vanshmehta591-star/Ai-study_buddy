"""
Tests for ChatService — grounded doubt-solving chat.
All BobClient calls are mocked.
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from services.chat_service import ChatService, ChatValidationError


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

MOCK_ANSWER = "Photosynthesis is the process by which plants make food using sunlight."

TOPICS = [
    {"name": "Photosynthesis", "content": "Photosynthesis is a biological process used by plants to convert light energy into chemical energy stored in glucose."},
    {"name": "Cell Structure", "content": "A cell is the basic unit of life. It contains a nucleus, mitochondria, and other organelles."},
    {"name": "Genetics", "content": "Genetics is the study of genes, heredity, and genetic variation in living organisms."},
]


@pytest.fixture
def mock_bob():
    bob = MagicMock()
    bob.generate.return_value = MOCK_ANSWER
    return bob


@pytest.fixture
def svc(mock_bob):
    return ChatService(bob_client=mock_bob)


# ---------------------------------------------------------------------------
# Validation tests
# ---------------------------------------------------------------------------

class TestChatValidation:
    def test_empty_query_raises(self, svc):
        with pytest.raises(ChatValidationError):
            svc.answer("", TOPICS)

    def test_whitespace_only_query_raises(self, svc):
        with pytest.raises(ChatValidationError):
            svc.answer("   ", TOPICS)

    def test_valid_query_passes(self, svc):
        result = svc.answer("What is photosynthesis?", TOPICS)
        assert result == MOCK_ANSWER


# ---------------------------------------------------------------------------
# Generation tests
# ---------------------------------------------------------------------------

class TestChatGeneration:
    def test_returns_bob_output(self, svc):
        result = svc.answer("What is a cell?", TOPICS)
        assert result == MOCK_ANSWER

    def test_bob_generate_called_once(self, svc, mock_bob):
        svc.answer("Tell me about genetics.", TOPICS)
        mock_bob.generate.assert_called_once()

    def test_prompt_contains_query(self, svc, mock_bob):
        svc.answer("What is photosynthesis?", TOPICS)
        prompt = mock_bob.generate.call_args[0][0]
        assert "What is photosynthesis?" in prompt

    def test_relevant_topic_included_in_prompt(self, svc, mock_bob):
        svc.answer("How does photosynthesis work?", TOPICS)
        prompt = mock_bob.generate.call_args[0][0]
        assert "Photosynthesis" in prompt

    def test_disclaimer_instruction_in_prompt(self, svc, mock_bob):
        svc.answer("What is DNA?", TOPICS)
        prompt = mock_bob.generate.call_args[0][0]
        assert "not" in prompt.lower() or "could not" in prompt.lower()

    def test_no_topics_still_generates(self, svc, mock_bob):
        result = svc.answer("Explain relativity?", [])
        assert result == MOCK_ANSWER

    def test_chat_history_included_in_prompt(self, svc, mock_bob):
        history = [
            {"role": "user", "content": "What is a cell?"},
            {"role": "assistant", "content": "A cell is the basic unit of life."},
        ]
        svc.answer("Tell me more.", TOPICS, chat_history=history)
        prompt = mock_bob.generate.call_args[0][0]
        assert "cell" in prompt.lower()

    def test_runtime_error_propagated(self, mock_bob):
        mock_bob.generate.side_effect = RuntimeError("API down")
        svc = ChatService(bob_client=mock_bob)
        with pytest.raises(RuntimeError, match="API down"):
            svc.answer("What is a cell?", TOPICS)


# ---------------------------------------------------------------------------
# Retrieval tests
# ---------------------------------------------------------------------------

class TestRelevantRetrieval:
    def test_retrieves_relevant_topics(self, svc):
        snippets = svc._retrieve_relevant("photosynthesis plant", TOPICS)
        assert any(s["name"] == "Photosynthesis" for s in snippets)

    def test_returns_at_most_top_k(self, svc):
        from services.chat_service import TOP_K_TOPICS
        snippets = svc._retrieve_relevant("biology", TOPICS * 5)
        assert len(snippets) <= TOP_K_TOPICS

    def test_empty_topics_returns_empty(self, svc):
        snippets = svc._retrieve_relevant("any query", [])
        assert snippets == []
