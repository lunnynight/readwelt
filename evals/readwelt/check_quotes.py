"""Mechanically compare explicitly quoted spans with a supplied source.

This checks literal overlap only. A match does not establish speaker attribution,
claim meaning, or entailment; a miss may result from punctuation/translation.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

_QUOTE = re.compile(r'[“「](.+?)[”」]', re.DOTALL)


def normalize(text: str) -> str:
    return "".join(text.split()).replace("，", ",").replace("。", ".")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("report", type=Path)
    args = parser.parse_args()
    source = normalize(args.source.read_text(encoding="utf-8"))
    report = args.report.read_text(encoding="utf-8")
    quotes = _QUOTE.findall(report)
    if not quotes:
        print("NO_EXPLICIT_QUOTES_FOUND")
        return 2
    misses = 0
    for index, quote in enumerate(quotes, start=1):
        matched = normalize(quote) in source
        status = "LITERAL_MATCH" if matched else "NO_LITERAL_MATCH"
        print(f"{index}\t{status}\t{quote[:100]}")
        misses += not matched
    print(f"SUMMARY\tquotes={len(quotes)}\tliteral_matches={len(quotes) - misses}\tmisses={misses}")
    return 1 if misses else 0


if __name__ == "__main__":
    sys.exit(main())
