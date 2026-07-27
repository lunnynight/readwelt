# ArticleGraph Open-source Adoption Record

Recorded: 2026-07-27
Change: `harden-article-graph-source-plane`

## Gate

Readwelt uses this decision order:

1. verify the product requirement and source-completeness invariant;
2. inspect the real open-source interface and pinned source;
3. verify code, model, and data licenses separately;
4. measure the required capability on Readwelt documents;
5. buy or adapt through a thin boundary;
6. build only the missing Readwelt-specific contract.

Adopting an algorithm or interface does not adopt the source project's product ontology, agent workflow, LLM pipeline, storage system, or global search behavior.

## Pinned local audit sources

| Project | Pinned revision/version | Code license evidence | Decision | Narrow reuse boundary |
|---|---|---|---|---|
| Xberg | `1.0.0rc38`; wheel hash pinned in `uv.lock` | installed package metadata: MIT | Buy, primary ingestion | `ExtractInput`, extraction, normalized content, and format-specific nodes/elements/pages actually exposed by probes |
| Docling | package `2.114.0`; complete converter runtime | PyPI package metadata and upstream root `LICENSE`: MIT | Optional production PDF/scan structural fallback | `DocumentConverter`, local-only `PdfPipelineOptions`, OCR, table/layout conversion, and `DoclingDocument` projection |
| Docling Core | `129811fe4959969e4cc91b958c7fc9ba884d288f` | root `LICENSE`: MIT | Data-model dependency/pattern source only; not a PDF/OCR parser | `RefItem`, JSON Pointer references, page/bbox/charspan provenance, hierarchical structure, ordered item iteration |
| Docling Graph | `4274df4741b91f565539292eae8c4128b499dcbe` | root `LICENSE`: MIT | Adapt patterns, do not install main runtime | provenance ledger, fail-empty binding, schema gate, rekey/collision/conflict/validation merge flow |
| Microsoft GraphRAG | `14a00ad88fc33cf2b52f4f113f25807556f8e25e` | root `LICENSE`: MIT | Adapt algorithms only | TextUnit reverse maps and budgeted mixed-context assembly |
| OpenSPG/KAG | `fdab15b3929d2ee40dfcdd388f90233096a6afc9` | root `LICENSE`: Apache-2.0 | Adapt contract shape only | `ExtractorABC`, Chunk→SubGraph shape, explicit knowledge `source`→chunk relationship |
| HanLP | `ddb1299bddff079e447af52ec12549c50636bfa8` | root `LICENSE`: Apache-2.0; model licenses vary | Bake-off candidate | thin parse/MTL adapter for CWS/POS/NER/DEP/SRL with exact offset recovery |
| LTP | `1f042d48b0a785ff7875b2e63c1439ef8c78995c` | bundled license requires payment for commercial and institutional use | Authorization-limited control | one-call CWS/POS/NER/SRL/DEP/SDP pipeline only when authorization permits |
| DeepKE | `77083bf1d9ccc386c02d5b7643f4f4d2251f4c30` | root `LICENSE`: MIT; model licenses separate | Reject default runtime; reference only | `RecordSchema` and schema-constrained output conventions |
| Splink | `04189f570f3e4ae08322f016e23349b137f6f5a6` | root `LICENSE`: MIT | Optional later experiment | blocking/comparison/m-u/Bayes-factor mention-pair scoring, never canonical merge ownership |
| prov | `421ade5794d696d64af77718ad20dcbd723596e0` | root `LICENSE`: MIT | Optional interoperability export | internal ledger → PROV document projection |
| OpenLineage | `2ab809038344cb07fe504be1783ee2341665a084` | root `LICENSE`: Apache-2.0 | Adapt envelope only | event time, producer, schema URL, and facet-extension conventions |

## Candidates requiring a pin before execution

| Project | Current state | Gate |
|---|---|---|
| PaddleNLP | resolver selected `2.6.1` with PaddlePaddle `3.3.1`; no source/model revision | Isolated install/import timed out twice; no runtime adoption until the exact source/model revision, model license, and executable benchmark are recorded |
| Stanza | package `1.14.0`; model `stanfordnlp/stanza-zh-hans@v1.14.0` | Admitted as an optional production linguistic adapter after the focused execution and grounding gate; remains non-default and degrades explicitly when its local model is unavailable |

