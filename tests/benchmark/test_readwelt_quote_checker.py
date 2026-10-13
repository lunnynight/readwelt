from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CHECKER = ROOT / "evals" / "readwelt" / "check_quotes.py"


def test_quote_checker_reports_literal_match_without_claiming_semantic_validity(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source.md"
    report = tmp_path / "report.md"
    source.write_text("原文写道：阶级斗争的历史。", encoding="utf-8")
    report.write_text("引用：“阶级斗争的历史。”", encoding="utf-8")

    result = subprocess.run(
        [sys.executable, str(CHECKER), str(source), str(report)],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    assert "LITERAL_MATCH" in result.stdout
    assert "semantic" not in result.stdout.lower()


def test_quote_checker_fails_when_explicit_quote_has_no_literal_match(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source.md"
    report = tmp_path / "report.md"
    source.write_text("原文没有这个句子。", encoding="utf-8")
    report.write_text("引用：“不存在的原文。”", encoding="utf-8")

    result = subprocess.run(
        [sys.executable, str(CHECKER), str(source), str(report)],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 1
    assert "NO_LITERAL_MATCH" in result.stdout
