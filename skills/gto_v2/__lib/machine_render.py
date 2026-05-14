from __future__ import annotations

from dataclasses import dataclass

from ..models import Finding

# Domain definitions matching RNS render.py DOMAIN_MAP
DOMAIN_MAP: dict[str, tuple[str, str]] = {
    "quality": ("🔧", "QUALITY"),
    "code_quality": ("🔧", "QUALITY"),
    "tests": ("🧪", "TESTS"),
    "testing": ("🧪", "TESTS"),
    "docs": ("📄", "DOCS"),
    "documentation": ("📄", "DOCS"),
    "security": ("🔒", "SECURITY"),
    "performance": ("⚡", "PERFORMANCE"),
    "git": ("🐙", "GIT"),
    "deps": ("📦", "DEPS"),
    "dependencies": ("📦", "DEPS"),
    "session": ("💬", "SESSION"),
    "other": ("📌", "OTHER"),
}

ACTION_ORDER = ("recover", "prevent", "realize")
ACTION_LABELS: dict[str, str] = {
    "recover": "Recovery",
    "prevent": "Preserve",
    "realize": "Future",
}
PRIORITY_ORDER = ("critical", "high", "medium", "low")

PRIORITY_DOT_MAP: dict[str, str] = {
    "critical": "🔴",
    "high": "🟠",
    "medium": "🟡",
    "low": "🔵",
}


def _subletter(idx: int) -> str:
    """Return Excel-style column label for 1-based index: 1→a, 26→z, 27→aa."""
    result: list[str] = []
    n = idx - 1
    while True:
        n, rem = divmod(n, 26)
        result.append(chr(ord("a") + rem))
        if n == 0:
            break
    return "".join(reversed(result))


def _get_domain_def(domain: str) -> tuple[str, str]:
    return DOMAIN_MAP.get(domain, ("📌", domain.upper()))


def _domain_sort_key(domain: str, findings: list[Finding]) -> tuple[int, str]:
    """Sort domains: explicit order first, then by count descending."""
    explicit_order = {
        "quality": 0, "code_quality": 0,
        "tests": 1, "testing": 1,
        "docs": 2, "documentation": 2,
        "security": 3,
        "performance": 4,
        "git": 5,
        "deps": 6, "dependencies": 6,
        "session": 7,
        "other": 8,
    }
    return (explicit_order.get(domain, 99), -len(findings), domain)


# ---------------------------------------------------------------------------
# Human-readable renderer
# ---------------------------------------------------------------------------


@dataclass
class RenderOptions:
    show_file_refs: bool = True
    show_effort: bool = True
    show_owner: bool = True
    show_done: bool = True
    unverified_marker: str = "[UNVERIFIED]"
    max_description_chars: int | None = None


DEFAULT_OPTIONS = RenderOptions()


def _finding_file_ref(f: Finding) -> str:
    if f.file:
        return f"{f.file}:{f.line}" if f.line else f.file
    return ""


def _render_finding_line(f: Finding, opts: RenderOptions) -> str:
    """Render a single Finding as a compact line with priority dot and annotations."""
    dot = PRIORITY_DOT_MAP.get(f.priority, "⚪")
    parts = [f"{dot} "]

    desc = f.description
    if opts.max_description_chars and len(desc) > opts.max_description_chars:
        desc = desc[:opts.max_description_chars].rstrip() + "…"
    parts.append(desc)

    if opts.show_effort and f.effort:
        parts.append(f"[E:{f.effort}]")

    if f.unverified:
        parts.append(opts.unverified_marker)

    if opts.show_owner and f.owner_skill:
        parts.append(f"{{{f.owner_skill}}}")

    if opts.show_file_refs:
        ref = _finding_file_ref(f)
        if ref:
            parts.append(f"@ {ref}")

    return " ".join(parts)


