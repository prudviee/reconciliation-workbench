from __future__ import annotations

import re
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
FEATURE_ROOT = PROJECT_ROOT / "specs" / "001-foundation"


def read(name: str) -> str:
    return (FEATURE_ROOT / name).read_text(encoding="utf-8")


def test_foundation_release_traceability_is_complete() -> None:
    specification = read("spec.md")
    tasks = read("tasks.md")
    verification = read("verification.md")

    requirements = set(
        re.findall(r"^- \*\*(FND-\d{3})\*\*", specification, flags=re.MULTILINE)
    )
    scenarios = set(
        re.findall(r"^- \*\*(FND-A\d{2})\*\*", specification, flags=re.MULTILINE)
    )
    requirement_results = dict(
        re.findall(
            r"^\| (FND-\d{3}) \| [^|]+ \| [^|]+ \| ([^|]+) \|$",
            verification,
            flags=re.MULTILINE,
        )
    )
    scenario_results = dict(
        re.findall(
            r"^\| (FND-A\d{2}) \| ([^|]+) \|",
            verification,
            flags=re.MULTILINE,
        )
    )
    task_traceability = dict(
        re.findall(
            r"^\| (FND-\d{3}) \| [^|]+ \| [^|]+ \| ([^|]+) \|$",
            tasks,
            flags=re.MULTILINE,
        )
    )

    assert requirements == {f"FND-{number:03d}" for number in range(1, 14)}
    assert scenarios == {f"FND-A{number:02d}" for number in range(1, 13)}
    assert set(requirement_results) == requirements
    assert set(scenario_results) == scenarios
    assert set(task_traceability) == requirements
    assert all(result.strip().startswith("Pass") for result in requirement_results.values())
    assert all(result.strip().startswith("Pass") for result in scenario_results.values())
    assert all(result.strip().startswith("Yes:") for result in task_traceability.values())


def test_foundation_release_status_and_task_evidence_are_closed() -> None:
    assert "**Status:** Verified" in read("spec.md")
    assert "**Status:** Complete" in read("plan.md")
    assert "**Status:** Complete" in read("tasks.md")
    assert "**Status:** Verified" in read("verification.md")

    evidence_names = {
        path.name for path in (FEATURE_ROOT / "evidence").glob("FND-T*.md")
    }
    assert evidence_names == {f"FND-T{number:02d}.md" for number in range(1, 11)}
