# TRACE debugRCA Integration Features

TRACE integrates with debugRCA for enhanced root cause analysis capabilities.

## 1. Evidence Saturation Detection

**What**: Detect when TRACE has sufficient evidence coverage
**When**: Automatic validation during TRACE
**Benefit**: Dynamic scenario generation based on evidence coverage

```python
from core.tracer import EvidenceSaturationChecker

checker = EvidenceSaturationChecker(threshold=0.75)
is_complete = checker.is_trace_complete(scenarios)
```

## 2. Red Flag Detection

**What**: Validate TRACE findings for anti-debugging patterns
**When**: Automatic quality check before accepting TRACE report
**Benefit**: Enforces TRACE best practices, prevents poor-quality reports

```python
red_flags = report.validate_quality()
# Returns: ["P0 issue without line reference: ..."]
```

## 3. ACH Scenario Generation

**What**: Generate comprehensive scenarios using Analysis of Competing Hypotheses framework
**When**: Enhanced scenario generation (6 categories vs 3 fixed)
**Benefit**: Systematic coverage of Logic, Data, State, Integration, Resource, Environment

```python
from core.tracer import ACHScenarioGenerator

generator = ACHScenarioGenerator()
scenarios = generator.generate_ach_scenarios(target_path, content, "code")
```

## 4. Timeline Visualization for RCA

**What**: Generate Mermaid timeline diagrams for incident reports
**When**: debugRCA Phase 1 (Gather) timeline visualization
**Benefit**: Visual incident timelines for RCA reports

```python
from core.tracer import generate_rca_timeline_mermaid

mermaid = generate_rca_timeline_mermaid(events, "Database Outage")
```

## 5. Call Graph Hypothesis Generation

**What**: Generate hypotheses from call graph analysis
**When**: debugRCA Phase 2 (Isolate) hypothesis generation
**Benefit**: Automated, evidence-based hypothesis generation

```python
from core.tracer import generate_hypotheses_from_call_graph

hypotheses = generate_hypotheses_from_call_graph("src/main.py")
```

## 6. CKS Findings Persistence

**What**: Store TRACE findings to CKS for cross-session pattern recognition
**When**: Automatic after TRACE completion
**Benefit**: Cross-session pattern recognition, trend analysis

```python
stored_count = report.persist_to_cks()
# Returns: Number of findings stored to CKS
```

## 7. Differential TRACE

**What**: Compare TRACE results between working and broken versions
**When**: Differential debugging for version comparison
**Benefit**: Faster root cause identification with version comparison

```python
from core.tracer import DifferentialTracer

diff_tracer = DifferentialTracer(
    target_path=Path("src/main.py"),
    working_version="abc123",
    broken_version="def456"
)
comparison = diff_tracer.compare_traces()
```

## Integration Benefits

| Feature | TRACE Benefit | debugRCA Benefit |
|---------|--------------|------------------|
| **Timeline Visualization** | N/A | Visual incident timelines |
| **CKS Storage** | Cross-session pattern recognition | N/A |
| **Red Flag Detection** | Quality enforcement | N/A |
| **Evidence Saturation** | Dynamic scenario generation | N/A |
| **ACH Scenarios** | Comprehensive coverage | Hypothesis categories |
| **Call Graph Hypotheses** | N/A | Automated hypothesis generation |
| **Differential TRACE** | Version comparison | Debugging framework |
