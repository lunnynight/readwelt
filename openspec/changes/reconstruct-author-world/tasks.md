## 1. Domain contracts and compatibility

- [ ] 1.1 Add versioned immutable author-world item and relation contracts with evidence classes, relation kinds, decisions, limitations, typed citations, and deterministic content digests.
- [ ] 1.2 Add aggregate serialization/decoding for author-world data, including source-closure validation and compatibility for historical bundles that do not contain the optional aggregate.
- [ ] 1.3 Update canonical bundle and JSON artifact projections to expose the author-world aggregate without fabricating data for legacy runs.

## 2. Stage production and validation

- [ ] 2.1 Extend stage-3 and stage-4 response contracts so providers can return bounded world items and causal relations in addition to ordinary claims.
- [ ] 2.2 Validate evidence-class/citation compatibility, upstream claim references, interpretation identities, and article-only stage boundaries before accepting author-world material.
- [ ] 2.3 Route accepted author-world material through the existing settlement and ledger eligibility rules; retain competing interpretations and withhold rejected or unresolved conclusions from published claims.
- [ ] 2.4 Include bounded author-world material in provider request budgeting and provenance so hard serialized-token limits and continuation behavior remain deterministic.

## 3. Reader report projection

- [ ] 3.1 Add deterministic rendering for the causal chain from world condition to problem pressure to article choice, with evidence-class labels and traceable claim/anchor references.
- [ ] 3.2 Render incomplete, qualified, competing, and unavailable chains as explicit gaps or limitations instead of inferred author facts; preserve existing report sections and historical output behavior.
- [ ] 3.3 Update reader-facing documentation and the Readwelt skill guidance to describe author-world reconstruction as causal explanation, not biography or summary.

## 4. Verification and regression coverage

- [ ] 4.1 Add domain and codec tests for valid source-closed chains, invalid citation/evidence combinations, competing interpretations, deterministic digests, and historical bundle compatibility.
- [ ] 4.2 Add stage/request tests proving external context can enter only after stages 1–2 and that world relations cannot bypass anchor, upstream-claim, or settlement validation.
- [ ] 4.3 Add full Markdown projection tests for complete chains, missing causal links, qualified claims, rejected claims, and legacy bundles; assert unsettled text is withheld.
- [ ] 4.4 Run the full affected test modules, `openspec validate reconstruct-author-world --type change --strict`, and a provider-free `agent-start`/`agent-turn` smoke scenario; inspect the generated request and final report path for source closure and deterministic fallback behavior.
