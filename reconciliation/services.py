"""Three-phase synchronous runner: freeze, compute, and atomic publication."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable
from uuid import UUID

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from books.models import PolicyRevision, ReconciliationBook, ReconciliationScope
from ingestion.models import DatasetMembership
from jobs.models import WorkItem
from jobs.services import TransientJobFailure, enqueue
from reconciliation.domain import (
    AcceptedUnmatched,
    CanonicalSide,
    CanonicalState,
    DecisionAction,
    DecisionAuthorityKind,
    DecisionHealthEvidence,
    DecisionInputs,
    EngineResult,
    EngineSnapshot,
    JobKind,
    ManualLink,
    MatchRecord,
    PairOrigin,
    RecordSide,
    ReferenceSemantics,
    RejectedRelationship,
    ReservedIdentity,
    WorkspaceId,
    canonical_result_json,
    engine_result_digest,
    project_decision_health,
    reconcile,
)
from reconciliation.policies import comparison_policy_from_payload, matching_policy_from_payload
from reconciliation.solvers import ScipyAssignmentSolver
from resolutions.models import Decision, DecisionRevision
from workspaces.lifecycle import WorkspaceLifecycleService
from workspaces.models import Workspace
from workspaces.repositories import WorkspaceUnavailable

from .models import (
    AssignmentComponent,
    CandidateEvidence,
    CurrentDecisionHealth,
    DecisionHealthSnapshot,
    FieldComparison,
    ReconciliationRun,
    RunDecisionInput,
    RunDiagnostic,
    RunFreshness,
    RunInput,
    RunLifecycle,
    RunProgressStage,
    RunPair,
    RunUnpaired,
)


class RunUnavailable(LookupError):
    """A run or dependency is unavailable inside the authorized workspace."""


class RunStateConflict(RuntimeError):
    """The requested phase is incompatible with the durable run state."""


class RunResultMismatch(RuntimeError):
    """Computed evidence does not match the frozen run manifest."""


@dataclass(frozen=True, slots=True)
class FrozenRun:
    run_id: UUID
    manifest_hash: str
    input_count: int
    decision_count: int
    work_item_id: UUID


@dataclass(frozen=True, slots=True)
class PublishedRun:
    run_id: UUID
    freshness: RunFreshness
    result_digest: str
    pair_count: int
    unpaired_count: int


def _no_publication_probe(_run: ReconciliationRun) -> None:
    return None


@dataclass(slots=True)
class ReconciliationRunService:
    clock: Callable[[], datetime] = timezone.now
    lifecycle_service: WorkspaceLifecycleService = field(default_factory=WorkspaceLifecycleService)
    publication_probe: Callable[[ReconciliationRun], None] = _no_publication_probe

    def create_run_manifest(self, workspace_id: WorkspaceId, scope_id: UUID) -> FrozenRun:
        created_at = self.clock()
        with transaction.atomic():
            self._require_active_workspace(workspace_id, created_at, lock=True)
            try:
                scope_hint = (
                    ReconciliationScope.objects.owned_by(workspace_id)
                    .only("id", "book_id")
                    .get(id=scope_id)
                )
                book = (
                    ReconciliationBook.objects.select_for_update()
                    .owned_by(workspace_id)
                    .get(id=scope_hint.book_id)
                )
                scope = (
                    ReconciliationScope.objects.select_for_update(of=("self",))
                    .owned_by(workspace_id)
                    .select_related(
                        "book",
                        "left_dataset__current_revision",
                        "right_dataset__current_revision",
                    )
                    .get(id=scope_id)
                )
            except (
                ReconciliationBook.DoesNotExist,
                ReconciliationScope.DoesNotExist,
            ) as error:
                raise RunUnavailable from error
            left_revision = scope.left_dataset.current_revision
            right_revision = scope.right_dataset.current_revision
            if left_revision is None or right_revision is None:
                raise RunUnavailable("both scope datasets require an active revision")
            policy = (
                PolicyRevision.objects.owned_by(workspace_id)
                .filter(book=book)
                .order_by("-revision", "-id")
                .first()
            )
            if policy is None:
                raise RunUnavailable("the book requires a policy revision")
            matching_policy = matching_policy_from_payload(policy.matching_policy)
            left_members = self._members(workspace_id, left_revision.id)
            right_members = self._members(workspace_id, right_revision.id)
            decisions = self._active_decisions(workspace_id, book.id)
            manifest = {
                "schema": "reconciliation-run-manifest-v1",
                "workspace_id": str(workspace_id.value),
                "book_id": str(book.id),
                "scope_id": str(scope.id),
                "coverage_key": scope.coverage_key,
                "data_generation": book.generation,
                "resolution_generation": book.resolution_generation,
                "scope_generation": scope.generation,
                "left_revision_id": str(left_revision.id),
                "right_revision_id": str(right_revision.id),
                "policy_revision_id": str(policy.id),
                "policy_digest": policy.digest,
                "engine_version": matching_policy.engine_version,
                "solver_version": matching_policy.solver_version,
                "left_inputs": self._manifest_members(left_members),
                "right_inputs": self._manifest_members(right_members),
                "decision_revision_ids": [str(item.id) for item in decisions],
            }
            manifest_hash = _canonical_digest(manifest)
            existing = ReconciliationRun.objects.owned_by(workspace_id).filter(
                scope=scope, manifest_hash=manifest_hash
            ).first()
            if existing is not None:
                work_item = enqueue(
                    workspace_id,
                    JobKind.RECONCILIATION_RUN,
                    max_attempts=settings.JOBS_RUN_MAX_ATTEMPTS,
                    now=created_at,
                    reconciliation_run=existing,
                )
                return FrozenRun(
                    existing.id,
                    existing.manifest_hash,
                    existing.inputs.count(),
                    existing.decision_inputs.count(),
                    work_item.id,
                )
            run = ReconciliationRun.objects.create(
                workspace_id=workspace_id.value,
                scope=scope,
                left_revision=left_revision,
                right_revision=right_revision,
                policy_revision=policy,
                manifest=manifest,
                manifest_hash=manifest_hash,
                data_generation=book.generation,
                resolution_generation=book.resolution_generation,
                scope_generation=scope.generation,
                engine_version=matching_policy.engine_version,
                solver_version=matching_policy.solver_version,
                progress_stage=RunProgressStage.QUEUED,
                progress_counts={
                    "inputs": len(left_members) + len(right_members),
                    "decisions": len(decisions),
                },
                created_at=created_at,
            )
            RunInput.objects.bulk_create(
                [
                    RunInput(
                        workspace_id=workspace_id.value,
                        run=run,
                        side=side.value,
                        logical_transaction_id=member.logical_transaction_id,
                        observation_id=member.observation_id,
                    )
                    for side, members in ((RecordSide.LEFT, left_members), (RecordSide.RIGHT, right_members))
                    for member in members
                ]
            )
            RunDecisionInput.objects.bulk_create(
                [RunDecisionInput(workspace_id=workspace_id.value, run=run, decision_revision=item) for item in decisions]
            )
            work_item = enqueue(
                workspace_id,
                JobKind.RECONCILIATION_RUN,
                max_attempts=settings.JOBS_RUN_MAX_ATTEMPTS,
                now=created_at,
                reconciliation_run=run,
            )
            return FrozenRun(
                run.id,
                manifest_hash,
                len(left_members) + len(right_members),
                len(decisions),
                work_item.id,
            )

    def execute_and_publish_run(
        self,
        workspace_id: WorkspaceId,
        run_id: UUID,
        *,
        attempt_token: str | None = None,
    ) -> PublishedRun:
        now = self.clock()
        self._require_active_workspace(workspace_id, now, lock=False)
        run = self._get_run(workspace_id, run_id)
        if run.lifecycle == RunLifecycle.COMPLETED:
            assert run.result_digest is not None
            return PublishedRun(run.id, RunFreshness(run.freshness), run.result_digest, run.result_counts["pairs"], run.result_counts["unpaired"])
        claim_filter = {"id": run.id}
        if attempt_token is None:
            if run.lifecycle not in (RunLifecycle.FROZEN, RunLifecycle.FAILED):
                raise RunStateConflict("run is already executing")
            claim_filter["lifecycle__in"] = (RunLifecycle.FROZEN, RunLifecycle.FAILED)
        claimed = ReconciliationRun.objects.owned_by(workspace_id).filter(
            **claim_filter
        ).update(
            lifecycle=RunLifecycle.RUNNING,
            freshness=RunFreshness.PENDING,
            started_at=now,
            completed_at=None,
            failure_code=None,
            current_attempt_token=attempt_token,
            progress_stage=RunProgressStage.LOADING_INPUTS,
            progress_counts={
                "inputs": len(run.manifest["left_inputs"])
                + len(run.manifest["right_inputs"]),
                "decisions": len(run.manifest["decision_revision_ids"]),
            },
        )
        if claimed == 0:
            raise RunStateConflict("run is already executing")
        try:
            result = self.compute_run(workspace_id, run.id)
            return self.publish_run(workspace_id, run.id, result, attempt_token=attempt_token)
        except Exception as error:
            ReconciliationRun.objects.owned_by(workspace_id).filter(
                id=run.id, lifecycle=RunLifecycle.RUNNING, current_attempt_token=attempt_token
            ).update(
                lifecycle=RunLifecycle.FAILED,
                failure_code=type(error).__name__[:80],
                progress_stage=RunProgressStage.FAILED,
                current_attempt_token=None,
            )
            raise

    def compute_run(self, workspace_id: WorkspaceId, run_id: UUID) -> EngineResult:
        run = self._get_run(workspace_id, run_id)
        if run.lifecycle not in (RunLifecycle.FROZEN, RunLifecycle.RUNNING, RunLifecycle.FAILED):
            raise RunStateConflict("completed runs cannot be recomputed")
        inputs = tuple(
            RunInput.objects.owned_by(workspace_id)
            .filter(run=run)
            .select_related(
                "logical_transaction",
                "observation__raw_row__attempt__contract_revision",
            )
            .order_by("side", "observation_id")
        )
        left = tuple(self._match_record(item) for item in inputs if item.side == RecordSide.LEFT)
        right = tuple(self._match_record(item) for item in inputs if item.side == RecordSide.RIGHT)
        snapshot = EngineSnapshot(str(run.left_revision_id), str(run.right_revision_id), left, right)
        decision_rows = tuple(
            RunDecisionInput.objects.owned_by(workspace_id)
            .filter(run=run)
            .select_related(
                "decision_revision__decision",
                "decision_revision__left_logical",
                "decision_revision__right_logical",
                "decision_revision__record_logical",
            )
            .order_by("decision_revision_id")
        )
        decisions = self._decision_inputs(inputs, decision_rows)
        ReconciliationRun.objects.owned_by(workspace_id).filter(
            id=run.id,
            lifecycle=RunLifecycle.RUNNING,
        ).update(
            progress_stage=RunProgressStage.MATCHING,
            progress_counts={
                "inputs loaded": len(inputs),
                "decisions loaded": len(decision_rows),
            },
        )
        matching = matching_policy_from_payload(run.policy_revision.matching_policy)
        comparison = comparison_policy_from_payload(run.policy_revision.comparison_policy)
        solver = ScipyAssignmentSolver()
        if solver.version != run.solver_version or matching.solver_version != run.solver_version:
            raise RunResultMismatch("the frozen solver version is unavailable")
        return reconcile(snapshot=snapshot, matching_policy=matching, comparison_policy=comparison, decisions=decisions, solver=solver)

    def publish_run(
        self,
        workspace_id: WorkspaceId,
        run_id: UUID,
        result: EngineResult,
        *,
        attempt_token: str | None = None,
    ) -> PublishedRun:
        completed_at = self.clock()
        publishing_counts = {
            "pairs computed": len(result.pairs),
            "unpaired computed": len(result.unpaired),
            "candidates computed": len(result.candidates),
            "components computed": len(result.components),
            "diagnostics computed": len(result.diagnostics),
        }
        ReconciliationRun.objects.owned_by(workspace_id).filter(
            id=run_id,
            lifecycle=RunLifecycle.RUNNING,
        ).update(
            progress_stage=RunProgressStage.PUBLISHING,
            progress_counts=publishing_counts,
        )
        with transaction.atomic():
            self._require_active_workspace(workspace_id, completed_at, lock=True)
            try:
                run_hint = (
                    ReconciliationRun.objects.owned_by(workspace_id)
                    .select_related("scope")
                    .only("id", "scope_id", "scope__book_id")
                    .get(id=run_id)
                )
                book = (
                    ReconciliationBook.objects.select_for_update()
                    .owned_by(workspace_id)
                    .get(id=run_hint.scope.book_id)
                )
                scope = (
                    ReconciliationScope.objects.select_for_update(of=("self",))
                    .owned_by(workspace_id)
                    .select_related("left_dataset", "right_dataset")
                    .get(id=run_hint.scope_id, book=book)
                )
                run = (
                    ReconciliationRun.objects.select_for_update(of=("self",))
                    .owned_by(workspace_id)
                    .select_related("policy_revision")
                    .get(id=run_id, scope=scope)
                )
            except (
                ReconciliationBook.DoesNotExist,
                ReconciliationRun.DoesNotExist,
                ReconciliationScope.DoesNotExist,
            ) as error:
                raise RunUnavailable from error
            if run.lifecycle == RunLifecycle.COMPLETED:
                raise RunStateConflict("run has already been published")
            if run.lifecycle != RunLifecycle.RUNNING:
                raise RunStateConflict("run must be running before publication")
            if attempt_token is not None and run.current_attempt_token != attempt_token:
                raise RunStateConflict(
                    "a newer attempt has reclaimed this run; the fenced attempt cannot publish"
                )
            inputs = tuple(
                RunInput.objects.owned_by(workspace_id)
                .filter(run=run)
                .select_related(
                    "observation__raw_row__attempt__contract_revision",
                    "logical_transaction",
                )
            )
            self._validate_result(run, inputs, result)
            payload = json.loads(canonical_result_json(result))
            latest_policy_id = (
                PolicyRevision.objects.owned_by(workspace_id).filter(book_id=scope.book_id).order_by("-revision", "-id").values_list("id", flat=True).first()
            )
            fresh = (
                scope.left_dataset.current_revision_id == run.left_revision_id
                and scope.right_dataset.current_revision_id == run.right_revision_id
                and latest_policy_id == run.policy_revision_id
                and book.generation == run.data_generation
                and book.resolution_generation == run.resolution_generation
                and scope.generation == run.scope_generation
            )
            self._persist_result(workspace_id, run, inputs, result, payload)
            self._persist_decision_health(
                workspace_id,
                run,
                inputs,
                result,
                is_current=fresh,
                created_at=completed_at,
            )
            from cases.services import materialize_run_cases

            materialize_run_cases(
                workspace_id,
                run,
                is_current=fresh,
                created_at=completed_at,
            )
            self.publication_probe(run)
            freshness = RunFreshness.CURRENT if fresh else RunFreshness.STALE
            digest = engine_result_digest(result)
            counts = {
                "inputs": len(result.input_left_ids) + len(result.input_right_ids),
                "pairs": len(result.pairs),
                "unpaired": len(result.unpaired),
                "candidates": len(result.candidates),
                "components": len(result.components),
                "diagnostics": len(result.diagnostics),
            }
            ReconciliationRun.objects.filter(id=run.id).update(
                lifecycle=RunLifecycle.COMPLETED,
                freshness=freshness,
                result_digest=digest,
                result_counts=counts,
                completed_at=completed_at,
                failure_code=None,
                current_attempt_token=None,
                progress_stage=RunProgressStage.COMPLETED,
                progress_counts=counts,
            )
            if fresh:
                ReconciliationScope.objects.filter(id=scope.id).update(current_run=run, is_dirty=False)
            return PublishedRun(run.id, freshness, digest, counts["pairs"], counts["unpaired"])

    @staticmethod
    def _members(workspace_id: WorkspaceId, revision_id: UUID) -> tuple[DatasetMembership, ...]:
        return tuple(
            DatasetMembership.objects.owned_by(workspace_id)
            .filter(dataset_revision_id=revision_id)
            .select_related("logical_transaction", "observation")
            .order_by("observation_id")
        )

    @staticmethod
    def _manifest_members(members: tuple[DatasetMembership, ...]) -> list[dict[str, str]]:
        return [
            {
                "logical_transaction_id": str(item.logical_transaction_id),
                "observation_id": str(item.observation_id),
                "observation_fingerprint": item.observation.fingerprint,
            }
            for item in members
        ]

    @staticmethod
    def _active_decisions(workspace_id: WorkspaceId, book_id: UUID) -> tuple[DecisionRevision, ...]:
        decisions = (
            Decision.objects.owned_by(workspace_id)
            .filter(book_id=book_id, current_revision__isnull=False, current_revision__superseded_by__isnull=True)
            .exclude(current_revision__action=DecisionAction.REVOKE)
            .select_related("current_revision")
            .order_by("current_revision_id")
        )
        return tuple(item.current_revision for item in decisions if item.current_revision is not None)

    @staticmethod
    def _match_record(item: RunInput) -> MatchRecord:
        observation = item.observation
        semantics = observation.raw_row.attempt.contract_revision.reference_semantics
        alias = observation.business_reference if semantics == ReferenceSemantics.TRUSTED_SHARED else None
        return MatchRecord(
            observation_id=str(observation.id),
            logical_transaction_id=str(item.logical_transaction_id),
            source_record_key=item.logical_transaction.source_record_key,
            state=CanonicalState(observation.state),
            instrument=observation.instrument,
            side=CanonicalSide(observation.side),
            currency=observation.currency,
            quantity=observation.quantity,
            executed_at=observation.executed_at_utc,
            unit_price=observation.unit_price,
            gross_amount=observation.gross_amount,
            reference_value=observation.business_reference,
            shared_reference_alias=alias,
        )

    @staticmethod
    def _decision_inputs(inputs: tuple[RunInput, ...], rows: tuple[RunDecisionInput, ...]) -> DecisionInputs:
        observations = {item.logical_transaction_id: str(item.observation_id) for item in inputs}
        manual: list[ManualLink] = []
        accepted: list[AcceptedUnmatched] = []
        rejected: list[RejectedRelationship] = []
        reserved: list[ReservedIdentity] = []
        for row in rows:
            revision = row.decision_revision
            decision_id = str(revision.decision_id)
            revision_id = str(revision.id)
            if revision.authority_kind == DecisionAuthorityKind.LINK:
                left = observations.get(revision.left_logical_id)
                right = observations.get(revision.right_logical_id)
                if left is not None and right is not None:
                    manual.append(ManualLink(decision_id, revision_id, left, right))
                elif left is not None or right is not None:
                    reserved.append(ReservedIdentity(decision_id, revision_id, left or right))
            elif revision.authority_kind == DecisionAuthorityKind.ACCEPT_UNMATCHED:
                record = observations.get(revision.record_logical_id)
                if record is not None:
                    accepted.append(AcceptedUnmatched(decision_id, revision_id, record))
            elif revision.authority_kind == DecisionAuthorityKind.REJECT_CANDIDATE:
                left = observations.get(revision.left_logical_id)
                right = observations.get(revision.right_logical_id)
                if left is not None and right is not None:
                    rejected.append(RejectedRelationship(decision_id, revision_id, left, right))
        return DecisionInputs(tuple(manual), tuple(accepted), tuple(rejected), tuple(reserved))

    @staticmethod
    def _validate_result(run: ReconciliationRun, inputs: tuple[RunInput, ...], result: EngineResult) -> None:
        expected_left = tuple(sorted(str(item.observation_id) for item in inputs if item.side == RecordSide.LEFT))
        expected_right = tuple(sorted(str(item.observation_id) for item in inputs if item.side == RecordSide.RIGHT))
        if (
            result.left_revision_id != str(run.left_revision_id)
            or result.right_revision_id != str(run.right_revision_id)
            or result.input_left_ids != expected_left
            or result.input_right_ids != expected_right
            or result.engine_version != run.engine_version
            or result.solver_version != run.solver_version
        ):
            raise RunResultMismatch("result does not match the frozen run manifest")

    def _persist_result(self, workspace_id: WorkspaceId, run: ReconciliationRun, inputs: tuple[RunInput, ...], result: EngineResult, payload: dict) -> None:
        by_observation = {str(item.observation_id): item for item in inputs}
        decision_rows = tuple(RunDecisionInput.objects.owned_by(workspace_id).filter(run=run).select_related("decision_revision"))
        manual_by_edge: dict[tuple[str, str], DecisionRevision] = {}
        accepted_by_observation: dict[str, DecisionRevision] = {}
        logical_to_observation = {item.logical_transaction_id: str(item.observation_id) for item in inputs}
        for row in decision_rows:
            revision = row.decision_revision
            if revision.authority_kind == DecisionAuthorityKind.LINK:
                left = logical_to_observation.get(revision.left_logical_id)
                right = logical_to_observation.get(revision.right_logical_id)
                if left and right:
                    manual_by_edge[(left, right)] = revision
            elif revision.authority_kind == DecisionAuthorityKind.ACCEPT_UNMATCHED:
                record = logical_to_observation.get(revision.record_logical_id)
                if record:
                    accepted_by_observation[record] = revision

        component_rows: dict[str, AssignmentComponent] = {}
        for component, component_payload in zip(result.components, payload["components"], strict=True):
            component_rows[component.component_id] = AssignmentComponent.objects.create(
                workspace_id=workspace_id.value,
                run=run,
                component_key=component.component_id,
                graph_digest=component.graph_digest,
                solver_version=component.solver_version,
                left_observation_ids=list(component.left_ids),
                right_observation_ids=list(component.right_ids),
                candidate_count=component.candidate_count,
                optimal_utility_bp=component.optimal_utility_bp,
                complete=component.complete,
                limit_reason=component.limit_reason,
                proposals=component_payload["proposals"],
            )
        component_for_edge: dict[tuple[str, str], AssignmentComponent] = {}
        for component in result.components:
            persisted = component_rows[component.component_id]
            for left in component.left_ids:
                for right in component.right_ids:
                    component_for_edge[(left, right)] = persisted
        CandidateEvidence.objects.bulk_create(
            [
                CandidateEvidence(
                    workspace_id=workspace_id.value,
                    run=run,
                    left_observation_id=item.left_id,
                    right_observation_id=item.right_id,
                    component=component_for_edge.get((item.left_id, item.right_id)),
                    blocking_reasons=list(item.blocking_reasons),
                    features=item_payload["features"],
                    contradictions=list(item.contradictions),
                    coverage_failures=list(item.coverage_failures),
                    coverage_sufficient=item.coverage_sufficient,
                    complete_computation=item.complete_computation,
                    score_bp=item.score_bp,
                    score_label=item.score_label,
                )
                for item, item_payload in zip(result.candidates, payload["candidates"], strict=True)
            ]
        )
        for pair, pair_payload in zip(result.pairs, payload["pairs"], strict=True):
            left = by_observation[pair.left_id]
            right = by_observation[pair.right_id]
            decision = manual_by_edge.get((pair.left_id, pair.right_id)) if pair.origin is PairOrigin.MANUAL else None
            reference = left.observation.business_reference if pair.origin is PairOrigin.AUTHORITATIVE_REFERENCE else None
            persisted_pair = RunPair.objects.create(
                workspace_id=workspace_id.value,
                run=run,
                left_observation=left.observation,
                right_observation=right.observation,
                left_logical=left.logical_transaction,
                right_logical=right.logical_transaction,
                origin=pair.origin.value,
                decision_revision=decision,
                reference_value=reference,
                score_bp=pair.score_bp,
                global_gap_bp=pair.global_gap_bp,
                explanation=_pair_explanation(pair.origin),
            )
            FieldComparison.objects.bulk_create(
                [
                    FieldComparison(
                        workspace_id=workspace_id.value,
                        pair=persisted_pair,
                        field=comparison.field,
                        status=comparison.status.value,
                        left_value=comparison_payload["left_value"],
                        right_value=comparison_payload["right_value"],
                        signed_difference=comparison_payload["signed_difference"],
                        allowed_difference=comparison_payload["allowed_difference"],
                        explanation=comparison.explanation,
                    )
                    for comparison, comparison_payload in zip(pair.comparisons, pair_payload["comparisons"], strict=True)
                ]
            )
        RunUnpaired.objects.bulk_create(
            [
                RunUnpaired(
                    workspace_id=workspace_id.value,
                    run=run,
                    observation=item_row.observation,
                    logical_transaction=item_row.logical_transaction,
                    side=item.side.value,
                    reason=item.reason.value,
                    explanation=item.explanation,
                    related_observation_ids=list(item.related_ids),
                )
                for item in result.unpaired
                for item_row in (by_observation[item.record_id],)
            ]
        )
        RunDiagnostic.objects.bulk_create(
            [
                RunDiagnostic(
                    workspace_id=workspace_id.value,
                    run=run,
                    decision_revision=accepted_by_observation.get(item.record_id),
                    kind=item.kind.value,
                    record_observation_id=item.record_id,
                    candidate_observation_id=item.candidate_id,
                    candidate_current_pair_id=item.candidate_current_pair_id,
                    complete=item.complete,
                    explanation=item.explanation,
                )
                for item in result.diagnostics
            ]
        )

    def _persist_decision_health(
        self,
        workspace_id: WorkspaceId,
        run: ReconciliationRun,
        inputs: tuple[RunInput, ...],
        result: EngineResult,
        *,
        is_current: bool,
        created_at: datetime,
    ) -> None:
        input_by_logical = {item.logical_transaction_id: item for item in inputs}
        diagnostics_by_record: dict[str, list] = {}
        for diagnostic in result.diagnostics:
            diagnostics_by_record.setdefault(diagnostic.record_id, []).append(diagnostic)
        matching_policy = matching_policy_from_payload(run.policy_revision.matching_policy)
        decision_rows = tuple(
            RunDecisionInput.objects.owned_by(workspace_id)
            .filter(run=run)
            .select_related("decision_revision__decision")
            .order_by("decision_revision_id")
        )
        snapshots: list[DecisionHealthSnapshot] = []
        for row in decision_rows:
            revision = row.decision_revision
            kind = DecisionAuthorityKind(revision.authority_kind)
            logical_ids = (
                (revision.record_logical_id,)
                if kind is DecisionAuthorityKind.ACCEPT_UNMATCHED
                else (revision.left_logical_id, revision.right_logical_id)
            )
            current_inputs = tuple(
                input_by_logical[logical_id]
                for logical_id in logical_ids
                if logical_id in input_by_logical
            )
            endpoints_available = len(current_inputs) == len(logical_ids)
            current_digest = (
                _reviewed_evidence_digest(tuple(item.observation for item in current_inputs))
                if current_inputs
                else None
            )
            evidence_changed = (
                endpoints_available
                and current_digest != revision.reviewed_evidence_digest
            )
            new_candidate = False
            diagnostic_complete = True
            authoritative_conflict = False
            if kind is DecisionAuthorityKind.ACCEPT_UNMATCHED and current_inputs:
                record_id = str(current_inputs[0].observation_id)
                diagnostics = diagnostics_by_record.get(record_id, [])
                new_candidate = any(
                    item.kind.value == "ACCEPTED_UNMATCHED_CANDIDATE"
                    for item in diagnostics
                )
                diagnostic_complete = not any(
                    item.kind.value == "INCOMPLETE_SEARCH" or not item.complete
                    for item in diagnostics
                )
            elif kind is DecisionAuthorityKind.REJECT_CANDIDATE and endpoints_available:
                authoritative_conflict = self._authoritative_reference_conflict(
                    current_inputs,
                    matching_policy.reference_contract.value,
                )
            projection = project_decision_health(
                decision_id=str(revision.decision_id),
                revision_id=str(revision.id),
                run_id=str(run.id),
                evidence=DecisionHealthEvidence(
                    authority_kind=kind,
                    endpoints_available=endpoints_available,
                    evidence_changed=evidence_changed,
                    new_candidate=new_candidate,
                    diagnostic_complete=diagnostic_complete,
                    comparison_changed=(
                        kind is DecisionAuthorityKind.LINK
                        and endpoints_available
                        and evidence_changed
                    ),
                    authoritative_reference_conflict=authoritative_conflict,
                ),
            )
            snapshot = DecisionHealthSnapshot.objects.create(
                workspace_id=workspace_id.value,
                run=run,
                decision_id=revision.decision_id,
                decision_revision=revision,
                health=projection.health.value,
                attention=[item.value for item in projection.attention],
                endpoints_available=endpoints_available,
                evidence_changed=evidence_changed,
                current_observation_ids=sorted(
                    str(item.observation_id) for item in current_inputs
                ),
                current_evidence_digest=current_digest,
                created_at=created_at,
            )
            snapshots.append(snapshot)
        if not is_current:
            return
        current_decision_ids = [item.decision_id for item in snapshots]
        CurrentDecisionHealth.objects.owned_by(workspace_id).filter(
            scope_id=run.scope_id
        ).exclude(decision_id__in=current_decision_ids).delete()
        for snapshot in snapshots:
            CurrentDecisionHealth.objects.update_or_create(
                workspace_id=workspace_id.value,
                scope_id=run.scope_id,
                decision_id=snapshot.decision_id,
                defaults={
                    "decision_revision_id": snapshot.decision_revision_id,
                    "run": run,
                    "snapshot": snapshot,
                    "health": snapshot.health,
                    "attention": snapshot.attention,
                    "applied_data_generation": run.data_generation,
                    "applied_resolution_generation": run.resolution_generation,
                    "updated_at": created_at,
                },
            )

    @staticmethod
    def _authoritative_reference_conflict(
        inputs: tuple[RunInput, ...],
        reference_contract: str,
    ) -> bool:
        if len(inputs) != 2:
            return False
        left = ReconciliationRunService._match_record(inputs[0])
        right = ReconciliationRunService._match_record(inputs[1])
        if reference_contract == "SHARED_MUST_AGREE":
            return (
                left.reference_value is not None
                and left.reference_value == right.reference_value
            )
        return (
            left.shared_reference_alias is not None
            and left.shared_reference_alias == right.shared_reference_alias
        )

    def _get_run(self, workspace_id: WorkspaceId, run_id: UUID) -> ReconciliationRun:
        try:
            return ReconciliationRun.objects.owned_by(workspace_id).select_related("policy_revision").get(id=run_id)
        except ReconciliationRun.DoesNotExist as error:
            raise RunUnavailable from error

    def _require_active_workspace(self, workspace_id: WorkspaceId, now: datetime, *, lock: bool) -> None:
        queryset = Workspace.objects.select_for_update() if lock else Workspace.objects.all()
        try:
            workspace = queryset.get(id=workspace_id.value)
            self.lifecycle_service.require_active(workspace, now=now)
        except (Workspace.DoesNotExist, WorkspaceUnavailable) as error:
            raise RunUnavailable from error


def _canonical_digest(value: dict) -> str:
    payload = json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _reviewed_evidence_digest(observations: tuple) -> str:
    payload = [
        {
            "logical_transaction_id": str(item.logical_transaction_id),
            "observation_id": str(item.id),
            "fingerprint": item.fingerprint,
        }
        for item in sorted(observations, key=lambda value: str(value.id))
    ]
    return _canonical_digest(
        {"version": "reviewed-evidence-v1", "observations": payload}
    )


def _pair_explanation(origin: PairOrigin) -> str:
    return {
        PairOrigin.MANUAL: "Paired by active reviewer authority.",
        PairOrigin.AUTHORITATIVE_REFERENCE: "Paired by the configured authoritative shared reference.",
        PairOrigin.WEIGHTED_GLOBAL: "Paired by the deterministic global assignment and acceptance gates.",
    }[origin]


def execute_claimed_run(work_item: WorkItem, token) -> None:
    """A `jobs.services.claim_and_execute` executor for `JobKind.RECONCILIATION_RUN`.

    Categorizes a lost fencing race as transient (worth retrying under a new
    claim) and lets every other failure propagate as permanent.
    """
    if work_item.reconciliation_run_id is None:
        raise RunUnavailable("work item has no reconciliation run target")
    try:
        ReconciliationRunService().execute_and_publish_run(
            WorkspaceId(work_item.workspace_id),
            work_item.reconciliation_run_id,
            attempt_token=str(token),
        )
    except RunStateConflict as error:
        raise TransientJobFailure(str(error)) from error
