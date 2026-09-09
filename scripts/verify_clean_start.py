"""Rebuild and verify the complete local Compose stack from empty app volumes."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from time import monotonic
from urllib.request import urlopen


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SERVICES = {"db", "web", "worker"}
COMPOSE_PROJECT = "reconciliation-workbench"


class VerificationFailure(RuntimeError):
    pass


def run(*command: str, cwd: Path = PROJECT_ROOT) -> str:
    completed = subprocess.run(
        command,
        cwd=cwd,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if completed.returncode:
        detail = completed.stderr.strip() or completed.stdout.strip()
        raise VerificationFailure(f"{' '.join(command)} failed: {detail}")
    return completed.stdout.strip()


def readiness() -> dict[str, object]:
    with urlopen("http://127.0.0.1:8010/health/ready", timeout=5) as response:
        if response.status != 200:
            raise VerificationFailure(f"readiness returned HTTP {response.status}")
        payload = json.load(response)
    expected = {
        "status": "ready",
        "database": "ready",
        "worker_status": "healthy",
    }
    if any(payload.get(key) != value for key, value in expected.items()):
        raise VerificationFailure(f"unexpected readiness payload: {payload!r}")
    if not isinstance(payload.get("worker_heartbeat_age_seconds"), (int, float)):
        raise VerificationFailure(f"missing worker heartbeat age: {payload!r}")
    return payload


def compose(*arguments: str, cwd: Path) -> str:
    return run("docker", "compose", "-p", COMPOSE_PROJECT, *arguments, cwd=cwd)


def verify_migration_owner() -> None:
    compose = (PROJECT_ROOT / "compose.yaml").read_text(encoding="utf-8")
    if compose.count("python manage.py migrate --noinput") != 1:
        raise VerificationFailure(
            "compose.yaml must assign migration application to exactly one service"
        )


def staged_compose_project() -> tempfile.TemporaryDirectory[str]:
    temporary = tempfile.TemporaryDirectory(prefix="reconciliation-workbench-")
    target = Path(temporary.name) / "source"
    shutil.copytree(
        PROJECT_ROOT,
        target,
        ignore=shutil.ignore_patterns(
            ".git",
            ".venv",
            ".tmp",
            "__pycache__",
            ".pytest_cache",
            "*.pyc",
            "FND-T09-runtime.json",
        ),
    )
    return temporary


def verify(timeout_seconds: int) -> dict[str, object]:
    verify_migration_owner()
    with staged_compose_project() as temporary:
        compose_root = Path(temporary) / "source"
        compose(
            "down",
            "--volumes",
            "--remove-orphans",
            cwd=compose_root,
        )
        started = monotonic()
        compose(
            "up",
            "--build",
            "--detach",
            "--wait",
            "--wait-timeout",
            str(timeout_seconds),
            cwd=compose_root,
        )
        elapsed = round(monotonic() - started, 3)

        running = set(
            compose(
                "ps",
                "--status",
                "running",
                "--services",
                cwd=compose_root,
            ).splitlines()
        )
        if running != SERVICES:
            raise VerificationFailure(
                f"expected running services {sorted(SERVICES)}, found {sorted(running)}"
            )

        ready = readiness()
        database_probe = compose(
            "exec",
            "-T",
            "db",
            "pg_isready",
            "-U",
            "reconciliation",
            "-d",
            "reconciliation",
            cwd=compose_root,
        )
        compose(
            "exec",
            "-T",
            "worker",
            "sh",
            "-c",
            "test -s /tmp/reconciliation-worker-heartbeat",
            cwd=compose_root,
        )
        volume_probe = "shared-private-artifact-volume"
        compose(
            "exec",
            "-T",
            "web",
            "sh",
            "-c",
            f"printf '%s' '{volume_probe}' > /var/lib/reconciliation/artifacts/.volume-probe",
            cwd=compose_root,
        )
        observed_probe = compose(
            "exec",
            "-T",
            "worker",
            "cat",
            "/var/lib/reconciliation/artifacts/.volume-probe",
            cwd=compose_root,
        )
        if observed_probe != volume_probe:
            raise VerificationFailure("web and worker do not share the private artifact volume")
        compose(
            "exec",
            "-T",
            "web",
            "rm",
            "/var/lib/reconciliation/artifacts/.volume-probe",
            cwd=compose_root,
        )
        compose(
            "exec",
            "-T",
            "web",
            "python",
            "manage.py",
            "migrate",
            "--check",
            cwd=compose_root,
        )

        return {
            "verified_at": datetime.now(UTC).isoformat(),
            "startup_seconds": elapsed,
            "services": sorted(running),
            "readiness": ready,
            "database_probe": database_probe,
            "worker_heartbeat": "ready",
            "private_artifact_volume": "shared_by_web_and_worker",
            "migrations": "fully_applied_by_web_only",
            "versions": {
                "docker": run(
                    "docker",
                    "version",
                    "--format",
                    "{{.Server.Version}}",
                    cwd=compose_root,
                ),
                "compose": run("docker", "compose", "version", "--short"),
                "python": compose(
                    "exec",
                    "-T",
                    "web",
                    "python",
                    "--version",
                    cwd=compose_root,
                ),
                "django": compose(
                    "exec",
                    "-T",
                    "web",
                    "python",
                    "-c",
                    "import django; print(django.get_version())",
                    cwd=compose_root,
                ),
                "postgresql": compose(
                    "exec",
                    "-T",
                    "db",
                    "postgres",
                    "--version",
                    cwd=compose_root,
                ),
            },
        }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--timeout", type=int, default=180, help="startup timeout in seconds")
    parser.add_argument("--evidence", type=Path, help="write successful JSON evidence here")
    parser.add_argument(
        "--remove-volumes-after",
        action="store_true",
        help="stop the verified stack and remove its project volumes",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.timeout < 1:
        print("--timeout must be positive", file=sys.stderr)
        return 2
    try:
        result = verify(args.timeout)
        if args.evidence:
            output = args.evidence
            if not output.is_absolute():
                output = PROJECT_ROOT / output
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(result, indent=2))
        return 0
    except (OSError, VerificationFailure, ValueError) as error:
        print(f"clean-start verification failed: {error}", file=sys.stderr)
        try:
            logs = compose("logs", "--no-color", "--tail", "80", cwd=PROJECT_ROOT)
            if logs:
                print(logs, file=sys.stderr)
        except (OSError, VerificationFailure):
            pass
        return 1
    finally:
        if args.remove_volumes_after:
            subprocess.run(
                [
                    "docker",
                    "compose",
                    "-p",
                    COMPOSE_PROJECT,
                    "down",
                    "--volumes",
                    "--remove-orphans",
                ],
                cwd=PROJECT_ROOT,
                check=False,
            )


if __name__ == "__main__":
    raise SystemExit(main())
