"""Pure transcript linter — flags contract violations render.split relies on."""
from __future__ import annotations
import re

# Accepts speaker/moderator headers, including the kickoff "moderator·킥오프" form.
_HEADER_RE = re.compile(r"^##\s*\[[^\]]+\]\s*—\s*TURN\s+\d+\s*\((speaker|moderator)[^)]*\)\s*$")
_SECTION_RE = re.compile(r"^##\s*\[")
_SUMMARY_RE = re.compile(r"^##\s*\[SUMMARY\]\s*$", re.M)
_FINAL_RE = re.compile(r"^##\s*\[FINAL\][^\n]*$", re.M)


def lint_transcript(text: str) -> list[str]:
    warnings: list[str] = []
    for line in text.splitlines():
        if not _SECTION_RE.match(line):
            continue
        if line.strip().startswith(("## [SUMMARY]", "## [FINAL]", "## [DECISIONS]",
                                    "## [사용자 지침]", "## [결정 요청]", "## [사용자 결정]")):
            continue
        if not _HEADER_RE.match(line.strip()):
            warnings.append(f"형식 오류 헤더: {line.strip()[:80]}")

    finals = _FINAL_RE.findall(text)
    if len(finals) > 1:
        warnings.append("FINAL 블록이 여러 개입니다.")

    fm = _FINAL_RE.search(text)
    if fm and not _SUMMARY_RE.search(text[:fm.start()]):
        warnings.append("FINAL은 있으나 그 앞에 SUMMARY 블록이 없습니다.")
    return warnings
