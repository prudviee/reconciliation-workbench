import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("workspaces", "0001_initial")]

    operations = [
        migrations.CreateModel(
            name="WorkspaceCleanupRequest",
            fields=[
                (
                    "workspace",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        primary_key=True,
                        related_name="cleanup_request",
                        serialize=False,
                        to="workspaces.workspace",
                    ),
                ),
                (
                    "reason",
                    models.CharField(
                        choices=[("EXPIRED", "Expired"), ("DELETED", "Deleted")],
                        max_length=7,
                    ),
                ),
                ("requested_at", models.DateTimeField()),
                ("processed_at", models.DateTimeField(blank=True, null=True)),
            ],
            options={
                "db_table": "workspace_cleanup_request",
                "indexes": [
                    models.Index(
                        condition=models.Q(("processed_at__isnull", True)),
                        fields=["requested_at"],
                        name="cleanup_pending_idx",
                    )
                ],
                "constraints": [
                    models.CheckConstraint(
                        condition=models.Q(("reason__in", ["EXPIRED", "DELETED"])),
                        name="cleanup_valid_reason",
                    )
                ],
            },
        ),
        migrations.AddConstraint(
            model_name="workspace",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    models.Q(
                        ("deleted_at__isnull", True),
                        ("revoked_at__isnull", True),
                        ("state", "ACTIVE"),
                    ),
                    models.Q(
                        ("deleted_at__isnull", True),
                        ("revoked_at__isnull", False),
                        ("state", "REVOKED"),
                    ),
                    models.Q(
                        ("deleted_at__isnull", False),
                        ("revoked_at__isnull", False),
                        ("state", "DELETED"),
                    ),
                    _connector="OR",
                ),
                name="workspace_lifecycle_timestamps",
            ),
        ),
    ]
