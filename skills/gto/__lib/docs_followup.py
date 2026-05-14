from __future__ import annotations

from pathlib import Path

from ..models import Finding, EvidenceRef


def detect_docs_followup(root: Path, findings: list[Finding]) -> list[Finding]:
    """Add documentation follow-up findings when code changes lack doc updates.

    Only triggers when:
    - There are quality/test/security findings with file references
    - The referenced file lacks corresponding documentation updates
    """
    doc_findings: list[Finding] = []
    seen_files: set[str] = set()

    for f in findings:
        if not f.file or f.file in seen_files:
            continue
        if f.domain not in ("quality", "tests", "security"):
            continue
        seen_files.add(f.file)

        filepath = root / f.file
        if not filepath.exists():
            continue

        # Check if a nearby doc file exists (convention: same dir, README or docs/)
        doc_candidates = [
            filepath.parent / "README.md",
            filepath.parent / "docs" / f"{filepath.stem}.md",
        ]
        has_doc = any(d.exists() for d in doc_candidates)

        if not has_doc and f.severity in ("critical", "high"):
            doc_findings.append(
                Finding(
                    id=f"DOC-FOLLOWUP-{len(doc_findings) + 1:03d}",
                    title=f"Missing docs for {f.file}",
                    description=f"High-severity finding in {f.file} but no documentation found nearby.",
                    source_type="detector",
                    source_name="docs_followup",
                    domain="docs",
                    gap_type="missingdocs",
                    severity="low",
                    evidence_level="derived",
                    action="prevent",
                    priority="low",
                    file=f.file,
                    evidence=[EvidenceRef(kind="path", value=str(filepath))],
                )
            )

    return doc_findings
