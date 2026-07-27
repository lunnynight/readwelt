"""Budgeted, resumable ArticleGraph projections for the six reading stages."""

from __future__ import annotations

from collections.abc import Sequence

from readwelt.article_graph import ArticleGraphBuildResult
from readwelt.article_graph.digest import content_digest
from readwelt.domain.reading import ExternalEvidence, ReadingClaim, ReadingStage
from readwelt.provenance import (
    provider_visible_material,
    validate_provider_material_closure,
)
from readwelt.semantic.models import SemanticEvidencePacket
from readwelt.token_budget import DEFAULT_TOKEN_COUNTER

from .coverage import anchor_to_unit, coverage_manifest
from .cursors import policy_digest, validate_cursor, validate_locator
from .models import (
    ElementTraversalPosition,
    StageContext,
    StageView,
    StageViewBlockingRecord,
    StageViewCapabilityOutcome,
    StageViewContinuationCursor,
    StageViewExternalEvidence,
    StageViewExternalEvidenceOmission,
    TraversalPosition,
)
from .paging import SelectedPage, select_page, unbounded_serialized_estimate
from .selection import (
    apply_rescue_ladder,
    constrain_units_to_admitted_anchors,
    knowledge_units,
    ranked_unit_ids,
    selected_graph,
    selection_reasons,
)
from .selection import upstream_claims as select_upstream_claims
from .serialization import StageViewBudgetExceeded


