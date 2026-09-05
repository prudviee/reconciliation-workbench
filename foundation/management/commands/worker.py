from __future__ import annotations

import os
import time
from pathlib import Path

from django.core.management.base import BaseCommand
from django.db import close_old_connections, connection


class Command(BaseCommand):
    help = "Run the temporary foundation worker heartbeat."

    def add_arguments(self, parser) -> None:
        parser.add_argument("--once", action="store_true")
        parser.add_argument("--interval", type=float, default=5.0)

    def handle(self, *args, **options) -> None:
        interval = options["interval"]
        if interval <= 0:
            raise ValueError("--interval must be greater than zero")

        while True:
            close_old_connections()
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
                cursor.fetchone()

            heartbeat_path = os.getenv("WORKER_HEARTBEAT_FILE")
            if heartbeat_path:
                Path(heartbeat_path).touch()
            self.stdout.write("worker heartbeat ready")

            if options["once"]:
                return
            time.sleep(interval)
