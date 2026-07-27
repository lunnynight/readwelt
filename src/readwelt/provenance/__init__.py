"""Provenance ledger and source navigation projections."""

from . import closure_models as _closure_models
from .adoption import (
    ALGORITHM_LINEAGE_SCHEMA_VERSION,
    AlgorithmLineageRecord,
    algorithm_lineage_for_build,
)
from .closure import (
    final_provider_visible_material,
    provider_visible_material,
    validate_provider_material_closure,
)
from .ledger import ProvenanceLedger
from .models import (
    GENESIS_DIGEST,
    PROVENANCE_SCHEMA_VERSION,
    ChainVerification,
    ProducerIdentity,
    ProvenanceEvent,
    ProvenanceEventType,
    ProvenanceLedgerArtifact,
)
from .source_index import (
    SOURCE_INDEX_SCHEMA_VERSION,
    SourceIndex,
    SourceIndexClosure,
    SourceIndexDiagnostic,
    SourceLookup,
    SourceNeighborhood,
    UnitKnowledge,
)

PROVENANCE_CLOSURE_SCHEMA_VERSION = _closure_models.PROVENANCE_CLOSURE_SCHEMA_VERSION
ProvenanceClosureIssue = _closure_models.ProvenanceClosureIssue
ProvenanceClosureReport = _closure_models.ProvenanceClosureReport
ProviderMaterialDisposition = _closure_models.ProviderMaterialDisposition
ProviderMaterialKind = _closure_models.ProviderMaterialKind
ProviderMaterialResolution = _closure_models.ProviderMaterialResolution
ProviderVisibleMaterial = _closure_models.ProviderVisibleMaterial
SourceRecordKind = _closure_models.SourceRecordKind
TypedSourceReference = _closure_models.TypedSourceReference

__all__ = [
    "ALGORITHM_LINEAGE_SCHEMA_VERSION",
    "GENESIS_DIGEST",
    "PROVENANCE_SCHEMA_VERSION",
    "PROVENANCE_CLOSURE_SCHEMA_VERSION",
    "SOURCE_INDEX_SCHEMA_VERSION",
    "ChainVerification",
    "AlgorithmLineageRecord",
    "ProducerIdentity",
    "ProviderMaterialDisposition",
    "ProviderMaterialKind",
    "ProviderMaterialResolution",
    "ProviderVisibleMaterial",
    "ProvenanceEvent",
    "ProvenanceEventType",
    "ProvenanceClosureIssue",
    "ProvenanceClosureReport",
    "ProvenanceLedger",
    "ProvenanceLedgerArtifact",
    "SourceIndex",
    "SourceIndexClosure",
    "SourceIndexDiagnostic",
    "SourceLookup",
    "SourceNeighborhood",
    "SourceRecordKind",
    "TypedSourceReference",
    "UnitKnowledge",
    "algorithm_lineage_for_build",
    "final_provider_visible_material",
    "provider_visible_material",
    "validate_provider_material_closure",
]
