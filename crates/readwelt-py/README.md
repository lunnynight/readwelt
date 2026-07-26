# readwelt-py

PyO3 adapter for the `readwelt-core` module. The extension module is named
`readwelt._core` when packaged with maturin.

The Python seam exposes only `prepare(text)` and
`put_object(object_root, data)`, plus immutable result types. All normalization,
anchoring, hashing, object layout, integrity checking, and atomic-write behavior
remain inside the Rust implementation.
