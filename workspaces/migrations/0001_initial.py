# Generated for the reconciliation workbench foundation.

from datetime import timedelta
import uuid

from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies: list[tuple[str, str]] = []

    operations = [
        migrations.CreateModel(
            name="Workspace",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("session_digest", models.CharField(max_length=64, unique=True)),
                (
                    "state",
                    models.CharField(
                        choices=[
                            ("ACTIVE", "Active"),
                            ("REVOKED", "Revoked"),
                            ("DELETED", "Deleted"),
                        ],
                        default="ACTIVE",
                        max_length=8,
                    ),
                ),
                ("created_at", models.DateTimeField()),
                ("expires_at", models.DateTimeField()),
                ("revoked_at", models.DateTimeField(blank=True, null=True)),
                ("deleted_at", models.DateTimeField(blank=True, null=True)),
                ("retained_bytes", models.BigIntegerField(default=0)),
                ("book_count", models.PositiveIntegerField(default=0)),
                ("active_job_count", models.PositiveIntegerField(default=0)),
            ],
            options={
                "db_table": "workspace",
                "indexes": [
                    models.Index(
                        fields=["state", "expires_at"],
                        name="workspace_state_expiry_idx",
                    )
                ],
                "constraints": [
                    models.CheckConstraint(
                        condition=models.Q(
                            ("expires_at", models.F("created_at") + timedelta(days=7))
                        ),
                        name="workspace_fixed_expiry_7d",
                    ),
                    models.CheckConstraint(
                        condition=models.Q(("state__in", ["ACTIVE", "REVOKED", "DELETED"])),
                        name="workspace_valid_state",
                    ),
                    models.CheckConstraint(
                        condition=models.Q(("retained_bytes__gte", 0)),
                        name="workspace_retained_bytes_nonnegative",
                    ),
                    models.CheckConstraint(
                        condition=models.Q(("book_count__gte", 0)),
                        name="workspace_book_count_nonnegative",
                    ),
                    models.CheckConstraint(
                        condition=models.Q(("active_job_count__gte", 0)),
                        name="workspace_active_jobs_nonnegative",
                    ),
                ],
            },
        )
    ]