def render_actions(
    findings: list[Finding],
    carryover: list[Finding] | None = None,
    opts: RenderOptions | None = None,
) -> str:
    """Render findings as human-readable RNS output with domain grouping.

    Adapted from RNS render.py render_actions(). Groups by domain, then by
    action type (recover/prevent/realize), with priority dots and annotations.
    """
    opts = opts or DEFAULT_OPTIONS
    carryover = carryover or []

    done_items = [f for f in findings if f.status == "resolved"] if opts.show_done else []
    pending = [f for f in findings if f.status != "resolved"]

    groups: dict[str, list[Finding]] = {}
    for f in pending:
        groups.setdefault(f.domain, []).append(f)

    lines: list[str] = []
    domain_num = 0

    for domain_key, domain_findings in sorted(
        groups.items(),
        key=lambda kv: _domain_sort_key(kv[0], kv[1]),
    ):
        domain_num += 1
        emoji, label = _get_domain_def(domain_key)
        lines.append(f"{domain_num} {emoji} {label} ({len(domain_findings)})")

        action_groups: dict[str, list[Finding]] = {}
        for f in domain_findings:
            action_groups.setdefault(f.action, []).append(f)

        item_counter = 0
        for action_key in ACTION_ORDER:
            if action_key not in action_groups:
                continue
            subgroup = action_groups[action_key]
            sorted_subgroup = sorted(
                subgroup,
                key=lambda f: (
                    PRIORITY_ORDER.index(f.priority) if f.priority in PRIORITY_ORDER else len(PRIORITY_ORDER),
                ),
            )
            label = ACTION_LABELS.get(action_key, action_key.title())
            lines.append(f"  {label} ({len(sorted_subgroup)} items)")

            prev_priority = None
            for f in sorted_subgroup:
                if prev_priority is not None and f.priority != prev_priority:
                    lines.append("")
                item_counter += 1
                sub = _subletter(item_counter)
                lines.append(f"    {domain_num}{sub} {_render_finding_line(f, opts)}")
                prev_priority = f.priority

        lines.append("")

    # Carryover section
    if carryover:
        co_num = domain_num + 1
        lines.append(f"{co_num} 📌 CARRYOVER ({len(carryover)} items)")
        for idx, f in enumerate(carryover, start=1):
            sub = _subletter(idx)
            lines.append(f"  {co_num}{sub} {_render_finding_line(f, opts)}")
        lines.append("")

    # Done section
    if done_items and opts.show_done:
        done_num = domain_num + (1 if carryover else 0) + 1
        lines.append(f"{done_num} ✓ DONE ({len(done_items)} items)")
        for idx, f in enumerate(done_items, start=1):
            sub = _subletter(idx)
            line = _render_finding_line(f, opts)
            # Strikethrough description
            parts = line.split(" ", 1)
            if len(parts) > 1:
                line = parts[0] + " ~~" + parts[1] + "~~"
            lines.append(f"  {done_num}{sub} {line}")
        lines.append("")

    # Do-all footer
    total = len(pending) + len(carryover)
    if total > 0:
        lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        lines.append(f"0 — Do ALL Recommended Next Actions ({total} items)")

    return "\n".join(lines).strip()


# ---------------------------------------------------------------------------
# Machine-format renderer
# ---------------------------------------------------------------------------


def render_machine_format(findings: list[Finding]) -> str:
    """Render findings in RNS-compatible machine-parseable pipe-delimited format.

    Format matches RNS render.py render_machine_format():
        RNS|D|{num}|{emoji}|{label}
        RNS|A|{num}{sub}|{domain}|E:{effort}|{action}/{priority}|{desc}|{file_ref}|owner={owner}|done={done}|caused_by={caused_by}|blocks={blocks}|unverified={unverified}
        RNS|Z|0|NONE

    This is the authoritative machine output contract for GTO artifacts.
    """
    lines: list[str] = ["<!-- format: machine -->"]

    # Group findings by domain
    groups: dict[str, list[Finding]] = {}
    for f in findings:
        groups.setdefault(f.domain, []).append(f)

    domain_num = 0
    for domain_key, domain_findings in groups.items():
        domain_num += 1
        emoji, label = _get_domain_def(domain_key)
        lines.append(f"RNS|D|{domain_num}|{emoji}|{label}")

        for idx, f in enumerate(domain_findings, start=1):
            sub = _subletter(idx)
            effort = f.effort or "?"
            desc = f.description.replace("|", "\\|")
            file_ref = _finding_file_ref(f)
            owner = f.owner_skill or ""
            done = "1" if f.status == "resolved" else "0"
            caused_by = ""
            blocks = ""
            unverified = "1" if f.unverified else "0"
            lines.append(
                f"RNS|A|{domain_num}{sub}|{f.domain}|"
                f"E:{effort}|{f.action}/{f.priority}|"
                f"{desc}|{file_ref}|owner={owner}|done={done}|"
                f"caused_by={caused_by}|blocks={blocks}|unverified={unverified}"
            )

    lines.append("RNS|Z|0|NONE")
    return "\n".join(lines)