An unpinned candidate may remain in the bake-off plan, but it cannot be installed or selected as a default backend.

## Confirmed interface evidence

## Measured Xberg format decision

The reproducible probe at
`reports/xberg-capability-probe-2026-07-27.json` used Xberg `1.0.0rc38` and
recorded:

| Case | Extracted characters | Exposed nodes/elements/pages/relationships | Decision |
|---|---:|---:|---|
| Plain TXT | 43 | 0 | content-only Source Plane input |
| HTML structure probe | 46 | 0 | content-only Source Plane input |
| Reconstructed real EPUB corpus | 99,415 | 0 | content plus Readwelt EPUB outline; structural fallback candidate |
| Native PDF (`aiwen.pdf`) | 122,120 | 0 | content plus structural fallback candidate |
| PDF empty-extraction control | 0 | 0 | parser/OCR fallback required |
| Dedicated scanned-PDF manifest entry | 0 | 0 | real image-only fixture measured; original bytes remain addressable and optional OCR fallback is eligible |

The probe content digest is
`sha256:963cf65da2fc45f2e5ab000fe464689c84c5b3895a5fefc6db61d8e2bf146d7a`.

**Decision:** the complete `docling==2.114.0` package—not `docling-core`—is the
optional production structure/layout/OCR fallback when Xberg exposes no PDF
structure or returns empty PDF content. `docling-core` supplies the document
model consumed by the converter, but it does not provide PDF/OCR conversion.
Xberg remains the primary ingestion authority; fallback records retain separate
backend provenance and are never silently presented as Xberg output.

The scanned-PDF entry now points to the real image-only acceptance fixture.
Xberg returned no text or structure for that file. Readwelt preserves its
original bytes as a content-addressed `source_document` root, but that source
reachability is not reported as OCR or normalized-text coverage.

### Xberg

Readwelt currently pins Xberg as its primary ingestion dependency. The measured
cases above show content extraction but no exposed structure. ArticleGraph
therefore consumes Xberg as one input source while the Readwelt Source Plane
owns stable source identity, exact ranges, preserved elements, capability
diagnostics, and traversal.

### Docling

Docling's official API places PDF/OCR conversion in
`docling.document_converter.DocumentConverter`, configured with
`PdfPipelineOptions`; `docling-core` defines `DoclingDocument` and its item and
provenance models. Readwelt therefore installs the full package only through the
`structural` extra and projects the resulting `DoclingDocument` into the
existing Source Plane rather than adopting another graph ontology.

The production seam is invoked only for `.pdf` inputs when Xberg has no
structure or empty content. It pins package version `2.114.0`, disables remote
services and external plugins, requires a pre-downloaded local model directory
through `READWELT_DOCLING_ARTIFACTS_PATH`, and uses the local RapidOCR backend
option. With no model directory it returns an explicit blocked capability
finding and does not fall back to automatic model downloads. Original PDF bytes
remain the Source Plane root in both success and failure paths.

The reproducible real-fixture probe is
`reports/docling-structural-fallback-probe-2026-07-27.json`. The official CLI
downloaded layout, TableFormer, and RapidOCR assets into the ignored
`.research-inputs/docling-artifacts` directory: 45 files, 633,340,087 bytes,
with tree digest
`sha256:117ce0d7c9486c4bb9b53a11b5fe5f2035bf192997cf4915b5cb99f97389a202`.
With those explicit local assets, the 50-page native PDF converted successfully
to 143,851 text characters, 865 structure records, and 841 page/geometry
records. The scanned one-page fixture has zero characters in its native PDF
text layer; RapidOCR recovered 1,619 characters plus 40 structure records, 33
of which carry page geometry. Complete traversal requests groups, picture
descendants, and every Docling content layer; the resulting Source Plane
records retain `content_layer` provenance. Both fixtures had zero anonymous
records and zero unresolved parent, child, or structural-relation references.
Both conversions completed with remote services and external plugins disabled.
The report digest is
`sha256:315bfd493bf7a6674bee2e0f1fd766c450e9536e1bdbc98841a8f9383d557399`;
the digest excludes only measured elapsed time.