class StageViewProjector:
    """Project a deterministic source traversal without making AI conclusions."""

    schema_version = "stage-view.v4"

    def project(
        self,
        build: ArticleGraphBuildResult,
        context: StageContext,
        *,
        upstream_claims: Sequence[ReadingClaim] = (),
        locator_packet: SemanticEvidencePacket | None = None,
        external_evidence: Sequence[ExternalEvidence] = (),
    ) -> StageView:
        validate_locator(build, context, locator_packet)
        unit_by_id = {unit.unit_id: unit for unit in build.unitization.units}
        range_by_id = {
            source_range.range_id: source_range for source_range in build.unitization.source_ranges
        }
        element_by_id = {
            element.element_id: element for element in build.unitization.source_elements
        }
        anchors = anchor_to_unit(build)
        current_policy_digest = policy_digest(context)

        if context.continuation is not None:
            validate_cursor(build, context, current_policy_digest)
            positions = context.continuation.frontier
            prior_visited = context.continuation.visited_unit_ids
            range_ids = context.continuation.range_frontier
            element_positions = context.continuation.element_frontier
            prior_visited_ranges = context.continuation.visited_range_ids
            prior_visited_elements = context.continuation.visited_element_ids
            eligible_unit_ids = frozenset(item.unit_id for item in positions)
            locator_ids: frozenset[str] = frozenset()
            graph_insufficient = False
        else:
            knowledge_unit_ids, graph_insufficient = knowledge_units(
                build,
                context.stage,
            )
            eligible_unit_ids = constrain_units_to_admitted_anchors(
                build,
                knowledge_unit_ids,
                context.allowed_anchor_ids,
            )
            ranked_ids, locator_ids = ranked_unit_ids(
                build,
                eligible_unit_ids,
                anchors,
                locator_packet,
            )
            ranked_ids = apply_rescue_ladder(
                build,
                ranked_ids,
                eligible_unit_ids,
                anchors,
                context,
            )
            positions = tuple(TraversalPosition(unit_id) for unit_id in ranked_ids)
            prior_visited = ()
            range_ids = tuple(
                item.range_id
                for item in sorted(
                    build.unitization.source_ranges,
                    key=lambda item: (item.start_offset, item.end_offset, item.range_id),
                )
            )
            element_positions = tuple(
                ElementTraversalPosition(item.element_id)
                for item in sorted(
                    build.unitization.source_elements,
                    key=lambda item: (
                        item.reading_order,
                        item.ordinal,
                        item.element_id,
                    ),
                )
            )
            prior_visited_ranges = ()
            prior_visited_elements = ()

        source_budget = context.token_budget

        def assemble(source_token_budget: int) -> StageView:
            page = select_page(
                positions,
                unit_by_id,
                source_token_budget,
                split_oversized_units=context.split_oversized_units,
                range_ids=range_ids,
                range_by_id=range_by_id,
                element_positions=element_positions,
                element_by_id=element_by_id,
                element_unit_ids=dict(build.source_index.element_to_units),
            )
            return self._assemble_view(
                build,
                context,
                page=page,
                eligible_unit_ids=eligible_unit_ids,
                locator_ids=locator_ids,
                locator_packet=locator_packet,
                external_evidence=external_evidence,
                graph_insufficient=graph_insufficient,
                upstream_claims=upstream_claims,
                policy_digest=current_policy_digest,
                prior_visited=prior_visited,
                prior_visited_ranges=prior_visited_ranges,
                prior_visited_elements=prior_visited_elements,
                blocking_records=(),
            )

        view = assemble(source_budget)
        if context.hard_serialized_token_budget is None:
            return view
        try:
            view.to_mapping()
        except StageViewBudgetExceeded as initial_error:
            # Use the measured envelope ratio to make a bounded number of large
            # admission steps. This avoids rebuilding and hashing the complete
            # coverage manifest once per removed source item.
            failed_budget = source_budget
            error = initial_error
            for _ in range(12):
                if failed_budget <= 0:
                    break
                scaled = int(
                    failed_budget
                    * context.hard_serialized_token_budget
                    / max(error.estimated_tokens, 1)
                    * 0.9
                )
                candidate_budget = max(0, min(failed_budget - 1, scaled))
                candidate = assemble(candidate_budget)
                try:
                    candidate.to_mapping()
                except StageViewBudgetExceeded as candidate_error:
                    failed_budget = candidate_budget
                    error = candidate_error
                    continue
                return candidate
            page = select_page(
                positions,
                unit_by_id,
                0,
                split_oversized_units=context.split_oversized_units,
                range_ids=range_ids,
                range_by_id=range_by_id,
                element_positions=element_positions,
                element_by_id=element_by_id,
                element_unit_ids=dict(build.source_index.element_to_units),
            )
            blocking_records = (
                StageViewBlockingRecord(
                    source_unit_id=(positions[0].unit_id if positions else None),
                    source_range_id=(range_ids[0] if not positions and range_ids else None),
                    source_element_id=(
                        element_positions[0].element_id
                        if not positions and not range_ids and element_positions
                        else None
                    ),
                    reason="hard_serialized_budget_below_stage_view_envelope",
                    estimated_tokens=unbounded_serialized_estimate(view),
                    budget=context.hard_serialized_token_budget,
                    detail=str(initial_error),
                ),
            )
            return self._assemble_view(
                build,
                context,
                page=page,
                eligible_unit_ids=eligible_unit_ids,
                locator_ids=locator_ids,
                locator_packet=locator_packet,
                external_evidence=external_evidence,
                graph_insufficient=graph_insufficient,
                upstream_claims=upstream_claims,
                policy_digest=current_policy_digest,
                prior_visited=prior_visited,
                prior_visited_ranges=prior_visited_ranges,
                prior_visited_elements=prior_visited_elements,
                blocking_records=blocking_records,
            )
        return view

    def _assemble_view(
        self,
        build: ArticleGraphBuildResult,
        context: StageContext,
        *,
        page: SelectedPage,
        eligible_unit_ids: frozenset[str],
        locator_ids: frozenset[str],
        locator_packet: SemanticEvidencePacket | None,
        external_evidence: Sequence[ExternalEvidence],
        graph_insufficient: bool,
        upstream_claims: Sequence[ReadingClaim],
        policy_digest: str,
        prior_visited: tuple[str, ...],
        prior_visited_ranges: tuple[str, ...],
        prior_visited_elements: tuple[str, ...],
        blocking_records: tuple[StageViewBlockingRecord, ...],
    ) -> StageView:
        selected_source_ids = {unit.unit_id for unit in page.selected}
        selected_element_ids = {element.element_id for element in page.source_elements}
        nodes, edges, claim_candidates = selected_graph(
            build,
            context.stage,
            selected_source_ids,
            selected_element_ids,
        )
        if context.stage not in {ReadingStage.MAINLINE, ReadingStage.STRUCTURE}:
            # Stage 3-6 already receive settled upstream reading claims plus the
            # same source anchors. Repeating raw graph claims there adds no new
            # locating identity and can crowd source material out of the hard
            # provider envelope.
            claim_candidates = ()
        view_claims = select_upstream_claims(context, upstream_claims)
        reasons = selection_reasons(
            page.selected,
            nodes,
            edges,
            claim_candidates,
            locator_ids,
            locator_packet,
            context,
        )
        unresolved_conflicts = tuple(
            conflict
            for conflict in build.merge_report.conflicts
            if conflict.resolution == "unresolved"
        )
        relevant_conflicts = tuple(
            conflict
            for conflict in unresolved_conflicts
            if (selected_source_ids | selected_element_ids).intersection(conflict.evidence_refs)
        )
        relevant_conflict_ids = {conflict.conflict_id for conflict in relevant_conflicts}
        unresolved_conflict_ids = tuple(
            conflict.conflict_id
            for conflict in (
                *relevant_conflicts,
                *(
                    conflict
                    for conflict in unresolved_conflicts
                    if conflict.conflict_id not in relevant_conflict_ids
                ),
            )
        )
        missing_capabilities = tuple(
            item.value for item in build.capability_report.missing_capabilities
        )
        capability_outcomes = tuple(
            StageViewCapabilityOutcome(
                backend_id=extraction.backend.backend_id,
                capability=outcome.capability.value,
                status=outcome.status.value,
                message=outcome.message,
            )
            for extraction in build.extractions
            for outcome in extraction.outcomes
        )
        visited = tuple(dict.fromkeys((*prior_visited, *page.considered_unit_ids)))
        visited_ranges = tuple(dict.fromkeys((*prior_visited_ranges, *page.considered_range_ids)))
        visited_elements = tuple(
            dict.fromkeys((*prior_visited_elements, *page.considered_element_ids))
        )
        cursor = (
            StageViewContinuationCursor.create(
                snapshot_id=build.snapshot_id,
                source_plane_schema_version=build.unitization.schema_version,
                stage=context.stage,
                policy_digest=policy_digest,
                index_digest=build.source_index.content_digest,
                frontier=page.remaining,
                visited_unit_ids=tuple(dict.fromkeys((*prior_visited, *page.completed_unit_ids))),
                range_frontier=page.remaining_range_ids,
                element_frontier=page.remaining_elements,
                visited_range_ids=tuple(
                    dict.fromkeys((*prior_visited_ranges, *page.completed_range_ids))
                ),
                visited_element_ids=tuple(
                    dict.fromkeys((*prior_visited_elements, *page.completed_element_ids))
                ),
            )
            if page.remaining or page.remaining_range_ids or page.remaining_elements
            else None
        )
        coverage = coverage_manifest(
            build,
            context,
            page,
            eligible_unit_ids,
            visited,
            visited_ranges,
            visited_elements,
            (*page.blocking_records, *blocking_records),
            completed_unit_ids=tuple(dict.fromkeys((*prior_visited, *page.completed_unit_ids))),
            completed_range_ids=tuple(
                dict.fromkeys((*prior_visited_ranges, *page.completed_range_ids))
            ),
            completed_element_ids=tuple(
                dict.fromkeys((*prior_visited_elements, *page.completed_element_ids))
            ),
        )
        coverage_complete = (
            coverage.source_complete and not coverage.omitted and coverage.stage_input_complete
        )
        locator_backend = (
            locator_packet.retrieval_backend if locator_packet is not None and locator_ids else None
        )
        fallback_backend = locator_backend if graph_insufficient else None
        admitted_external, omitted_external = _select_external_evidence(
            context.stage,
            external_evidence,
            token_budget=min(
                context.token_budget,
                (
                    context.hard_serialized_token_budget // 4
                    if context.hard_serialized_token_budget is not None
                    else context.token_budget
                ),
            ),
        )
        digest_value = {
            "schema_version": self.schema_version,
            "snapshot_id": build.snapshot_id,
            "stage": context.stage.value,
            "task_intent": context.task_intent,
            "nodes": nodes,
            "edges": edges,
            "claim_candidates": claim_candidates,
            "text_units": page.selected,
            "source_ranges": page.source_ranges,
            "source_elements": page.source_elements,
            "upstream_claims": view_claims,
            "unresolved_conflict_ids": unresolved_conflict_ids,
            "missing_capabilities": missing_capabilities,
            "capability_outcomes": capability_outcomes,
            "coverage_complete": coverage_complete,
            "coverage": coverage,
            "continuation": cursor,
            "blocking_records": (*page.blocking_records, *blocking_records),
            "token_budget": context.token_budget,
            "estimated_tokens": page.used_tokens,
            "selection_reasons": reasons,
            "locator_backend": locator_backend,
            "fallback_backend": fallback_backend,
            "graph_digest": build.graph.content_digest,
            "source_index_digest": build.source_index.content_digest,
            "provenance_ledger_digest": build.provenance_ledger.content_digest,
            "hard_serialized_token_budget": context.hard_serialized_token_budget,
            "external_evidence": admitted_external,
            "external_evidence_omissions": omitted_external,
        }
        view = StageView(
            schema_version=self.schema_version,
            snapshot_id=build.snapshot_id,
            stage=context.stage,
            task_intent=context.task_intent,
            nodes=nodes,
            edges=edges,
            text_units=page.selected,
            upstream_claims=view_claims,
            unresolved_conflict_ids=unresolved_conflict_ids,
            missing_capabilities=missing_capabilities,
            capability_outcomes=capability_outcomes,
            coverage_complete=coverage_complete,
            token_budget=context.token_budget,
            estimated_tokens=page.used_tokens,
            selection_reasons=reasons,
            locator_backend=locator_backend,
            fallback_backend=fallback_backend,
            graph_digest=build.graph.content_digest,
            source_index_digest=build.source_index.content_digest,
            provenance_ledger_digest=build.provenance_ledger.content_digest,
            content_digest=content_digest(digest_value),
            coverage=coverage,
            continuation=cursor,
            blocking_records=(*page.blocking_records, *blocking_records),
            hard_serialized_token_budget=context.hard_serialized_token_budget,
            source_ranges=page.source_ranges,
            source_elements=page.source_elements,
            external_evidence=admitted_external,
            external_evidence_omissions=omitted_external,
            claim_candidates=claim_candidates,
        )
        self._validate_provider_closure(build, view)
        return view

    @staticmethod
    def _validate_provider_closure(
        build: ArticleGraphBuildResult,
        view: StageView,
    ) -> None:
        visible_material = provider_visible_material(
            nodes=(
                (item.node_id, item.source_unit_ids, item.source_element_ids) for item in view.nodes
            ),
            edges=(
                (item.edge_id, item.source_unit_ids, item.source_element_ids) for item in view.edges
            ),
            claims=(
                (
                    item.claim_id,
                    item.evidence_unit_ids,
                    item.evidence_element_ids,
                )
                for item in view.claim_candidates
            ),
            text_items=(
                (
                    item.serialized_identity,
                    item.unit_id,
                    item.slice_id is not None,
                )
                for item in view.text_units
            ),
            source_ranges=((item.range_id, item.unit_ids) for item in view.source_ranges),
            source_elements=(
                (
                    item.serialized_identity,
                    item.element_id,
                    item.source_unit_ids,
                )
                for item in view.source_elements
            ),
        )
        closure = validate_provider_material_closure(
            visible_material,
            snapshot_id=build.snapshot_id,
            unitization=build.unitization,
            source_index=build.source_index,
            ledger_artifact=build.provenance_ledger,
            expected_graph_digest=view.graph_digest,
            expected_source_index_digest=view.source_index_digest,
            expected_ledger_digest=view.provenance_ledger_digest,
        )
        if not closure.valid:
            first_issue = closure.issues[0]
            raise ValueError(
                f"provider provenance closure failed: {first_issue.code}: {first_issue.detail}"
            )


