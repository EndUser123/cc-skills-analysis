# GTO Routing Policy

Findings are routed to owning skills based on `gap_type`:

| Gap Type | Owner Skill | Reason |
|----------|-------------|--------|
| missingdocs | /docs | Documentation gaps |
| techdebt | /code | Technical debt markers |
| runtime_error | /diagnose | Runtime bugs need diagnosis |
| bug | /diagnose | Bug investigation |
| security | /security | Security vulnerabilities |
| perf | /perf | Performance issues |
| invalidrepo | /git | Repository structure issues |
| staledeps | /deps | Dependency staleness |

Unrouted findings (no matching gap_type) remain available but have `owner_skill=None`.