Every production Docling invocation now contributes an immutable
`docling.pdf-ocr-structural-fallback` adoption event to the ArticleGraph build
ledger. The event records the adapter version, exact Docling dependency
versions, the local model-tree digest, resolved layout/TableFormer/RapidOCR
revisions, separate model-license decisions, the OCR backend, and the
remote-service/plugin exclusions. Injected test doubles are identified
separately and do not claim the production model lineage.
The offline configuration follows the official
[advanced options](https://docling-project.github.io/docling/usage/advanced_options/)
and [pipeline options](https://docling-project.github.io/docling/reference/pipeline_options/)
contracts.

Docling Graph remains useful for provenance and merge behavior, but its
Pydantic/NetworkX product graph is not the Readwelt ArticleGraph contract.

### GraphRAG and KAG

GraphRAG's `create_final_text_units` builds TextUnit→entity/relationship reverse
maps. KAG's extractors build `SubGraph` objects and explicit entity
`source`→chunk edges. Readwelt adapted those narrow patterns into its own
bidirectional and source-first SourceIndex without adding either runtime.

### Chinese linguistic extraction

HanLP exposes local multi-task and client parsing surfaces. LTP exposes a pipeline for CWS, POS, NER, SRL, DEP, and SDP but its bundled license restricts commercial/institutional use. DeepKE is a collection of task routes and Hydra examples rather than a stable unified Readwelt extractor; OneKE also conflicts with the default goal of reducing general-model cost.

The reproducible candidate manifest is
`benchmarks/articlegraph/linguistic_backend_manifest.json`. The only neural
candidate that executed a model was Stanza `1.14.0` with the
`stanfordnlp/stanza-zh-hans@v1.14.0` model. On three Chinese source units it
covered all three must-hit units, resolved all 38 grounding references to exact
source offsets, and recorded 317.76 ms latency, 182.53 characters/second, and
663,233 bytes of Python-traced peak memory. The full focused record is
`reports/linguistic-backend-bakeoff-2026-07-27.json`.

This result admits Stanza as an optional production linguistic adapter, pinned
as the `linguistic` extra. The production adapter is the same thin adapter used
by the measured bake-off, requires an explicitly supplied pre-downloaded model
directory, records the package/model revisions in its descriptor, performs no
implicit network download, and reports unsupported SRL/coreference capability
outcomes rather than inventing them. It does not become the default and does
not control source reachability. The result still does not prove long-document
locating quality, representative NER/DEP accuracy, cold-start cost, or
production memory; those limits remain explicit.

HanLP `2.1.3` imported successfully in isolation, but its upstream README
restricts the Chinese pretrained models to research and teaching, so no model
was downloaded or represented as a product-compatible run. LTP `4.2.14`
imported successfully, but was not model-executed because the audited upstream
terms require commercial/institutional authorization. PaddleNLP/PaddlePaddle
resolved to 73 transitive packages; isolated install/import exceeded 180
seconds after an earlier 60-second timeout, so it remains explicitly blocked
rather than silently adopted. DeepKE remains a `RecordSchema` and output-shape
reference only.

## Build-only Readwelt contracts

The following are product-specific and remain Readwelt-owned:

- exact complete Source Plane and coverage manifest;
- Xberg/optional-backend projection into one stable source contract;
- source-first range/ordinal/structure/lexical navigation;
- immutable extraction and canonicalization contracts;
- typed provenance closure;
- StageView continuation, rescue traversal, omission accounting, and hard provider-bound budgets;
- AI boundary between locating candidates and six-stage conclusions;
- `CompletionPlan` and Completion Engine, in a later change.

The resulting implemented chain and its current acceptance limits are described
in [ArticleGraph Source Plane Architecture](articlegraph-source-plane-baseline.md).
