"""CLI for freezing the D1 real-document evaluation manifest."""

from __future__ import annotations

import argparse
from pathlib import Path

from .manifest import write_preregistration


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("corpus_root", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    manifest, preregistration = write_preregistration(args.corpus_root, args.output)
    print(manifest)
    print(preregistration)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
