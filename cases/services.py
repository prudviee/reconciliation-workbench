"""Materialize stable cases from immutable run facts."""

from __future__ import annotations

from datetime import datetime

from reconciliation.domain import CaseKind, CaseResultKind, RecordSide, WorkspaceId, ambiguity_case_key, pair_case_key, unpaired_case_key
from reconciliation.models import AssignmentComponent, DecisionHealthSnapshot, ReconciliationRun, RunPair, RunUnpaired

from .models import CaseOccurrence, CaseScopeProjection, InvestigationCase


def materialize_run_cases(workspace_id: WorkspaceId, run: ReconciliationRun, *, is_current: bool, created_at: datetime) -> tuple[CaseOccurrence, ...]:
    health_by_revision = {
        item.decision_revision_id: item
        for item in DecisionHealthSnapshot.objects.owned_by(workspace_id).filter(run=run)
    }
    health_by_observation = {
        observation_id: item
        for item in health_by_revision.values()
        for observation_id in item.current_observation_ids
    }
    occurrences: list[CaseOccurrence] = []
    for pair in RunPair.objects.owned_by(workspace_id).filter(run=run).order_by("id"):
        key = pair_case_key(book_id=str(run.scope.book_id), left_id=str(pair.left_logical_id), right_id=str(pair.right_logical_id))
        case = _case(workspace_id, run, key.kind, str(key), key.digest, created_at, left_logical_id=pair.left_logical_id, right_logical_id=pair.right_logical_id)
        occurrences.append(CaseOccurrence.objects.create(
            workspace_id=workspace_id.value, case=case, run=run, result_kind=CaseResultKind.PAIR, pair=pair,
            state_snapshot={"origin": pair.origin, "score_bp": pair.score_bp, "global_gap_bp": pair.global_gap_bp}, created_at=created_at,
        ))
    for unpaired in RunUnpaired.objects.owned_by(workspace_id).filter(run=run).order_by("id"):
        side = RecordSide(unpaired.side)
        key = unpaired_case_key(book_id=str(run.scope.book_id), side=side, record_id=str(unpaired.logical_transaction_id))
        case = _case(workspace_id, run, key.kind, str(key), key.digest, created_at, record_logical_id=unpaired.logical_transaction_id, record_side=side.value)
        occurrences.append(CaseOccurrence.objects.create(
            workspace_id=workspace_id.value, case=case, run=run, result_kind=CaseResultKind.UNPAIRED, unpaired=unpaired,
            state_snapshot={"reason": unpaired.reason, "related_observation_ids": unpaired.related_observation_ids}, created_at=created_at,
        ))
    ambiguous = {
        str(value) for value in RunUnpaired.objects.owned_by(workspace_id).filter(
            run=run, reason__in=["AMBIGUOUS", "COMPUTATION_LIMITED"]
        ).values_list("observation_id", flat=True)
    }
    input_logical = {str(item.observation_id): str(item.logical_transaction_id) for item in run.inputs.all()}
    for component in AssignmentComponent.objects.owned_by(workspace_id).filter(run=run).order_by("component_key"):
        members = set(component.left_observation_ids) | set(component.right_observation_ids)
        if not members.intersection(ambiguous):
            continue
        left_ids = tuple(input_logical[item] for item in component.left_observation_ids)
        right_ids = tuple(input_logical[item] for item in component.right_observation_ids)
        key = ambiguity_case_key(book_id=str(run.scope.book_id), scope_id=str(run.scope_id), policy_digest=run.policy_revision.digest, left_ids=left_ids, right_ids=right_ids)
        case = _case(
            workspace_id, run, key.kind, str(key), key.digest, created_at,
            ambiguity_scope_id=run.scope_id, policy_digest=run.policy_revision.digest,
            ambiguity_left_logical_ids=list(left_ids), ambiguity_right_logical_ids=list(right_ids),
        )
        occurrences.append(CaseOccurrence.objects.create(
            workspace_id=workspace_id.value, case=case, run=run, result_kind=CaseResultKind.AMBIGUITY, component=component,
            state_snapshot={"complete": component.complete, "limit_reason": component.limit_reason, "candidate_count": component.candidate_count}, created_at=created_at,
        ))
    if is_current:
        current_ids = [item.case_id for item in occurrences]
        CaseScopeProjection.objects.owned_by(workspace_id).filter(scope_id=run.scope_id).exclude(case_id__in=current_ids).delete()
        for occurrence in occurrences:
            health = _health(occurrence, health_by_revision, health_by_observation)
            CaseScopeProjection.objects.update_or_create(
                workspace_id=workspace_id.value, case=occurrence.case, scope_id=run.scope_id,
                defaults={
                    "current_occurrence": occurrence, "run": run,
                    "review_health": None if health is None else health.health,
                    "attention": [] if health is None else health.attention,
                    "applied_data_generation": run.data_generation,
                    "applied_resolution_generation": run.resolution_generation,
                    "updated_at": created_at,
                },
            )
    return tuple(occurrences)


def _case(workspace_id, run, kind, stable_key, digest, created_at, **identity):
    existing = InvestigationCase.objects.owned_by(workspace_id).filter(book_id=run.scope.book_id, stable_key=stable_key).first()
    if existing is not None:
        return existing
    return InvestigationCase.objects.create(
        workspace_id=workspace_id.value, book_id=run.scope.book_id,
        kind=kind.value if isinstance(kind, CaseKind) else kind,
        stable_key=stable_key, digest=digest, created_at=created_at, **identity,
    )


def _health(occurrence, by_revision, by_observation):
    if occurrence.pair_id is not None and occurrence.pair.decision_revision_id is not None:
        return by_revision.get(occurrence.pair.decision_revision_id)
    if occurrence.unpaired_id is not None:
        return by_observation.get(str(occurrence.unpaired.observation_id))
    return None
