"""Pinned lineage for open-source patterns that contribute to build artifacts."""

from __future__ import annotations

from dataclasses import dataclass

from readwelt.article_graph.digest import content_digest

ALGORITHM_LINEAGE_SCHEMA_VERSION = "algorithm-lineage.v1"


@dataclass(frozen=True, slots=True)
class AlgorithmLineageRecord:
    algorithm_id: str
    source_repository: str
    source_revision: str
    license_name: str
    license_decision: str
    local_adapter_version: str
    capability_scope: tuple[str, ...]
    excluded_product_behavior: tuple[str, ...]
    adoption_kind: str = "adapted_pattern"
    dependency_versions: tuple[str, ...] = ()
    model_artifact_digest: str | None = None
    model_artifact_revisions: tuple[str, ...] = ()
    model_license_decisions: tuple[str, ...] = ()
    runtime_configuration: tuple[str, ...] = ()
    schema_version: str = ALGORITHM_LINEAGE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        required = (
            self.algorithm_id,
            self.source_repository,
            self.source_revision,
            self.license_name,
            self.license_decision,
            self.local_adapter_version,
            self.adoption_kind,
        )
        if any(not value.strip() for value in required):
            raise ValueError("algorithm lineage identity and license fields are required")
        if self.schema_version != ALGORITHM_LINEAGE_SCHEMA_VERSION:
            raise ValueError(f"unsupported algorithm lineage schema: {self.schema_version}")
        if not self.source_repository.startswith("https://"):
            raise ValueError("algorithm lineage repository must be an HTTPS URL")
        if not self.capability_scope or not self.excluded_product_behavior:
            raise ValueError("algorithm lineage requires capability and exclusion scopes")
        if self.model_artifact_digest is not None and not self.model_artifact_digest.startswith(
            "sha256:"
        ):
            raise ValueError("model artifact digest must be sha256")

    @property
    def content_digest(self) -> str:
        return content_digest(self.to_payload())

    def to_payload(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "schema_version": self.schema_version,
            "algorithm_id": self.algorithm_id,
            "source_repository": self.source_repository,
            "source_revision": self.source_revision,
            "license_name": self.license_name,
            "license_decision": self.license_decision,
            "local_adapter_version": self.local_adapter_version,
            "capability_scope": self.capability_scope,
            "excluded_product_behavior": self.excluded_product_behavior,
            "adoption_kind": self.adoption_kind,
        }
        if self.dependency_versions:
            payload["dependency_versions"] = self.dependency_versions
        if self.model_artifact_digest is not None:
            payload["model_artifact_digest"] = self.model_artifact_digest
        if self.model_artifact_revisions:
            payload["model_artifact_revisions"] = self.model_artifact_revisions
        if self.model_license_decisions:
            payload["model_license_decisions"] = self.model_license_decisions
        if self.runtime_configuration:
            payload["runtime_configuration"] = self.runtime_configuration
        return payload


_BUILD_PATTERN_LINEAGE = (
    AlgorithmLineageRecord(
        algorithm_id="docling-core.reference-provenance-pattern",
        source_repository="https://github.com/docling-project/docling-core",
        source_revision="129811fe4959969e4cc91b958c7fc9ba884d288f",
        license_name="MIT",
        license_decision="adapt interface patterns; no runtime dependency",
        local_adapter_version="readwelt.source-plane.v1",
        capability_scope=(
            "typed source references",
            "page and bounding-box provenance fields",
            "ordered hierarchical source elements",
        ),
        excluded_product_behavior=(
            "DoclingDocument ontology",
            "Docling chunking runtime",
            "parser fallback without a measured gate",
        ),
    ),
    AlgorithmLineageRecord(
        algorithm_id="docling-graph.provenance-merge-pattern",
        source_repository="https://github.com/docling-project/docling-graph",
        source_revision="4274df4741b91f565539292eae8c4128b499dcbe",
        license_name="MIT",
        license_decision="adapt fail-empty provenance and merge patterns",
        local_adapter_version="readwelt.canonicalizer.v1",
        capability_scope=(
            "fail-empty source binding",
            "merge decisions and conflicts",
            "schema-gated validation",
        ),
        excluded_product_behavior=(
            "Pydantic product graph",
            "NetworkX runtime",
            "Docling Graph ontology",
        ),
    ),
    AlgorithmLineageRecord(
        algorithm_id="graphrag.textunit-reverse-map",
        source_repository="https://github.com/microsoft/graphrag",
        source_revision="14a00ad88fc33cf2b52f4f113f25807556f8e25e",
        license_name="MIT",
        license_decision="adapt deterministic reverse-map algorithm",
        local_adapter_version="readwelt.source-index.v1",
        capability_scope=(
            "knowledge-to-source-unit projection",
            "source-unit-to-knowledge reverse projection",
        ),
        excluded_product_behavior=(
            "community summarization",
            "global search",
            "LLM graph extraction",
        ),
    ),
    AlgorithmLineageRecord(
        algorithm_id="kag.explicit-source-chunk-links",
        source_repository="https://github.com/OpenSPG/KAG",
        source_revision="fdab15b3929d2ee40dfcdd388f90233096a6afc9",
        license_name="Apache-2.0",
        license_decision="adapt explicit knowledge-to-source relationship shape",
        local_adapter_version="readwelt.source-index.v1",
        capability_scope=(
            "explicit source grounding",
            "bidirectional source lookup",
        ),
        excluded_product_behavior=(
            "KAG project runtime",
            "SchemaClient",
            "reasoner and SubGraph runtime",
        ),
    ),
    AlgorithmLineageRecord(
        algorithm_id="prov.independent-lineage-model",
        source_repository="https://github.com/trungdong/prov",
        source_revision="421ade5794d696d64af77718ad20dcbd723596e0",
        license_name="MIT",
        license_decision="adapt independent entity/activity/agent lineage pattern",
        local_adapter_version="readwelt.provenance-ledger.v1",
        capability_scope=(
            "independent append-only provenance records",
            "typed inputs outputs and source references",
        ),
        excluded_product_behavior=(
            "PROV ontology as ArticleGraph semantics",
            "prov package runtime",
            "automatic RDF export",
        ),
    ),
    AlgorithmLineageRecord(
        algorithm_id="openlineage.versioned-event-envelope",
        source_repository="https://github.com/OpenLineage/OpenLineage",
        source_revision="2ab809038344cb07fe504be1783ee2341665a084",
        license_name="Apache-2.0",
        license_decision="adapt versioned event-envelope conventions",
        local_adapter_version="readwelt.provenance-event.v1",
        capability_scope=(
            "event timestamp and producer identity",
            "schema version and extensible payload",
            "replayable artifact lineage",
        ),
        excluded_product_behavior=(
            "data-engineering job and dataset ontology",
            "OpenLineage collector runtime",
            "Marquez service",
        ),
    ),
)

