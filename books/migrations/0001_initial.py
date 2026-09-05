# Generated for the reconciliation workbench foundation.

import uuid

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = [("workspaces", "0001_initial")]

    operations = [
        migrations.CreateModel(
            name="ReconciliationBook",
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
                ("name", models.CharField(max_length=160)),
                (
                    "kind",
                    models.CharField(
                        choices=[("USER", "User"), ("DEMO", "Demo")],
                        max_length=4,
                    ),
                ),
                (
                    "sample_template_version",
                    models.CharField(blank=True, max_length=80, null=True),
                ),
                ("created_at", models.DateTimeField()),
                (
                    "workspace",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="books",
                        to="workspaces.workspace",
                    ),
                ),
            ],
            options={
                "db_table": "reconciliation_book",
                "indexes": [
                    models.Index(
                        fields=["workspace", "id"],
                        name="book_workspace_public_idx",
                    ),
                    models.Index(
                        fields=["workspace", "created_at"],
                        name="book_workspace_created_idx",
                    ),
                ],
                "constraints": [
                    models.CheckConstraint(
                        condition=models.Q(("name", ""), _negated=True),
                        name="book_name_nonempty",
                    ),
                    models.CheckConstraint(
                        condition=models.Q(
                            models.Q(
                                ("kind", "USER"),
                                ("sample_template_version__isnull", True),
                            ),
                            models.Q(
                                ("kind", "DEMO"),
                                ("sample_template_version__isnull", False),
                            ),
                            _connector="OR",
                        ),
                        name="book_kind_template_consistent",
                    ),
                ],
            },
        )
    ]
