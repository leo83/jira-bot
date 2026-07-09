"""Tests for SprintService similarity scoring and sprint selection."""

from app.sprint_service import SprintService


def _service():
    # SprintService only stores the client; _calculate_similarity/find_sprint
    # logic never touches self.jira directly (we stub _get_all_sprints).
    return SprintService(None)


def test_similarity_identical_is_one():
    svc = _service()
    assert svc._calculate_similarity("Sprint A", "Sprint A") == 1.0


def test_similarity_unrelated_is_low():
    svc = _service()
    score = svc._calculate_similarity("2025Q4-S3_agent", "zzzzz")
    assert 0.0 <= score < 0.4


def test_similarity_word_match_transliteration():
    svc = _service()
    # Docstring example: "s3 agent" should match "2025Q4-S3_агент"
    score = svc._calculate_similarity("2025Q4-S3_агент", "s3 agent")
    assert score >= 0.4


def test_find_sprint_active_single():
    svc = _service()
    svc._get_all_sprints = lambda: [
        {"id": 10, "name": "Active One", "state": "active"},
        {"id": 11, "name": "Future One", "state": "future"},
    ]
    sprint_id, message = svc.find_sprint("active")
    assert sprint_id == 10
    assert message is None


def test_find_sprint_active_none():
    svc = _service()
    svc._get_all_sprints = lambda: [
        {"id": 11, "name": "Future One", "state": "future"},
    ]
    sprint_id, message = svc.find_sprint("active")
    assert sprint_id is None
    assert "No active sprint" in message


def test_find_sprint_active_multiple():
    svc = _service()
    svc._get_all_sprints = lambda: [
        {"id": 10, "name": "Active One", "state": "active"},
        {"id": 12, "name": "Active Two", "state": "active"},
    ]
    sprint_id, message = svc.find_sprint("active")
    assert sprint_id is None
    assert "Multiple active sprints" in message


def test_find_sprint_by_name_match():
    svc = _service()
    svc._get_all_sprints = lambda: [
        {"id": 10, "name": "2025Q4-S3_агент", "state": "future"},
        {"id": 11, "name": "2025Q4-S1_backend", "state": "future"},
    ]
    sprint_id, message = svc.find_sprint("s3 agent")
    assert sprint_id == 10
    assert message is None


def test_find_sprint_no_match():
    svc = _service()
    svc._get_all_sprints = lambda: [
        {"id": 10, "name": "2025Q4-S3_agent", "state": "future"},
    ]
    sprint_id, message = svc.find_sprint("zzzzz-nonexistent")
    assert sprint_id is None
    assert "No sprint found" in message


def test_find_sprint_empty_project():
    svc = _service()
    svc._get_all_sprints = lambda: []
    sprint_id, message = svc.find_sprint("anything")
    assert sprint_id is None
    assert "No sprints found" in message