def _select_external_evidence(
    stage: ReadingStage,
    evidence: Sequence[ExternalEvidence],
    *,
    token_budget: int,
) -> tuple[
    tuple[StageViewExternalEvidence, ...],
    tuple[StageViewExternalEvidenceOmission, ...],
]:
    """Apply the fixed article-only boundary before provider serialization."""

    if stage in {ReadingStage.MAINLINE, ReadingStage.STRUCTURE}:
        return (
            (),
            tuple(
                StageViewExternalEvidenceOmission(
                    evidence_id=item.evidence_id,
                    reason="article_only_stage",
                    detail=f"{stage.value} permits article evidence only",
                )
                for item in evidence
            ),
        )
    admitted: list[StageViewExternalEvidence] = []
    omitted: list[StageViewExternalEvidenceOmission] = []
    used = 0
    for item in evidence:
        candidate = StageViewExternalEvidence(
            evidence_id=item.evidence_id,
            content=item.content,
            selection_reason="available_external_evidence_selected_by_stage_policy",
            provenance=item.provenance,
            stage_policy=stage.value,
        )
        cost = DEFAULT_TOKEN_COUNTER.count_json(candidate).tokens
        if used + cost <= token_budget:
            admitted.append(candidate)
            used += cost
        else:
            omitted.append(
                StageViewExternalEvidenceOmission(
                    evidence_id=item.evidence_id,
                    reason="stage_view_external_evidence_budget",
                    detail=f"required:{cost};remaining:{max(0, token_budget - used)}",
                )
            )
    return tuple(admitted), tuple(omitted)