_XBERG_LINEAGE = AlgorithmLineageRecord(
    algorithm_id="xberg.primary-ingestion-adapter",
    source_repository="https://github.com/xberg-io/xberg",
    source_revision="release:1.0.0rc38",
    license_name="MIT",
    license_decision="adopt pinned package behind a narrow ingestion adapter",
    local_adapter_version="readwelt.xberg-adapter.v1",
    capability_scope=(
        "primary normalized-content extraction",
        "native structure projection when exposed",
    ),
    excluded_product_behavior=(
        "unmeasured structure claims",
        "implicit OCR claims",
        "Xberg-native product ontology",
    ),
    adoption_kind="adopted_backend",
)

_DOCLING_LINEAGE = AlgorithmLineageRecord(
    algorithm_id="docling.pdf-ocr-structural-fallback",
    source_repository="https://github.com/docling-project/docling",
    source_revision="release:2.114.0",
    license_name="MIT",
    license_decision=(
        "adopt pinned optional PDF/OCR converter; model licenses are recorded "
        "separately and remote model acquisition is forbidden at runtime"
    ),
    local_adapter_version="readwelt.docling-structural-fallback.v1",
    capability_scope=(
        "PDF layout and reading-order projection",
        "table, figure, caption, page, and geometry projection",
        "local RapidOCR text recovery for image-only PDF",
        "DoclingDocument to complete Source Plane projection",
    ),
    excluded_product_behavior=(
        "implicit model download",
        "remote services",
        "external plugins",
        "DoclingDocument as the Readwelt product graph",
        "six-stage conclusions",
    ),
    adoption_kind="adopted_backend",
    dependency_versions=(
        "docling==2.114.0",
        "docling-core==2.87.1",
        "docling-ibm-models==3.13.3",
        "rapidocr==3.9.2",
    ),
    model_artifact_digest=(
        "sha256:117ce0d7c9486c4bb9b53a11b5fe5f2035bf192997cf4915b5cb99f97389a202"
    ),
    model_artifact_revisions=(
        "docling-project/docling-layout-heron@8f39ad3c0b4c58e9c2d2c84a38465abf757272d8",
        "docling-project/docling-models@fc0f2d45e2218ea24bce5045f58a389aed16dc23",
        "RapidAI/RapidOCR@v3.9.0",
    ),
    model_license_decisions=(
        "docling-layout-heron:Apache-2.0:adopt",
        "docling-models:CDLA-Permissive-2.0:adopt",
        "RapidOCR:Apache-2.0:adopt",
    ),
    runtime_configuration=(
        "models=pre-downloaded-local-only",
        "ocr_backend=onnxruntime",
        "remote_services=false",
        "external_plugins=false",
    ),
)


def algorithm_lineage_for_build(
    parse_findings: tuple[str, ...],
) -> tuple[AlgorithmLineageRecord, ...]:
    """Return only records that contribute to this build's artifact lineage."""

    xberg_used = any(finding.startswith("ingested_by_xberg_") for finding in parse_findings)
    docling_used = any(
        finding == "docling_fallback_backend:production" for finding in parse_findings
    )
    return (
        *((_XBERG_LINEAGE,) if xberg_used else ()),
        *((_DOCLING_LINEAGE,) if docling_used else ()),
        *_BUILD_PATTERN_LINEAGE,
    )
