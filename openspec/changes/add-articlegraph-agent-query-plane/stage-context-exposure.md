# Six-Stage Context Exposure Migration Measurement

Measured on 2026-07-29 with the deterministic two-paragraph Chinese integration
fixture used by `test_read_executes_and_persists_the_full_pipeline`. The run used
the same graph snapshot, stage policies, and provider request schema for all six
stages. No embedding backend or graph database participated.

| Stage | Eager StageView tokens | Query evidence tokens | Logical primary delta | Retained adapter tokens | Actual inline delta |
|---|---:|---:|---:|---:|---:|
| Mainline | 47 | 32 | -15 | 47 | 0 |
| Structure | 47 | 32 | -15 | 47 | 0 |
| Decompression | 47 | 32 | -15 | 47 | 0 |
| Author model | 47 | 32 | -15 | 47 | 0 |
| Boundaries | 47 | 32 | -15 | 47 | 0 |
| Transfer | 47 | 32 | -15 | 47 | 0 |

`Query evidence tokens` is the evidence volume settled by the persisted Query
Plane receipt. `Eager StageView tokens` is the old stage surface and
`Retained adapter tokens` is the rollback-compatible StageView still carried by
the current provider request. Consequently, the logical primary evidence is 15
estimated tokens smaller in this fixture, but actual inline savings are **zero**
until the compatibility adapter is removed from provider envelopes.

This is a migration/accounting check, not a product-quality result. The fixture
is too small and homogeneous to support claims about comprehension, location
accuracy, or production token savings. Those claims remain gated by the
preregistered real-document evaluation in tasks 5.1-5.5 and the release gates.
