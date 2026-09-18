"""
Tests for QuizService — generation, answer checking, scoring, persistence.
All BobClient calls are mocked.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from services.quiz_service import QuizService


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

MOCK_QUIZ_RESPONSE = """\
Q1. What is photosynthesis?
A) The process of making food using sunlight
B) The process of respiration
C) The movement of water
D) The breakdown of glucose
Answer: A

Q2. Where does photosynthesis occur?
A) Mitochondria
B) Nucleus
C) Chloroplast
D) Ribosome
Answer: C

Q3. What gas is released during photosynthesis?
A) Carbon dioxide
B) Nitrogen
C) Hydrogen
D) Oxygen
Answer: D

Q4. What is the primary pigment in photosynthesis?
A) Melanin
B) Chlorophyll
C) Carotene
D) Hemoglobin
Answer: B

Q5. What is the light-independent reaction called?
A) Glycolysis
B) Krebs cycle
C) Calvin cycle
D) Electron transport chain
Answer: C
"""


@pytest.fixture
def mock_bob():
    bob = MagicMock()
    bob.generate.return_value = MOCK_QUIZ_RESPONSE
    return bob


@pytest.fixture
def svc(mock_bob, tmp_path, monkeypatch):
    import services.quiz_service as qs_mod
    monkeypatch.setattr(qs_mod, "DATA_DIR", tmp_path)
    monkeypatch.setattr(qs_mod, "QUIZZES_FILE", tmp_path / "quizzes.json")
    monkeypatch.setattr(qs_mod, "ATTEMPTS_FILE", tmp_path / "attempts.json")
    return QuizService(bob_client=mock_bob)


# ---------------------------------------------------------------------------
# Generation tests
# ---------------------------------------------------------------------------

class TestQuizGeneration:
    def test_generate_returns_5_questions(self, svc, mock_bob):
        quiz = svc.generate_quiz("Photosynthesis", "Photosynthesis is the process…")
        assert len(quiz["questions"]) == 5

    def test_questions_have_required_fields(self, svc):
        quiz = svc.generate_quiz("Photosynthesis", "content")
        for q in quiz["questions"]:
            assert "question" in q
            assert "options" in q
            assert "answer" in q
            assert len(q["options"]) == 4

    def test_bob_generate_called_once(self, svc, mock_bob):
        svc.generate_quiz("Topic", "content")
        mock_bob.generate.assert_called_once()

    def test_quiz_record_has_id_and_topic(self, svc):
        quiz = svc.generate_quiz("Photosynthesis", "content")
        assert "id" in quiz
        assert quiz["topic"] == "Photosynthesis"

    def test_answers_are_valid_letters(self, svc):
        quiz = svc.generate_quiz("Bio", "content")
        for q in quiz["questions"]:
            assert q["answer"] in ("A", "B", "C", "D")

    def test_malformed_response_fills_placeholders(self, mock_bob, tmp_path, monkeypatch):
        import services.quiz_service as qs_mod
        monkeypatch.setattr(qs_mod, "DATA_DIR", tmp_path)
        monkeypatch.setattr(qs_mod, "QUIZZES_FILE", tmp_path / "quizzes.json")
        monkeypatch.setattr(qs_mod, "ATTEMPTS_FILE", tmp_path / "attempts.json")
        mock_bob.generate.return_value = "This is not a quiz at all."
        svc2 = QuizService(bob_client=mock_bob)
        quiz = svc2.generate_quiz("Topic", "content")
        assert len(quiz["questions"]) == 5


# ---------------------------------------------------------------------------
# Answer checking tests
# ---------------------------------------------------------------------------

class TestAnswerChecking:
    def test_correct_answer(self, svc):
        q = {"question": "?", "options": ["A) Yes", "B) No", "C) Maybe", "D) Never"], "answer": "A"}
        assert svc.check_answer(q, "A") is True

    def test_wrong_answer(self, svc):
        q = {"question": "?", "options": ["A) Yes", "B) No", "C) Maybe", "D) Never"], "answer": "A"}
        assert svc.check_answer(q, "B") is False

    def test_case_insensitive(self, svc):
        q = {"question": "?", "options": ["A) Yes", "B) No", "C) Maybe", "D) Never"], "answer": "C"}
        assert svc.check_answer(q, "c") is True

    def test_with_whitespace(self, svc):
        q = {"question": "?", "options": ["A) Yes", "B) No", "C) Maybe", "D) Never"], "answer": "B"}
        assert svc.check_answer(q, " B ") is True


# ---------------------------------------------------------------------------
# Scoring & persistence tests
# ---------------------------------------------------------------------------

class TestScoringAndPersistence:
    def test_save_attempt_returns_record(self, svc):
        record = svc.save_attempt("quiz-1", "Bio", ["A", "B", "C", "D", "A"], 3, 5)
        assert record["score"] == 3
        assert record["total"] == 5

    def test_attempt_is_persisted(self, svc, tmp_path):
        svc.save_attempt("quiz-1", "Bio", ["A", "C", "D", "B", "A"], 2, 5)
        attempts = svc.list_attempts()
        assert len(attempts) == 1
        assert attempts[0]["topic"] == "Bio"

    def test_multiple_attempts_accumulate(self, svc):
        svc.save_attempt("q1", "Bio", ["A"] * 5, 5, 5)
        svc.save_attempt("q2", "Chem", ["B"] * 5, 2, 5)
        assert len(svc.list_attempts()) == 2

    def test_quiz_is_persisted_on_generation(self, svc, tmp_path):
        svc.generate_quiz("Bio", "content")
        import json
        quizzes_file = tmp_path / "quizzes.json"
        assert quizzes_file.exists()
        with quizzes_file.open() as f:
            data = json.load(f)
        assert len(data) == 1
