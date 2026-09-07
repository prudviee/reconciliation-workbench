from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def test_domain_import_needs_no_django_settings_or_database() -> None:
    project_root = Path(__file__).resolve().parents[1]
    environment = os.environ.copy()
    environment.pop("DJANGO_SETTINGS_MODULE", None)
    probe = """
import sys
before = set(sys.modules)
import reconciliation.domain
loaded = set(sys.modules) - before
forbidden = sorted(name for name in loaded if name == 'django' or name.startswith('django.') or name == 'psycopg' or name.startswith('psycopg.'))
assert not forbidden, forbidden
assert 'reconciliation.domain.reconciliation' in loaded
print('domain import: independent')
"""

    completed = subprocess.run(
        [sys.executable, "-c", probe],
        cwd=project_root,
        env=environment,
        check=True,
        capture_output=True,
        text=True,
    )

    assert completed.stdout.strip() == "domain import: independent"
