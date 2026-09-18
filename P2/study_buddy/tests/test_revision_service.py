"""
Tests for RevisionService — plan generation, validation, persistence.
All BobClient calls are mocked.
"""
from __future__ import annotations

import datetime
from unittest.mock import MagicMock

import pytest

from services.revision_service import RevisionService, RevisionValidationError


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

MOCK_PLAN = (
    "Day 1: Study Introduction to Biology — read chapter 1 and take notes.\n"
    "Day 2: Study Cell Structure — review diagrams.\n"
    "Day 3: Full review and rest.\n"
)


@pytest.fixture
def mock_bob():
    bob = MagicMock()
    bob.generate.return_value = MOCK_PLAN
    return bob


@pytest.fixture
def svc(mock_bob, tmp_path, monkeypatch):
    import services.revision_service as rs_mod
    monkeypatch.setattr(rs_mod, "DATA_DIR", tmp_path)
    monkeypatch.setattr(rs_mod, "REVISION_PLANS_FILE", tmp_path / "revision_plans.json")
    return RevisionService(bob_client=mock_bob)


def future_date(days: int = 7) -> datetime.date:
    return datetime.date.today() + datetime.timedelta(days=days)


# ---------------------------------------------------------------------------
# Validation tests
# ---------------------------------------------------------------------------

class TestRevisionValidation:
    def test_past_exam_date_raises(self, svc):
        past = datetime.date.today() - datetime.timedelta(days=1)
        with pytest.raises(RevisionValidationError, match="future"):
            svc.generate_plan(past, ["Topic A"])

    def test_today_exam_date_raises(self, svc):
        with pytest.raises(RevisionValidationError, match="future"):
            svc.generate_plan(datetime.date.today(), ["Topic A"])

    def test_empty_topics_raises(self, svc):
        with pytest.raises(RevisionValidationError, match="topic"):
            svc.generate_plan(future_date(), [])

    def test_valid_inputs_pass(self, svc, mock_bob):
        plan = svc.generate_plan(future_date(), ["Topic A", "Topic B"])
        assert plan is not None
        mock_bob.generate.assert_called_once()


# ---------------------------------------------------------------------------
# Generation tests
# ---------------------------------------------------------------------------

class TestPlanGeneration:
    def test_plan_contains_bob_output(self, svc):
        plan = svc.generate_plan(future_date(), ["Bio"])
        assert plan["plan_text"] == MOCK_PLAN

    def test_plan_record_has_required_keys(self, svc):
        plan = svc.generate_plan(future_date(), ["Bio", "Chem"])
        for key in ("id", "exam_date", "topics", "plan_text", "created_at"):
            assert key in plan

    def test_exam_date_in_record(self, svc):
        exam = future_date(10)
        plan = svc.generate_plan(exam, ["Topic"])
        assert plan["exam_date"] == exam.isoformat()

    def test_topics_in_record(self, svc):
        topics = ["Topic A", "Topic B", "Topic C"]
        plan = svc.generate_plan(future_date(), topics)
        assert plan["topics"] == topics

    def test_prompt_includes_exam_date(self, svc, mock_bob):
        exam = future_date(5)
        svc.generate_plan(exam, ["Biology"])
        prompt_arg = mock_bob.generate.call_args[0][0]
        assert exam.isoformat() in prompt_arg

    def test_prompt_includes_topics(self, svc, mock_bob):
        svc.generate_plan(future_date(), ["Genetics", "Evolution"])
        prompt_arg = mock_bob.generate.call_args[0][0]
        assert "Genetics" in prompt_arg
        assert "Evolution" in prompt_arg

    def test_document_title_in_prompt(self, svc, mock_bob):
        svc.generate_plan(future_date(), ["Topic"], document_title="Biology Notes")
        prompt_arg = mock_bob.generate.call_args[0][0]
        assert "Biology Notes" in prompt_arg


# ---------------------------------------------------------------------------
# Persistence tests
# ---------------------------------------------------------------------------

class TestPlanPersistence:
    def test_plan_is_saved(self, svc, tmp_path):
        svc.generate_plan(future_date(), ["Topic A"])
        plans = svc.list_plans()
        assert len(plans) == 1

    def test_multiple_plans_accumulate(self, svc):
        svc.generate_plan(future_date(5), ["Topic A"])
        svc.generate_plan(future_date(10), ["Topic B"])
        assert len(svc.list_plans()) == 2

    def test_list_plans_empty_initially(self, svc):
        assert svc.list_plans() == []
