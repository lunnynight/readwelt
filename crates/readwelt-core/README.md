# readwelt-core

`readwelt-core` is Readwelt's deterministic, CPU-only kernel.

Its public interface intentionally has two operations:

- `prepare_text`: normalize Unicode text, hash it, and return stable paragraph
  anchors with half-open byte and character offsets.
- `store_object`: atomically write immutable bytes into
  `sha256/ab/cd/<digest>` below a caller-provided object root.

CUDA and model-provider behavior do not participate in this crate's result
contract.
