"""SciPy adapter for rectangular integer linear assignment."""

from __future__ import annotations

from typing import Sequence

import numpy as np
import scipy
from scipy.optimize import linear_sum_assignment

from reconciliation.domain.workspaces import DomainValidationError


class ScipyAssignmentSolver:
    @property
    def version(self) -> str:
        return f"scipy-{scipy.__version__}-linear-sum-assignment-v1"

    def minimize(
        self, costs: Sequence[Sequence[int]]
    ) -> tuple[tuple[int, int], ...]:
        if not costs:
            return ()
        column_count = len(costs[0])
        if column_count == 0 or any(len(row) != column_count for row in costs):
            raise DomainValidationError("assignment cost matrix must be nonempty and rectangular")
        if any(
            isinstance(value, bool) or not isinstance(value, int)
            for row in costs
            for value in row
        ):
            raise DomainValidationError("assignment costs must be integers")
        matrix = np.asarray(costs, dtype=np.int64)
        rows, columns = linear_sum_assignment(matrix)
        return tuple(
            sorted(
                ((int(row), int(column)) for row, column in zip(rows, columns, strict=True)),
                key=lambda item: item[0],
            )
        )
