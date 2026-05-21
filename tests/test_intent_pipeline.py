from __future__ import annotations

from datetime import date
import time

from momentum.capture.intent import parse_capture
from momentum.capture.local_model import LocalIntentModel
from momentum.capture.memory import CaptureMemory, CaptureRecord
from momentum.capture.router import ContextRouter


def test_parse_capture_representative_inputs() -> None:
    base = date(2026, 5, 21)

    task = parse_capture("tomorrow 09:30 apply to capgemini", base)
    assert task is not None
    assert task.kind == "task"
    assert task.day == date(2026, 5, 22)
    assert task.planned_time == "09:30"
    assert task.text == "apply to capgemini"

    goal = parse_capture("goal: exercise daily", base)
    assert goal is not None
    assert goal.kind == "goal"
    assert goal.text == "exercise daily"

    note = parse_capture("plan: roadmap for job search", base)
    assert note is not None
    assert note.kind == "note"
    assert note.text == "roadmap for job search"


def test_missing_local_model_falls_back_to_rules_memory_and_default(tmp_path, temp_database) -> None:
    memory = CaptureMemory(temp_database.conn)
    model = LocalIntentModel(tmp_path / "missing-model")
    router = ContextRouter(memory, local_model=model, preload_model=False)
    base = date(2026, 5, 21)

    assert model.predict("apply tonight") is None
    for _ in range(20):
        if "checkpoint missing" in model.status.lower():
            break
        time.sleep(0.01)
    assert "checkpoint missing" in model.status.lower()

    rule_route = router.route("tomorrow apply to capgemini", base, allow_model=False)
    assert rule_route is not None
    assert rule_route.intent.kind == "task"
    assert rule_route.source == "rules"

    default_route = router.route("miscellaneous context", base, allow_model=False)
    assert default_route is not None
    assert default_route.intent.kind == "note"
    assert default_route.source == "parser_default"

    examples = [
        ("recruiter followup", "task"),
        ("send resume", "task"),
        ("portfolio review", "task"),
        ("call hiring manager", "task"),
        ("daily linkedin", "goal"),
        ("exercise every day", "goal"),
        ("interview felt hard", "note"),
        ("remember salary note", "note"),
    ]
    for text, kind in examples:
        intent = parse_capture(f"{kind}: {text}", base)
        assert intent is not None
        memory.remember(CaptureRecord(intent, 0.99, "test"))

    classifier_route = router.route("recruiter message", base, allow_model=False)
    assert classifier_route is not None
    assert classifier_route.intent.kind == "task"
    assert classifier_route.source == "tiny_classifier"


def test_memory_related_and_summary_smoke(temp_repo) -> None:
    from momentum.capture.summary import build_summary

    base = date(2026, 5, 21)
    memory = CaptureMemory(temp_repo.conn)
    goal = temp_repo.add_goal("daily linkedin", created_on=base)
    task = temp_repo.add_task("send resume", base)
    temp_repo.set_task_status(task.id, "done")
    intent = parse_capture("note: capgemini interview felt rough", base)
    assert intent is not None
    event_id = memory.remember(CaptureRecord(intent, 0.9, "test", "reflection_note", None))

    related = memory.related("capgemini interview")
    assert related
    assert related[0].kind == "note"

    summary = build_summary(temp_repo, base, base)
    assert summary.metrics
    assert summary.bullets
    assert summary.start == base
    assert summary.end == base

    memory.forget(event_id)
    assert goal.id > 0
