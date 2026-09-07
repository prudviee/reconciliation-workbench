from __future__ import annotations

import json
import re
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
FEATURE_ROOT = PROJECT_ROOT / "specs" / "004-review-and-cases"


def read(name: str) -> str:
    return (FEATURE_ROOT / name).read_text(encoding="utf-8")


def test_review_release_traceability_is_complete() -> None:
    specification = read("spec.md")
    tasks = read("tasks.md")
    verification = read("verification.md")
    requirements = set(
        re.findall(r"^- \*\*(REV-\d{3})\*\*", specification, flags=re.MULTILINE)
    )
    scenarios = set(
        re.findall(r"^- \*\*(REV-A\d{2})\*\*", specification, flags=re.MULTILINE)
    )
    requirement_results = dict(
        re.findall(
            r"^\| (REV-\d{3}) \| [^|]+ \| [^|]+ \| ([^|]+) \|$",
            verification,
            flags=re.MULTILINE,
        )
    )
    scenario_results = dict(
        re.findall(
            r"^\| (REV-A\d{2}) \| ([^|]+) \|",
            verification,
            flags=re.MULTILINE,
        )
    )
    task_results = dict(
        re.findall(
            r"^\| (REV-\d{3}) \| [^|]+ \| [^|]+ \| ([^|]+) \|$",
            tasks,
            flags=re.MULTILINE,
        )
    )
    assert requirements == {f"REV-{number:03d}" for number in range(1, 17)}
    assert scenarios == {f"REV-A{number:02d}" for number in range(1, 14)}
    assert set(requirement_results) == requirements
    assert set(scenario_results) == scenarios
    assert set(task_results) == requirements
    assert all(value.strip() == "Passed" for value in requirement_results.values())
    assert all(value.strip() == "Passed" for value in scenario_results.values())
    assert all(value.strip().startswith("Yes:") for value in task_results.values())


def test_review_release_status_evidence_and_runtime_are_closed() -> None:
    assert "**Status:** Verified" in read("spec.md")
    assert "**Status:** Complete" in read("plan.md")
    assert "**Status:** Complete" in read("tasks.md")
    assert "**Status:** Verified" in read("verification.md")
    evidence_names = {
        path.name for path in (FEATURE_ROOT / "evidence").glob("REV-T*.md")
    }
    assert evidence_names == {f"REV-T{number:02d}.md" for number in range(1, 12)}
    runtime = json.loads((FEATURE_ROOT / "evidence/REV-T11-runtime.json").read_text())
    assert runtime["services"] == ["db", "web", "worker"]
    assert runtime["readiness"] == {"status": "ready", "database": "ready"}
    assert runtime["worker_heartbeat"] == "ready"
    assert runtime["private_artifact_volume"] == "shared_by_web_and_worker"
    assert runtime["migrations"] == "fully_applied_by_web_only"
