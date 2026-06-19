---
name: doc-compiler
version: 3.0.0
description: Compile skills, plugins, projects, and workflows into interactive, verified HTML documentation with Mermaid diagrams, TOC, proof metadata, and browser validation.
category: documentation
enforcement: strict
input_kinds:
  - skill
  - plugin
  - project
  - workflow
workflow_steps:
  - stage_a_source_extractor
  - stage_b_artifact_plan_builder
  - stage_c_mermaid_design
  - stage_d_mermaid_critic_review
  - stage_e1_loader
  - stage_e2_binder
  - stage_e3_assembler
  - stage_e4_writer
  - stage_f_static_validator
  - stage_g_artifact_proof
  - stage_h_external_critic
  - stage_i_emit_proof_metadata
triggers:
  - '/doc-compiler'
  - 'compile docs for'
  - 'create interactive docs for'
argument-hint: <target-path>
context: main
user-invocable: true
requires_tools:
  - browser-harness
status: active
---
# /doc-compiler — Documentation Compiler for Skills, Plugins, Projects, Workflows

Transforms source artifacts (skill SKILL.md, plugin manifest, project README, workflow YAML) into self-contained, verified, interactive HTML documentation with Mermaid diagrams, proof metadata, and browser-validated behavior.

## When to Use

- Skill needs browsable, shareable documentation
- Plugin manifest needs interactive reference
- Project README needs diagram visualization
- Workflow needs step-by-step walkthrough UI
- skill-craft routes here during EXECUTING when HTML output is needed

## Input Contract

```bash
/doc-compiler <target-path> [style]
# Examples:
/doc-compiler P:/.claude/skills/go/SKILL.md
/doc-compiler ./plugin-manifest.json
/doc-compiler ./my-project/README.md
/doc-compiler ./workflows/data-pipeline.yaml
/doc-compiler P:/.claude/skills/go/SKILL.md deepwiki
/doc-compiler P:/.claude/skills/go/SKILL.md product
/doc-compiler P:/.claude/skills/go/SKILL.md minimal
```

**Style selection (optional):**
- CLI arg 2 (`deepwiki`, `product`, `minimal`) takes highest precedence
- `DOCC_STYLE` env var is checked second
- `style` field in source frontmatter is checked third
- Defaults to `deepwiki` when none is specified

**Available styles:**
| Style | Character | Density | Diagram Weight |
|-------|-----------|---------|----------------|
| `deepwiki` | Architecture-first, OSS evaluator | dense | prominent (1.1×) |
| `product` | Polished hero, developer product page | comfortable | normal |
| `minimal` | Compact, reference-oriented, API docs | compact | collapsed (0.85×) |

**Reads:** Source file specified by `<target-path>`
**Outputs:**
- `<source-dir>/index.html` — written alongside target source (documentation artifact, not runtime state)
- `P:/.claude/.artifacts/{terminal_id}/doc-compiler/{target}/artifact-proof.json` (recommended)
- `P:/.claude/.artifacts/{terminal_id}/doc-compiler/{target}/source-model.json` (recommended)
- `P:/.claude/.artifacts/{terminal_id}/doc-compiler/{target}/diagram.mmd` (recommended)

***

## Pipeline Architecture

doc-compiler is a **compiler pipeline** where JSON is the source of truth between every stage. No stage reads prose spec directly — each receives only the structured output of the prior stage.

```
Stage A (Source Extractor)      → source-model.json
Stage B (Artifact Plan Builder) → artifact-plan.json (includes presentation.style)
Stage C (Mermaid Design)         → diagram.mmd
Stage D (Mermaid Critic)         → (gate)
Stage E (HTML Emitter)           → index.html (style-aware template assembly)
Stage F (Static Validator)       → static-validation.json
Stage G (Runtime Validator)      → artifact-proof.json
Stage H (External Critic)         → validation-report.json
Stage I (Proof Metadata)         → (final proof)
```

**Invariants between stages:**
- Each stage receives only the JSON artifact from the prior stage (not prose, not source file)
- Each stage outputs only one JSON artifact (never spec + implementation in the same file)
- Stage E (HTML Emitter) receives ONLY `artifact-plan.json` — never the full prose spec
- Stage H (External Critic) is a separate LLM instance from Stage E (HTML Emitter)

**Forbidden leakage rules:**
1. Final `index.html` must not contain internal control headings or policy prose from SKILL.md
2. CSS must not contain malformed selectors (bare identifiers where `#`, `.`, `:`, `@` is required)
3. Generated HTML must not invent routes, gates, or terminals not present in `artifact-plan.json`
4. Stage C must not emit spec commentary — only template-based HTML structure

***

## Style-Aware Presentation

The pipeline supports three named presentation styles that control section ordering, density, and visual tone without changing the underlying content.

**Style resolution order (first wins):**
1. CLI argument 2 (`deepwiki | product | minimal`)
2. `DOCC_STYLE` environment variable
3. `style:` field in source YAML frontmatter
4. Default: `deepwiki`

**How style flows through the pipeline:**
- Stage A extracts `style` from frontmatter into `source-model.json`
- Stage B resolves style from CLI > env > frontmatter > default, and writes `presentation.style` into `artifact-plan.json`
- Stage E1 loads style-specific template overrides (checked first) with fallback to `templates/`
- Stage E3 assembles CSS with a style-specific overlay on top of the shared base layer
- Content bindings (steps, artifacts, route-outs) remain identical across all styles

**Template loading rules:**
- Style-specific section templates live in `templates/styles/<style>/`
- Missing style files fall back to `templates/<name>` (shared)
- `base-shell.html`, `toc.html`, and all required DOM IDs must always resolve (style cannot strip required IDs)
- Style CSS overlays are appended after the shared CSS base layer

**Required DOM IDs (must never be removed by any style):**
`tocToggle`, `toc`, `themeToggle`, `searchInput`, `clearSearch`, `mermaidSource`, `diagramViewport`, `diagramStage`, `zoomIn`, `zoomOut`, `zoomReset`, `zoomFit`, `zoomPct`, `paletteSelect`, `diagramResizeHandle`

**Section ordering by style:**
| Section | deepwiki | product | minimal |
|---------|----------|---------|---------|
| overview | ✓ | ✓ | ✓ |
| what-it-does | ✓ | ✓ | — |
| pipeline | ✓ | ✓ | — |
| stages | ✓ | ✓ | ✓ |
| validation | ✓ | ✓ | ✓ |
| artifacts | ✓ | ✓ | ✓ |
| filemap | ✓ | ✓ | — |
| functions | ✓ | ✓ | ✓ |
| workflow | ✓ | ✓ | — |
| appendix | ✓ | ✓ | — |

**Validator compatibility:** All existing Stage F (static) and Stage G (runtime) validators check the same required DOM IDs regardless of style. Style CSS is visual-only and does not affect DOM structure.

***

## Workflow

### Stage A: Source Extractor → `source-model.json`

Read the target source file completely. Extract at minimum:
- frontmatter
- `steps`
- description, triggers, key sections
- prose-described routing, checklists/gating questions
- terminal states, artifacts emitted, referenced sub-skills

Build and emit `source-model.json`. Do not generate Mermaid or HTML yet.

```json
{
  "kind": "string",
  "name": "string",
  "version": "string",
  "description": "string",
  "steps": [
    {
      "id": "stable-step-id",
      "index": 1,
      "name": "read_source",
      "display_name": "Read Source",
      "description": "string",
      "kind": "step|decision|route|terminal|artifact",
      "conditions": [],
      "inputs": [],
      "outputs": [],
      "routes_to": [],
      "artifacts_emitted": []
    }
  ],
  "decision_points": [],
  "route_outs": [],
  "terminal_states": [],
  "artifacts": [],
  "gaps": [],
  "ambiguities": []
}
```

This workflow model is the source of truth for all downstream stages.

### Stage B: Artifact Plan Builder → `artifact-plan.json`

Receive `source-model.json` from Stage A. Design the page structure and emit `artifact-plan.json`.

```json
{
  "template": "default-docs-v1",
  "page_structure": {
    "sections": [
      { "id": "overview", "type": "hero", "title": "string" },
      { "id": "facts", "type": "quick-facts", "items": ["string"] },
      { "id": "diagram", "type": "mermaid" },
      { "id": "steps", "type": "accordion", "items": ["step-id"] },
      { "id": "route-outs", "type": "route-out-list" },
      { "id": "terminals", "type": "terminal-list" },
      { "id": "artifacts", "type": "artifact-cards" },
      { "id": "proof", "type": "proof-metadata" }
    ]
  },
  "ui_config": {
    "palette": "tailwind-modern",
    "toc_width": "18rem",
    "toc_breakpoint": 960,
    "diagram_height_initial": 480,
    "diagram_height_min": 200,
    "diagram_height_max": 800
  },
  "mermaid_source": "string (raw Mermaid diagram source)",
  "mermaid_config": { "curve": "basis", "nodeSpacing": 40, "rankSpacing": 50 },
  "toc_config": { "width": "18rem", "breakpoint": 960 },
  "css_contract": {
    "toggle_position": "fixed",
    "toggle_left": "0",
    "toc_transition": "left",
    "no_transform_on_desktop": true,
    "toggle_outside_nav": true,
    "mobile_toggle_display": "flex"
  },
  "content_bindings": {
    "name": "from source-model.name",
    "version": "from source-model.version",
    "description": "from source-model.description",
    "steps": "from source-model.steps",
    "route_outs": "from source-model.route_outs",
    "terminal_states": "from source-model.terminal_states",
    "artifacts": "from source-model.artifacts"
  }
}
```

**`template_version` field:** When emitting, the LLM must include a `template_version` field in `artifact-plan.json` matching a known template pack. If the version does not exist, fail with a descriptive error before attempting assembly.

**Stage C (HTML Emitter) receives ONLY this JSON.** It does not read SKILL.md or source-model.json directly — all content bindings are declared in `content_bindings` and resolved at render time.

#### Gap Detection (Stage B sub-process)

Before building `artifact-plan.json`, cross-check the source for mismatches.

Mandatory checks:

1. **Prose-only routing**
   - If prose says "route to /planning", "delegate to /code", or similar, but this is not reflected in `steps`, add it to the workflow model as a route or decision.

2. **Checklist-implied branching**
   - If a checklist question implies a Yes/No path (e.g. "Do I need explore first?"), model it as a decision gate.

3. **Conditional steps shown as unconditional**
   - If a step only runs under conditions, mark it conditional in the workflow model and diagram.

4. **Missing step descriptions**
   - If a `steps` entry has no prose description, generate a brief, faithful description before HTML generation.

5. **Terminal states not represented**
   - If the skill emits end states, promises, or blocking outcomes, ensure they appear in the workflow model.

6. **Artifact outputs not represented**
   - If the skill writes files, reports, JSON, or tokens, ensure those outputs are represented in the model.

7. **Naming mismatches**
   - If a prose label differs from the actual `steps` entry, preserve the source-of-truth step name and optionally use prose wording as display text.

If gaps remain unresolved, record them under `ambiguities` in the workflow model and surface them in proof metadata.

**Gate:** `ambiguities.length === 0 OR ambiguities_recorded === true` — unresolved gaps must be explicitly recorded, not silently ignored.

### Stage C: Mermaid Design → `diagram.mmd`

Generate Mermaid from the normalized workflow model, not directly from raw prose.

**Layout rules:**

| Rule | Why | Enforce with |
|------|-----|--------------|
| Direction matters | TD for vertical workflows, LR for state-machine-like flows | `flowchart TD` or `flowchart LR` |
| Group by phase | Related concepts should share rank or proximity | Node order / rank alignment |
| Avoid crossings | Crossings reduce readability | Reorder nodes or insert invisible guides |
| Color-code intent | Forward vs route-out vs terminal is easier to scan | Distinct classDefs |
| Smooth curves | Improves readability in dense graphs | `curve: 'basis'` (mandatory, not optional) |
| Spacing matters | Avoid visual fusion and excessive gaps | `nodeSpacing: 60`, `rankSpacing: 80`, `padding: 16` |
| Width control | Prevent jagged wrapping | responsive container + `useMaxWidth: true` |
| Visual weight for decisions | Decision gates must feel different from steps | gate stroke-width: 3px, step stroke-width: 2.5px |
| Stroke color distinguishes type | Different node types should have distinct stroke colors | classDefs use different stroke: colors per type |
| Label length | Long labels create Jagged edges and break zoom readability | Max 40 chars per node; use `wrap()` for longer labels; never exceed 2 visual lines |

**Label length enforcement:**

- Target: ≤ 40 characters per node label
- If label exceeds 40 chars: truncate to 40 and append `wrap()`
- If wrapped label exceeds 2 visual lines: split into two nodes or use a shorter phrase
- `curve: 'basis'` is mandatory on every diagram — omit it only if the graph has ≤ 5 nodes

**Node shape choices:**
- Start/End: rounded pill
- Step: rectangle
- Decision: diamond
- Route-out: distinct class
- Terminal state: pill or emphasized terminal node
- Artifact/data: boxed state node

The diagram must reflect actual decision structure, route-outs, and terminal states.

**Visual style guidelines (REQUIRED for all diagrams):**

ClassDef colors — use these exact values for consistent dark-theme appearance:
```
classDef step     fill:#1e40af, stroke:#60a5fa, stroke-width:2.5px, color:#ffffff, font-size:13px, font-weight:600
classDef gate     fill:#92400e, stroke:#fbbf24, stroke-width:3px,   color:#fef3c7, font-weight:700
classDef terminal fill:#059669, stroke:#10b981, stroke-width:3px,   color:#ffffff, font-weight:700
classDef route-out fill:#7c3aed, stroke:#c084fc, stroke-width:2px,  color:#ede9fe, font-style:italic
classDef start    fill:#1e1b4b, stroke:#818cf8, stroke-width:3px,  color:#c7d2fe, font-weight:700
```

Emoji in labels — use emoji prefix for visual scanning:
- `📖` step labels (read, extract, scan)
- `🔍` for detection/analysis
- `🎨` for design/generate
- `⚙️` for build/emit
- `✅` or `✔️` for success/terminal
- `⚠️` for gates/critic points
- `↪` for route-outs/delegation

Edge labels — every non-forward edge must have a descriptive label:
- Decision branches: `|✓ pass|` and `|✗ fail|`
- Data flows: `|frontmatter + metadata|` style labels
- At least one labeled edge per decision point

Init config — include in every diagram:
```
%%{ init: { 'theme': 'dark', 'flowchart': { 'curve': 'basis', 'nodeSpacing': 60, 'rankSpacing': 80 }, 'htmlLabels': true } }%%
```

Readability at zoom levels — diagram must remain legible at 50%, 100%, and 150% zoom. Test by temporarily scaling the SVG.

### Stage D: Mermaid Critic Review (MANDATORY GATE)

```
agent: general-purpose
purpose: Validate Mermaid diagram for doc-compiler workflow artifact
inputs:
  - diagram.mmd           # Raw Mermaid source
  - source-model.json   # Source of truth for what diagram must represent
checks:
  1. Start-to-end traceability — trace from Start to every terminal without lifting your pen
  2. Edge crossings — count crossing pairs; flag if > 0
  3. Label clarity — every node label is self-explanatory standing alone
  4. Non-forward edge labeling — every edge that is not a forward/pass has an explicit condition label
  5. Readability at 50% zoom — all text legible, no overlapping nodes
  5b. Zoom 50% legible — at 50% zoom, all node labels have effective font size ≥ 10px (computed fontSize * 0.5 ≥ 10px)
  5c. Zoom 100 no overflow — at 100% zoom, no text overflow, all edges labeled if present
  5d. Zoom 150 no scroll — at 150% zoom, diagram width * 1.5 ≤ viewport width, no horizontal scroll
  6. Mermaid syntax validity — parse with no errors
  7. Coverage of all workflow model steps — every step in source-model.json appears as a node
  8. Coverage of all route-outs — every route_out in workflow model appears in diagram
  9. Coverage of all terminal states — every terminal state in workflow model appears
  10. Coverage of all decision points — every decision_point in workflow model is a diamond or branch
  11. Explicit color: in each classDef — every classDef has a color: attribute (not just fill:/stroke:)
  12. Theme-safe text colors:
      - Dark theme: text color must have ≥ 4.5:1 contrast ratio against node fill (light text on dark fill)
      - Light theme: text color must be dark enough to read on light fills (no #000 on white without contrast)
      - Verify both themes; reject any color: value that is purely #000 with no theme-specific override
gate: crossings == 0 AND syntax_errors == [] AND legibility_score >= 0.8 AND missing_steps == [] AND missing_route_outs == [] AND missing_terminal_states == [] AND dark_theme_contrast_ok == true AND light_theme_text_readable == true AND zoom_50_legible == true AND zoom_100_no_overflow == true AND zoom_150_no_scroll == true
```

**Note:** `agent: general-purpose` is the canonical subagent type for inline critic agents, consistent with skill-craft's own mermaid critic block. This string is an established convention, not an arbitrary value. The `subagent_type` field is intentionally omitted in favor of inline agent dispatch.

If the critic fails, fix the workflow model or Mermaid before proceeding.

**Error handling:** If the agent dispatch fails or returns an error, record the error in the proof metadata and fail the step with a descriptive message. Infrastructure failures (agent timeout, browser launch failure) are distinct from critic-gate failures — report the exact failure mode.

### Stage E: HTML Emitter → `index.html`

**Receives ONLY `artifact-plan.json`** — never the full prose SKILL.md. All content bindings are resolved from the plan's declared references.

**Template assembly (Stage E core behavior):**
Stage E assembles `index.html` by loading named template skeleton files and filling them with data from `artifact-plan.json`. It does NOT generate layout, CSS, or control JS from prose rules.

Assembly sequence:
1. Read `artifact-plan.json.template_version` to identify the template pack
2. Load `templates/base-shell.html` — contains DOCTYPE, `<head>`, `.page-shell` wrapper, and `#tocToggle` button
3. Load `templates/toc.html` — insert into `nav#toc`
4. Load section templates in `page_structure.sections` order: `templates/hero.html`, `templates/facts.html`, `templates/mermaid-panel.html`, `templates/steps-accordion.html`, `templates/route-outs.html`, `templates/terminals.html`, `templates/artifacts.html`, `templates/proof-summary.html`
5. Concatenate CSS files: `templates/shared-css.css` + `templates/toc-css.css` + `templates/section-css.css` + `templates/diagram-css.css`
6. Inline `mermaid-palettes.json` (from `artifact-plan.json.ui_config.palette`) into the JS as `PALETTES`
7. Load JS: `templates/shared-scripts.js` (non-mermaid init) then `templates/diagram-scripts.js` (mermaid, zoom/pan, resize)
8. Fill content slots from `content_bindings` — never generate prose or structure from scratch

**Invariant:** Stage E must not generate or modify infrastructure code outside content slots. Only bind data.

**Template-based emission rules:**
- HTML structure is produced from the template contract (see HTML Authoring Rules section)
- Content values are sourced exclusively from `artifact-plan.json.content_bindings`
- CSS is emitted from the `css_contract` declared in `artifact-plan.json`
- No control headings, policy prose, or internal control flow text from SKILL.md may appear in the output

**Page structure (from `artifact-plan.json.page_structure.sections`):**

1. **Hero card** — skill name, version badge, description (from `content_bindings`)
2. **Quick Facts** — bullets derived from step count, gate count, artifact count, browser check count (from `content_bindings`)
3. **Mermaid diagram section** (with zoom/pan/reset controls per `mermaid_config`)
4. **Workflow Steps** — accordion per step, title + description from `content_bindings.steps`
5. **Route Outs** — distinct section with each route-out's target and trigger condition
6. **Terminal States** — distinct section with each terminal's description
7. **Artifacts** — card per artifact with path + copy-to-clipboard button
8. **Proof Summary** — scannable card: coverage metrics, gate pass/fail status

**Required elements (from template):**
- `#tocToggle` as sibling of `.page-shell` (NOT inside `nav.toc`)
- `nav#toc` with class `.toc`, desktop `position: fixed; left: 0` transition
- Mermaid diagram with zoom/pan/reset controls
- **Diagram pane resize handle** — user-draggable vertical resize between 200px and 800px
- Accordion per step
- Theme toggle inside `.toc-header .toc-controls`
- Search UI
- Copy-to-clipboard for all artifact paths
- Responsive layout (mobile: `#tocToggle` visible at top-left)

**Diagram pane resizing (REQUIRED — no exceptions):**
The diagram pane must be resizable by the user via a drag handle on the bottom edge of `.diagram-shell`.

DOM structure (inside `.diagram-shell`, after `.diagram-viewport`):
```html
<div class="diagram-resize-handle" id="diagramResizeHandle"
     role="separator" aria-orientation="horizontal"
     aria-label="Drag to resize diagram pane" tabindex="0" title="Drag to resize">
</div>
```

CSS (`.diagram-shell` must be `display: flex; flex-direction: column`):
```css
.diagram-shell {
  display: flex;
  flex-direction: column;
  background: var(--surface-2);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  overflow: hidden;
}
.diagram-viewport {
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;
  touch-action: none;
  cursor: grab;
  position: relative;
  min-height: 200px;        /* will be overridden by JS height, clamped 200-800px */
  background: var(--surface);
  flex-shrink: 0;
}
.diagram-viewport:active { cursor: grabbing; }
.diagram-resize-handle {
  height: 6px;
  background: var(--border);
  cursor: ns-resize;
  transition: background var(--timing-snap);
  flex-shrink: 0;
}
.diagram-resize-handle:hover,
.diagram-resize-handle:focus { background: var(--accent); outline: none; }
.diagram-resize-handle:focus { outline: 2px solid var(--accent); outline-offset: -2px; }
```

JS (drag-to-resize, clamped 200–800px):
```javascript
const resizeHandle = document.getElementById('diagramResizeHandle');
const diagramViewport = document.getElementById('diagramViewport');
let isResizing = false;
let lastResizeY = 0;
const MIN_HEIGHT = 200;
const MAX_HEIGHT = 800;

resizeHandle?.addEventListener('pointerdown', (e) => {
  if (e.button !== 0) return;
  e.stopPropagation(); // prevent viewport's pointerdown from capturing first
  isResizing = true;
  lastResizeY = e.clientY;
  resizeHandle.setPointerCapture(e.pointerId);
  document.body.style.cursor = 'ns-resize';
  document.body.style.userSelect = 'none';
}, { capture: true });

resizeHandle?.addEventListener('pointermove', (e) => {
  if (!isResizing) return;
  const dy = e.clientY - lastResizeY;
  lastResizeY = e.clientY;
  const currentHeight = diagramViewport.clientHeight;
  const newHeight = Math.min(MAX_HEIGHT, Math.max(MIN_HEIGHT, currentHeight + dy));
  diagramViewport.style.height = newHeight + 'px';
}, { capture: true });

resizeHandle?.addEventListener('pointerup', () => {
  isResizing = false;
  document.body.style.cursor = '';
  document.body.style.userSelect = '';
});

resizeHandle?.addEventListener('pointercancel', () => {
  isResizing = false;
  document.body.style.cursor = '';
  document.body.style.userSelect = '';
});

resizeHandle?.addEventListener('keydown', (e) => {
  // Arrow keys adjust height in 40px steps
  if (e.key === 'ArrowUp' || e.key === 'ArrowRight') {
    e.preventDefault();
    const newHeight = Math.min(MAX_HEIGHT, diagramViewport.clientHeight + 40);
    diagramViewport.style.height = newHeight + 'px';
  }
  if (e.key === 'ArrowDown' || e.key === 'ArrowLeft') {
    e.preventDefault();
    const newHeight = Math.max(MIN_HEIGHT, diagramViewport.clientHeight - 40);
    diagramViewport.style.height = newHeight + 'px';
  }
});
```

Key implementation notes:
- `{ capture: true }` on `pointerdown` and `pointermove` is REQUIRED so the handle's listeners fire before the viewport's (which also uses `setPointerCapture`)
- `e.stopPropagation()` on the handle's `pointerdown` prevents the viewport from ever acquiring the pointer capture
- `setPointerCapture` keeps resize working even when the pointer moves outside the handle
- Keyboard adjustment uses 40px steps, same clamped range
- `diagramViewport.style.height` is set directly; `min-height: 200px` on the viewport provides the floor

**Style requirements (from template):**
- Inter + JetBrains Mono via Google Fonts
- `#0d1017` background for code/path blocks
- Section cards: gradient background, `1px solid` border, `8-12px` radius, soft shadow
- Gate badges: warm amber; Route badges: purple; Terminal badges: green
- `:target` box-shadow flash animation
- Exactly 3 transition timings (see Animation Consistency below)
- Light mode CSS via `@media (prefers-color-scheme: light)` (see Light Mode below)

**Required emission-time checks (BLOCKING — fail if violated):**
- [ ] Every async operation (`navigator.clipboard.writeText`, `fetch`, etc.) has a `try/catch`
- [ ] `setTimeout`/`setInterval` calls are tracked and cleared on `beforeunload`, or use `AbortController`
- [ ] No direct DOM mutation inside `forEach`/loop — use `DocumentFragment` to batch
- [ ] All scroll/touch event listeners use `{ passive: true }`
- [ ] All interactive non-button elements have `role` and `tabindex` set
- [ ] `::selection` pseudo-element is defined
- [ ] Form elements (`button, input, select, textarea`) have explicit `line-height`
- [ ] Semantic element ratio ≥ 15% of divs (`<main>`, `<nav>`, `<section>`, `<article>`, `<header>`)
- [ ] Light mode CSS variables are defined for every dark mode variable

**CSS contract enforcement (from `artifact-plan.json.css_contract`):**
Before emitting, verify the CSS will contain:
1. `#tocToggle { position: fixed; left: 0; }` — always at viewport left edge
2. `#tocToggle { display: flex; }` at `max-width: 960px` — no `display: none` on mobile
3. `.toc { transition: left var(--timing-smooth), opacity var(--timing-smooth); }` — uses `--timing-smooth` CSS variable, not hardcoded value
4. `.toc.collapsed { left: calc(-1 * var(--toc-width) + 40px); }` — desktop tab variant
5. `.main-content` transitions `margin-left` and `max-width` using `var(--timing-smooth)` on `body.toc-hidden`
6. `#tocToggle` is a sibling of `.page-shell`, NOT inside `nav.toc`
7. **Exactly 3 transition timing values** used throughout: `140ms ease` (snap), `180ms ease` (smooth/layout), `200ms ease` (slow/emphasis) — no other timing values
8. **Light mode** `@media (prefers-color-scheme: light)` redefines every `--var` used in dark mode
9. **`::selection`** pseudo-element defined using `--accent` and `--bg`
10. **Form elements** (`button, input, select, textarea`) have explicit `line-height` set

If the CSS would violate any of these, fail with a descriptive error identifying the violated rule.

**Self-emission validation check (after HTML is assembled — BLOCKING):**
After assembling `index.html` from template files, the emitter MUST verify the following before proceeding to Stage F. Since HTML now comes from verified template files, this check confirms assembly completeness rather than generation correctness.

Assembly verification checks:
- [ ] All template skeleton files were loaded from the declared `template_version` path
- [ ] `base-shell.html` provided the `<!DOCTYPE>`, `<head>`, `.page-shell`, and `#tocToggle`
- [ ] `toc.html` provided `nav#toc` with `.toc-header` and `.toc-body`
- [ ] All `page_structure.sections` have corresponding template files assembled
- [ ] `mermaid_source` from `artifact-plan.json` is present in `pre#mermaidSource`
- [ ] No freeform HTML detected outside the known template structure (look for unexpected `<script>` blocks, inline styles, or prose not from `content_bindings`)
- [ ] `window.initTocToggle`, `window.toggleStep`, `window.copyPath` are defined in the script block
- [ ] `pre#mermaidSource` contains Mermaid diagram source (not empty)
- [ ] `.diagram-resize-handle` is present in the DOM

If any check fails, fail with a descriptive error identifying the missing template slot or unexpected content. Do not proceed to Stage F with an incompletely assembled artifact.

### Stage F: Static Validator → `static-validation.json`

**Role: static-validator.** Reads the emitted `index.html` and checks structural and CSS validity before any browser testing begins.

**Checks (all blocking):**

**S1. Malformed selector check:**
- Scan all CSS in `index.html` (inline `<style>` or linked)
- Flag any bare identifier where proper syntax requires `#`, `.`, `:`, or `@`
- Example: `toc { ... }` is malformed (should be `.toc`); `@media (max-width 960px)` is malformed (should be `(max-width: 960px)`)
- Any malformed selector → blocking FAIL

**S2. DOM structure check:**
- `#tocToggle` must be a sibling of `.page-shell`, not inside `nav.toc`
- If `document.getElementById('tocToggle').parentElement.id === 'toc'` → FAIL
- `nav#toc` must exist as a sibling of `.main-content`

**S3. CSS mechanism check:**
- No `transform: translateX` on `.toc` at desktop viewport (min-width: 961px)
- If CSS contains `transform: translateX` applied to `.toc` at desktop → FAIL
- `transition: left` on `.toc` must be present

**S4. Toggle visibility check:**
- No `display: none` on `#tocToggle` at any breakpoint
- If any CSS rule sets `#tocToggle { display: none; }` → FAIL

**S5. Content binding check:**
- Generated HTML must not contain internal SKILL.md prose or policy text not derivable from `artifact-plan.json`
- Any hardcoded text that appears to be copied from SKILL.md → flag for review (not automatically blocking unless obviously internal)

**S6. No invented content:**
- Every `section#workflow-step-*` in HTML must correspond to a step in `source-model.json`
- Any section not backed by the model → FAIL

**S7. Mermaid render call check:**
- The module script must call `mermaid.render(` to generate SVG markup
- `mermaid.render(id, source)` returns `{ svg }` markup — this is the correct approach for injecting fresh SVG on palette/zoom changes
- `startOnLoad: true` alone is insufficient — Mermaid v11 ESM does not reliably auto-render from module scripts
- If `mermaid.render(` is absent from the script block → FAIL

**S8. YAML frontmatter isolation check:**
- The frontmatter block is the content between the first `---` and the second `---` (lines 1–30)
- Isolate the frontmatter using `split('---', 2)[1]` (maxsplit=2, take the middle part) before passing to `yaml.safe_load()`
- Note: `\n---\n` does NOT match at the file start because the first `---` has no preceding newline — `split('---', 2)` handles all cases correctly
- If `yaml.safe_load()` is passed the full file content → the `---` section dividers inside the body create extra YAML documents → `safe_load()` raises `ComposerError` or `ParserError` → FAIL
- Valid SKILL.md: exactly one YAML document in the frontmatter block

**S9. TOC toggle click logic check:**
- Read the `initTocToggle` function body in the generated HTML
- The click handler must toggle `collapsed` and `toc-hidden` using the SAME boolean — if it toggles one with `expanded` it must toggle the other with `expanded` (not `!expanded`)
- Invariant: `toc.classList.toggle('collapsed', X)` and `body.classList.toggle('toc-hidden', X)` must use the same `X` (both `expanded` or both `!expanded`)
- If the two toggles use opposite booleans → FAIL (the toggle is inverted — clicking when open adds the closed class)

**S10. CSS completeness check:**
- Extract the `<style>` block content from `index.html`
- Scan for incomplete declarations: every `property:` must be followed by a value before the next `;` or `}`. Pattern `:/[^;}]*[\n}]` flags a missing value → FAIL
- Scan for `:root` or `body` defining all CSS custom properties used in the stylesheet. Undefined `--var-name` references silently fall through → FAIL
- Scan for duplicate non-adjacent selectors: if the same selector appears more than once in the `<style>` block, the second rule overrides the first with no warning → flag for review, not automatically blocking
- All `rgba()` calls must have exactly 4 comma-separated numeric components → FAIL if 3-component rgb found
- Every `font-weight` value must be `100`–`900` in steps of 100, or a named keyword (`normal`, `bold`, etc.) → FAIL if bare `600` style number outside this range appears without unit
- `overflow-x: hidden` must be present on `html` or `body` to clip the collapsed desktop TOC (which sits at `left: calc(-1 * var(--toc-width) + 40px)` ≈ `left: -248px`) → FAIL if absent

**S11. CSS transition timing check:**
- Scan all CSS for `transition` or `transition-duration` values
- Collect every unique timing value (e.g., `140ms`, `200ms`, `300ms`)
- There MUST be exactly 3 unique timing values across the entire stylesheet
- If > 3 unique timings found → FAIL with list of all unique values
- Exceptions: `0ms` and `animation` keyframe timings are excluded from the count

**S12. Light mode check:**
- `@media (prefers-color-scheme: light)` block MUST exist in `<style>`
- Inside that block, every CSS variable used in dark mode MUST be redefined
- If any `--var` used in the main stylesheet is absent from the light-mode block → FAIL, listing the missing variables

**S13. Selection and form element check:**
- `::selection` pseudo-element MUST be defined in CSS → FAIL if absent
- Every `button`, `input`, `select`, `textarea` rule (or shared rule) MUST have explicit `line-height` → FAIL if absent

**S14. Semantic HTML ratio check:**
- Count semantic elements: `<main>`, `<nav>`, `<section>`, `<article>`, `<header>`, `<aside>`, `<footer>`, `<figure>`, `<figcaption>`, `<time>`
- Count non-semantic: `<div>`, `<span>`
- Ratio = semantic / (semantic + non-semantic)
- If ratio < 0.15 (15%) → FAIL

**S15. Accessibility attribute check:**
- Every `<button>` MUST have either visible text content OR `aria-label`
- Every icon-only button (no text) MUST have both `aria-label` AND `title`
- Missing `aria-label` on icon button → FAIL

**S16. JS async/timeout check:**
- Scan the `<script>` block for `navigator.clipboard.writeText`, `fetch`, or `.then(` patterns
- Each async pattern MUST be inside a `try { ... } catch` block
- If async call found without surrounding try/catch → FAIL
- Scan for `setTimeout` / `setInterval` — each MUST have a corresponding `clearTimeout`/`clearInterval` on `beforeunload`, or the script must use `AbortController`
- Missing cleanup → FAIL
- Resize handle JS: the script MUST define `isResizing`, `lastResizeY`, `MIN_HEIGHT`, `MAX_HEIGHT`, and event listeners for `pointerdown`, `pointermove`, `pointerup`/`pointercancel` on `#diagramResizeHandle` (or the handle element)
- The `pointerdown` handler MUST call `e.stopPropagation()` to prevent viewport capture conflicts
- If resize handle listeners are absent or missing `stopPropagation()` → FAIL

**S17. HTML structural completeness check:**
- Extract the full `<body>` content
- Parse for balanced tag structure: every opening tag must have a matching closing tag in the correct hierarchy. Unmatched tags → FAIL
- The following elements MUST be present in the DOM (exact IDs):
  - `#tocToggle` (toggle button)
  - `#toc` (sidebar nav)
  - `#themeToggle` (theme toggle inside `.toc-controls`)
  - `pre.mermaid#mermaidSource` (diagram source block, inside `.diagram-stage`)
  - `#diagramViewport` (diagram viewport container)
  - `#diagramStage` (diagram transform stage)
  - `#zoomIn`, `#zoomOut`, `#zoomReset`, `#zoomFit` (zoom controls)
  - `#zoomPct` (zoom percentage readout)
  - `#paletteSelect` (palette selector)
  - `#diagramResizeHandle` (resize handle — must exist as a sibling of `.diagram-viewport` inside `.diagram-shell`)
  - `#searchInput` (search field)
  - `.main-content` (content area)
  - `section#overview` (hero)
  - `.toc-body` (TOC nav body)
  - Any missing required element → FAIL

**S18. Mermaid SVG centering check:**
- Extract the `<style>` block content from `index.html`
- Scan for `.mermaid-container svg` CSS rule
- If the rule exists, it MUST include `display: block` AND `margin: 0 auto` (or `margin: auto`) for horizontal centering
- If centering properties are absent → FAIL
- If `.mermaid-container svg` rule is absent entirely → PASS (centering is optional for CSS-based centering approaches)

**S19. Template contract check:**
Since Stage E now assembles HTML from verified template skeleton files rather than generating from prose, this check verifies the assembly was correctly formed:
- Template files must exist at the declared `template_version` path
- All required template sections must be present in the assembled output
- No freeform HTML outside the known template structure
- Content bindings must be filled — no empty required slots

**Gate:** S1–S19 ALL pass. Output `static-validation.json`:
```json
{
  "passed": "boolean",
  "checks": {
    "malformed_selectors": { "passed": "boolean", "found": [] },
    "dom_structure": { "passed": "boolean", "toc_toggle_parent": "string" },
    "css_mechanism": { "passed": "boolean", "transform_found": "boolean" },
    "toggle_visibility": { "passed": "boolean", "display_none_found": "boolean" },
    "no_invented_content": { "passed": "boolean", "extra_sections": [] },
    "mermaid_render_call": { "passed": "boolean", "has_mermaid_run": "boolean" },
    "yaml_isolation": { "passed": "boolean", "frontmatter_isolated": "boolean" },
    "toc_toggle_logic": { "passed": "boolean", "toggle_inverted": "boolean" },
    "css_completeness": { "passed": "boolean", "incomplete_declarations": [], "missing_vars": [], "overflow_clip": "boolean" },
    "transition_timings": { "passed": "boolean", "unique_timings": [], "count": "integer" },
    "light_mode": { "passed": "boolean", "missing_vars": [] },
    "selection_and_form": { "passed": "boolean", "selection_present": "boolean", "form_line_height": "boolean" },
    "semantic_ratio": { "passed": "boolean", "ratio": "float", "semantic_count": "integer", "nonsemantic_count": "integer" },
    "accessibility_attrs": { "passed": "boolean", "missing_labels": [] },
    "js_async_timeout": { "passed": "boolean", "async_without_catch": [], "uncleaned_timers": [] },
    "html_structure": { "passed": "boolean", "missing_elements": [], "unmatched_tags": [] }
  },
  "validatedAt": "ISO-8601"
}
```

If any check fails, the skill run is failed. Do not proceed to Stage G.

### Stage G: Runtime Validator → `artifact-proof.json`

**Not agent-portable.** The orchestrating LLM performs this step directly. Do not dispatch to a subagent.

**Rule: Treat the generated HTML as untrusted.** DOM inspection alone is insufficient. Every layout-affecting behavior MUST be verified with a live browser assertion AND a captured screenshot showing the result.

#### Verification Matrix

Run the full matrix before declaring success. Every cell is mandatory.

| Viewport | Action | What to verify |
|----------|--------|----------------|
| Desktop (1280×800) | Initial load | TOC visible, main content has left margin, no console errors |
| Desktop (1280×800) | Click TOC toggle | TOC hides, main content expands to fill space |
| Desktop (1280×800) | Click TOC toggle again | TOC reappears, main content returns to margin |
| Desktop (1280×800) | Resize to ≤960px | TOC hidden, #tocToggle visible at top-left |
| Mobile (375×667) | Initial load | #tocToggle visible at top-left (not display:none), TOC collapsed |
| Mobile (375×667) | Click toggle | TOC opens, main content reflows |
| Mobile (375×667) | Click toggle again | TOC closes |
| Desktop (1280×800) | Click theme toggle | Mermaid rerenders, viewport state preserved |
| Any | Accordion open/close | Section expands/collapses, no layout break |
| Any | Search query | Matching sections visible, non-matching hidden |
| Desktop (1280×800) | Mermaid zoom 50% | All node labels legible (effective font ≥ 10px), screenshot required |
| Desktop (1280×800) | Mermaid zoom 100% | No text overflow, all edges labeled if present, no horizontal scroll |
| Desktop (1280×800) | Mermaid zoom 150% | Diagram width * 1.5 ≤ viewport width, no horizontal scroll |
| Desktop (1280×800) | Drag resize handle up | Diagram pane shrinks, clamped at MIN_HEIGHT (200px), no overflow |
| Desktop (1280×800) | Drag resize handle down | Diagram pane grows, clamped at MAX_HEIGHT (800px), no overflow |
| Desktop (1280×800) | Resize handle ArrowUp key | Diagram pane height decreases by ~40px, clamped at 200px |
| Desktop (1280×800) | Resize handle ArrowDown key | Diagram pane height increases by ~40px, clamped at 800px |

#### Explicit Assertions (all MUST pass)

For each assertion below, record the actual result in `verification_matrix` in artifact-proof.json.

**TOC state model invariants (MUST hold at all times):**
- `nav.classList.contains('collapsed')` is `true` ↔ `body.classList.contains('toc-hidden')` is `true` (they are always the same value, never opposites)
- `aria-expanded` on `#tocToggle` is `"true"` ↔ nav is open (not collapsed)
- These invariants MUST hold after init, after every toggle, and after every resize across the 960px breakpoint

**Layout assertions:**
- A1. Desktop initial load: `#tocToggle` is `position:fixed`, reachable at viewport x=0, y=36 (left edge clickable). Confirm with `js("getComputedStyle(document.getElementById('tocToggle')).position")` returning `"fixed"`.
- A2. Desktop toggle click at (0, 36): CDP click fires, TOC changes open/closed state. Prove with before/after screenshot.
- A3. Desktop TOC closed: main content `max-width` is `calc(100vw - 4rem)` (full width minus 4rem right margin), NOT shifted left by `margin-left`. Prove with `js("getComputedStyle(document.querySelector('.main-content')).maxWidth")`.
- A4. Desktop TOC open: main content has `margin-left: var(--toc-width)` and `max-width: calc(100vw - var(--toc-width) - 4rem)`.
- A5. Mobile viewport (≤960px): `#tocToggle` has `display: flex` (not `none`). Prove with screenshot showing the button at top-left.
- A6. Mobile toggle click: TOC opens/closes without page jump. Prove with before/after screenshots.
- A7. Multiple toggle cycles: No duplicate event listeners. Confirm `getEventListeners(document.getElementById('tocToggle'))` returns exactly 1 click listener.
- A8. Theme toggle: Mermaid SVG rerenders, zoom/pan state preserved. Prove with before/after SVG transform comparison.
- A9. Console errors: Zero errors on load and after every interaction in the matrix.
- A10. No CSS class toggling without visible effect: If `body.classList.toggle('toc-hidden')` changes the class but `getComputedStyle(main).marginLeft` does not change, the test FAILS.
- A11. Resize handle: drag handle down past 800px — viewport height must not exceed 800px. Prove with `js("document.getElementById('diagramViewport').clientHeight")` returning ≤ 800 after multiple down-drags.
- A12. Resize handle: drag handle up past 200px — viewport height must not go below 200px. Prove with `js("document.getElementById('diagramViewport').clientHeight")` returning ≥ 200 after multiple up-drags.
- A13. Resize handle keyboard: ArrowDown key increases height, ArrowUp decreases. Prove with before/after `clientHeight` values differing by ~40px per press.

**Screenshot capture requirements:**
For every layout-affecting interaction (A1–A6, A8, A11, A12, A13), capture a screenshot immediately before and after. Store paths in `verification_matrix[interactionId].screenshots = {before: path, after: path}`. If a screenshot is missing, the assertion is incomplete and MUST be recorded as `false`.

**Timeout:** 120000ms for full matrix. If any individual check exceeds 30s, fail with exact stall point reported.

**Failure handling:** If any assertion fails, record `verification_matrix[row][col] = {passed: false, reason: "exact failure message", screenshots: {...}}`. The step is failed. Do not emit artifact-proof.json with `passed: true` for any incomplete matrix.

### Stage H: External Critic → `validation-report.json`

**Role: external-validator.** This role is performed by a separate LLM instance or agent that did NOT generate the HTML. The generator and validator must be distinct. Self-validation (generator = validator) is insufficient and is a blocking defect.

The validator's job is to compare the generated artifact against the declared contract and the runtime evidence, and to fail closed when evidence is missing.

**Inputs:**
- `index.html` — the generated artifact
- `source-model.json` — extracted source of truth
- `artifact-proof.json` — evidence record from Step 7 (MUST exist; if missing, fail)
- `SKILL.md` — this file, specifically the HTML Authoring Rules section

**Validator checks (all are blocking unless marked optional):**

**E1. Evidence completeness (blocking):**
- `artifact-proof.json` exists and is valid JSON
- `verification_matrix` field is present and has entries for all 9 matrix cells
- Every matrix cell has `passed: boolean` and `reason: string`
- Every layout-affecting cell has `screenshots: {before, after}` paths that exist on disk
- If any cell is missing, is `null`, or has no screenshot evidence → FAIL

**E2. TOC state model (blocking):**
- Read the actual JS initialization in index.html
- Confirm `initTocToggle` is called on DOMContentLoaded
- Confirm the click handler toggles BOTH `nav.classList.toggle('collapsed', ...)` AND `body.classList.toggle('toc-hidden', ...)` in the same synchronous branch
- If the handler toggles only one without the other → FAIL (atomicity violation)
- Confirm aria-expanded is set correctly before the handler fires (not after a race)
- Confirm the handler uses `aria-expanded === 'true'` as the source of current open state (not nav.collapsed, which is the inverse)

**E3. CSS mechanism audit (blocking):**
- Read the CSS in index.html (inline `<style>` or linked)
- Confirm there is NO `transform: translateX` on `.toc` for desktop viewports (desktop uses `left` transitions only)
- Confirm `#tocToggle` is NOT inside `nav.toc` in the DOM (must be a sibling of `.page-shell`, not a child of nav)
- Confirm `#tocToggle` is `position: fixed` with `left: 0`
- If CSS contains `display: none` on `#tocToggle` at any viewport width → FAIL
- If CSS contains `transform` on `.toc` for desktop (min-width: 961px) → FAIL

**E4. Mobile breakpoint consistency (blocking):**
- Confirm the mobile breakpoint is exactly `max-width: 960px` (not 768px, not 1024px)
- Confirm at ≤960px the toggle is `display: flex` (not `display: none`)
- Confirm at ≤960px the toggle is `position: fixed` (not relative, not absolute)
- If mobile CSS conflicts with the CSS rules in the SKILL.md HTML Authoring Rules section → FAIL

**E5. Layout width behavior (blocking):**
- Read the CSS for `.main-content`
- Confirm `body:not(.toc-hidden) .main-content` has an explicit `margin-left` equal to `var(--toc-width)`
- Confirm `body.toc-hidden .main-content` has `margin-left: 0` (not just `margin-left: 0` but also `max-width` that widens to fill)
- The reflow MUST be measurable: `getComputedStyle(main).marginLeft` changes from `var(--toc-width)` to `0` on close
- If the main content merely shifts left without changing width, this is NOT correct reflow → FAIL

**E6. Mermaid rerender on theme (blocking):**
- Confirm the theme toggle button has an `addEventListener('click', ...)` that calls `mermaid.run()` or `mermaid.initialize()` with a new theme
- Confirm viewport state (zoom level, pan offset) is saved before the rerender and restored after
- If the theme toggle does not call mermaid at all → FAIL

**E7. Fidelity to workflow model (blocking):**
- Count `section#workflow-step-*` elements in the HTML
- Compare to `source-model.json.steps.length`
- Every step in the model MUST have a corresponding section in the HTML
- Every decision_point in the model MUST have a visible representation (accordion branch or distinct section)
- Every route_out MUST have a visible section
- Missing sections → FAIL

**E8. No invented routes (blocking):**
- Scan the generated HTML for any route, gate, or terminal not present in `source-model.json`
- Any invented element → FAIL with exact element identified

**E9. Console errors (blocking):**
- If `artifact-proof.json.browser_verification.console_errors` is a non-empty array → FAIL

**E10. Anti-self-deception review (blocking):**
- If any `verification_matrix` cell has `passed: true` but `reason` is missing or generic ("ok", "works", "verified") → FAIL
- Reason field MUST contain the specific assertion that passed (e.g., "A3: maxWidth calc(100vw - 4rem) confirmed at viewport 1280×800")
- If screenshot paths in the proof do not exist on disk → FAIL

**Gate:** E1 through E10 ALL pass. Any single failure is a blocking defect. The external validator has veto authority. Do not proceed to Step 9 if any E* check fails.

**Output:** Write a `validation-report.json` to the artifacts directory with `{passed: boolean, failures: [{check: string, expected: string, actual: string, screenshot: string}], passedAt: ISO-8601}`. If passed is false, the skill run is failed.

### Stage I: Emit Proof Metadata

**Prerequisite:** All Stage E (Runtime Validator) and Stage F (External Critic) checks MUST pass before this step. If either stage failed, emit a failed proof and stop.

Emit proof metadata alongside the artifact.

#### source-model.json

Normalized extracted workflow model (see Step 2 schema). This file is the source of truth for all fidelity checks in Step 8.

#### artifact-proof.json

**MUST be generated. MUST NOT contain placeholder values.** Every field below is required. Fields marked `MUST_TEST` require runtime evidence from Step 7.

```json
{
  "skill_name": "string (from workflow model)",
  "skill_version": "string (from workflow model)",
  "source_path": "string (absolute path to SKILL.md)",
  "artifact_path": "string (absolute path to generated index.html)",
  "generated_at": "ISO-8601",
  "generator_skill_version": "2.1.0",
  "mermaid_version": "11",

  "coverage": {
    "steps_declared": "integer (from workflow model)",
    "workflow_sections_rendered": "integer (count from HTML)",
    "decision_points_detected": "integer (from workflow model)",
    "decision_points_rendered": "integer (count from HTML)",
    "route_outs_detected": "integer (from workflow model)",
    "route_outs_rendered": "integer (count from HTML)",
    "terminal_states_detected": "integer (from workflow model)",
    "terminal_states_rendered": "integer (count from HTML)"
  },

  "verification_matrix": {
    "desktop_initial": {
      "passed": "boolean (MUST_TEST — runtime assertion required)",
      "reason": "string (specific measurement, not generic)",
      "screenshots": { "before": "path", "after": "path" }
    },
    "desktop_close": {
      "passed": "boolean (MUST_TEST)",
      "reason": "string",
      "screenshots": { "before": "path", "after": "path" }
    },
    "desktop_reopen": {
      "passed": "boolean (MUST_TEST)",
      "reason": "string",
      "screenshots": { "before": "path", "after": "path" }
    },
    "desktop_resize_to_mobile": {
      "passed": "boolean (MUST_TEST)",
      "reason": "string",
      "screenshots": { "before": "path", "after": "path" }
    },
    "mobile_initial": {
      "passed": "boolean (MUST_TEST)",
      "reason": "string (must state computed display value of #tocToggle)",
      "screenshots": { "before": "path", "after": "path" }
    },
    "mobile_toggle_open": {
      "passed": "boolean (MUST_TEST)",
      "reason": "string",
      "screenshots": { "before": "path", "after": "path" }
    },
    "mobile_toggle_close": {
      "passed": "boolean (MUST_TEST)",
      "reason": "string",
      "screenshots": { "before": "path", "after": "path" }
    },
    "theme_toggle_preserves_viewport": {
      "passed": "boolean (MUST_TEST)",
      "reason": "string (must state zoom/pan state before and after)",
      "screenshots": { "before": "path", "after": "path" }
    },
    "no_console_errors": {
      "passed": "boolean",
      "reason": "string",
      "errors": []
    }
  },

  "toc_state": {
    "initial_sync": {
      "passed": "boolean (MUST_TEST — runtime assertion required)",
      "reason": "string (must quote actual values of nav.collapsed and body.toc-hidden)"
    },
    "handler_atomic": {
      "passed": "boolean (MUST_TEST — JS inspection required)",
      "reason": "string (must identify the exact toggle line)",
      "handler_lines": "string (line numbers in index.html)"
    },
    "aria_consistent": {
      "passed": "boolean (MUST_TEST)",
      "reason": "string (must quote aria-expanded value before and after toggle)"
    }
  },

  "css_contract": {
    "no_transform_on_desktop_toc": {
      "passed": "boolean (MUST_TEST — CSS audit required)",
      "reason": "string (must identify any transform rule found)"
    },
    "toggle_outside_nav": {
      "passed": "boolean (MUST_TEST — DOM inspection required)",
      "reason": "string (must confirm #tocToggle parent element)"
    },
    "toggle_mobile_display_flex": {
      "passed": "boolean (MUST_TEST)",
      "reason": "string (must quote computed display value)"
    },
    "no_mobile_display_none": {
      "passed": "boolean (MUST_TEST)",
      "reason": "string"
    },
    "main_content_reflow_measurable": {
      "passed": "boolean (MUST_TEST)",
      "reason": "string (must quote marginLeft before and after close)"
    }
  },

  "listener_integrity": {
    "toc_toggle_unique_listener": {
      "passed": "boolean (MUST_TEST)",
      "reason": "string (must state listener count)"
    }
  },

  "critic_results": {
    "mermaid_gate_passed": "boolean",
    "external_validator_passed": "boolean (MUST be from Step 8 external validator, not self-assessed)",
    "validation_report_path": "string (path to validation-report.json from Step 8)",
    "unresolved_ambiguities": []
  }
}
```

**Mandatory fields that MUST NOT be omitted or set to null:**
- `verification_matrix` (entire object)
- `toc_state` (entire object)
- `css_contract` (entire object)
- `critic_results.external_validator_passed`
- `critic_results.validation_report_path`

**If any mandatory field is missing, null, or set to a generic value like "N/A" or "not tested" → the proof is incomplete and the skill run is failed.**

**If any `passed` boolean is set to `true` without a corresponding `reason` string that contains a specific measurement or finding → treat as a false positive and fail.**

***

## HTML Authoring Rules

### CSS Rules

| Rule | Why |
|------|-----|
| No duplicate selectors | Avoid accidental overrides |
| `line-height: 0` on Mermaid container | Prevent extra whitespace below SVG |
| `max-width: 100%; height: auto; display: block; margin: 0 auto` on Mermaid SVG | Keep diagram responsive and centered in the container |
| Main layout must define explicit TOC width/state behavior | Prevent "class toggles with no visible effect" |
| Focus-visible styles required | Keyboard usability |
| Responsive rules required for mobile TOC | Desktop-only sidebars break mobile usability |
| `#tocToggle` MUST be `position: fixed; left: 0` at all widths | Toggle must be reachable at viewport edge regardless of nav state |
| `#tocToggle` MUST be `display: flex` at ≤960px | No `display: none` on mobile — button must always be visible |
| `#tocToggle` MUST be outside `nav.toc` (sibling of `.page-shell`) | Nesting inside nav.collapsed makes it disappear with the nav |
| `.toc` MUST use `left` transitions, NOT `transform`, for desktop | `transform` on ancestor breaks fixed positioning of toggle button |
| `body.toc-hidden .main-content` MUST widen to fill viewport | Reflow must be measurable via `marginLeft` change, not just class toggle |
| `pointer-events: none` MUST NOT be on `#tocToggle` | Toggle must always be clickable |
| Exactly 3 transition timings in CSS | 140ms (snap/hover), 180ms (smooth/layout), 200ms (slow/emphasis) — no custom values |
| All CSS variables MUST have light-mode counterparts | `prefers-color-scheme: light` must redefine every `--var` used in dark mode |
| `::selection` pseudo-element MUST be defined | Text selection must use accent color, not browser default |
| Form elements MUST have explicit `line-height` | Inherited line-height from body (1.55) is too tall for inputs/buttons |
| `.diagram-shell` MUST be `display: flex; flex-direction: column` | Enables the resize handle to control viewport height via `flex-shrink: 0` on handle and `flex: 1` on viewport |
| `.diagram-resize-handle` MUST have `cursor: ns-resize` | Visual affordance that the handle is draggable vertically |

### HTML Structure

```text
button#tocToggle (sibling of page-shell, fixed position, always visible at left edge)
.page-shell (sibling, not parent of button)
  ├── nav.toc
  │     ├── .toc-header
  │     │     ├── h2 "Contents"
  │     │     └── .toc-controls
  │     │           └── button#themeToggle.toc-btn
  │     └── .toc-body
  │           └── ul > li > a (TOC links)
  └── main.main-content
        ├── section#overview (Hero)
        ├── section#facts (Quick Facts)
        ├── #searchWrap + #noResults
        ├── section#diagram (Mermaid)
        ├── .proof-summary (Verification Summary)
        ├── section#steps (Workflow Steps accordions)
        ├── section#route-outs
        ├── section#terminals
        ├── section#artifacts (Artifact cards)
        └── section#proof (Proof metadata)
```

**Theme toggle placement:** The theme toggle button lives inside the TOC sidebar's header controls (`.toc-controls`), not as a fixed-position element. This avoids fixed-position overlap issues and groups related controls in one place.

**Sidebar close behavior:** When the TOC is hidden, `.main-content` expands to fill the full available width via `max-width: calc(100vw - 4rem)` rather than simply shifting left. The `.page-shell` uses flexbox to achieve this without position:fixed tricks.

**Semantic HTML requirement (BLOCKING):**
Generated HTML must use semantic elements. Minimum requirements:
- `<main>` — exactly one per page, wraps the primary content
- `<nav aria-label="Table of contents">` — the TOC sidebar
- `<section>` — major content divisions (overview, facts, diagram, steps, route-outs, terminals, artifacts, proof)
- `<article>` — each workflow step accordion item
- `<header>` — page header (inside hero), TOC header
- Semantic element ratio MUST be ≥ 15% of all div-like elements (`<div>`, `<span>` count as non-semantic)

Every `<button>` without visible text label MUST have `aria-label`. Every icon-only control MUST have `aria-label` and `title`.

### Mermaid CDN (ESM only)

```html
<script type="module">
  import mermaid from 'https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.esm.min.mjs';
</script>
```

Never use local split Mermaid ESM bundles.

### Side Panel / TOC Contract (MANDATORY)

This section is the **binding CSS/JS/DOM specification** for all generated documentation pages that include a TOC. All rules here are MUST/MUST NOT. No exceptions.

#### Canonical TOC State Model

The TOC has exactly two visible states:

| State | nav.classList | body.classList | aria-expanded |
|-------|---------------|----------------|---------------|
| OPEN  | no `collapsed` | no `toc-hidden` | `"true"` |
| CLOSED | has `collapsed` | has `toc-hidden` | `"false"` |

**Required invariant (MUST hold at all times):**
```
nav.classList.contains('collapsed') === body.classList.contains('toc-hidden')
```
These two classes are always the same value. If they ever differ, the toggle is inverted and the page is broken.

**Inverse representation:**
`aria-expanded === 'true'` means OPEN. `aria-expanded === 'false'` means CLOSED.
`nav.classList.contains('collapsed')` means CLOSED (the class name is the *opposite* of the visible state).

#### Required DOM Structure

```html
<!-- #tocToggle is a SIBLING of .page-shell, NOT inside nav.toc -->
<!-- This is the only supported structure — variations are not permitted -->

<button id="tocToggle"
        aria-label="Toggle table of contents"
        title="Toggle TOC"
        aria-expanded="true">
  ☰
</button>

<div class="page-shell">
  <nav id="toc" class="toc" aria-label="Table of contents">
    <div class="toc-header">
      <h2>Contents</h2>
      <div class="toc-controls">
        <button id="themeToggle" class="toc-btn" title="Toggle theme">🌙</button>
      </div>
    </div>
    <div class="toc-body">
      <!-- TOC links -->
    </div>
  </nav>

  <main class="main-content">
    <!-- page content -->
  </main>
</div>
```

**MUST NOT** nest `#tocToggle` inside `nav.toc` or any child of `nav.toc`. The toggle button must be a sibling of `.page-shell`.

#### Required JS Behavior

```javascript
window.initTocToggle = function() {
  const btn = document.getElementById('tocToggle');
  const toc = document.getElementById('toc');
  if (!btn || !toc) return;

  // Initialize: derive state from DOM, reconcile mismatches
  const isMobile = window.matchMedia('(max-width: 960px)').matches;
  const navIsCollapsed = toc.classList.contains('collapsed');

  // Enforce invariant: if nav and body disagree on initial state, correct body to match nav
  if (navIsCollapsed) {
    document.body.classList.add('toc-hidden');
  } else {
    document.body.classList.remove('toc-hidden');
  }
  btn.setAttribute('aria-expanded', navIsCollapsed ? 'false' : 'true');

  // Toggle handler: MUST toggle both atomically
  btn.addEventListener('click', () => {
    const isExpanded = btn.getAttribute('aria-expanded') === 'true';
    // isExpanded=true means currently open → close it (add collapsed class)
    toc.classList.toggle('collapsed', isExpanded);
    document.body.classList.toggle('toc-hidden', isExpanded);
    btn.setAttribute('aria-expanded', String(!isExpanded));
  });
};
```

**Atomicity rule (MUST be enforced):** Every click handler that toggles the TOC MUST toggle BOTH `nav.classList` AND `body.classList` in the same synchronous block. Toggling only one without the other is a blocking defect.

**MUST use `aria-expanded` as the source of truth for open state** inside the handler, not `nav.classList.contains('collapsed')`. The class and the attribute are inverses of each other; using the wrong one causes inverted toggle behavior.

#### Required CSS Behavior

**Desktop (viewport width ≥ 961px):**

```css
:root { --toc-width: 18rem; }

html { overflow-x: hidden; }   /* clip collapsed TOC at left edge */
body { overflow-x: hidden; }   /* redundant safety for all browsers */

.page-shell { display: flex; min-height: 100vh; }

.toc {
  position: fixed;
  top: 0; left: 0;
  width: var(--toc-width);
  height: 100vh;
  z-index: 100;
  transition: left 180ms ease, opacity 180ms ease;
}
.toc.collapsed {
  left: calc(-1 * var(--toc-width) + 40px); /* 40px tab remains visible at edge */
  opacity: 0;
  pointer-events: none;
}

#tocToggle {
  position: fixed;
  top: 1rem; left: 0;
  z-index: 200;
  width: 2.5rem; height: 2.5rem;
  border-radius: 0 8px 8px 0;
  cursor: pointer;
  display: flex; align-items: center; justify-content: center;
}
/* Button is ALWAYS at viewport left edge — clickable at x=0 regardless of TOC state */

.main-content {
  flex: 1;
  margin-left: var(--toc-width);
  max-width: calc(100vw - var(--toc-width) - 4rem);
  transition: margin-left 180ms ease, max-width 180ms ease;
}
body.toc-hidden .main-content {
  margin-left: 0;
  max-width: calc(100vw - 4rem); /* expands to fill viewport when TOC is hidden */
}
```

**Mobile (viewport width ≤ 960px):**

```css
@media (max-width: 960px) {
  .toc {
    /* Use left transitions for consistency with desktop.
       Do NOT use transform: translateX — it creates a new containing block
       that makes position:fixed children behave as position:absolute,
       breaking the toggle button's fixed positioning. */
    left: 0 !important;               /* override the desktop left value */
    transform: none !important;       /* explicitly remove any transform */
    transition: left 180ms ease, opacity 180ms ease;
  }
  .toc.collapsed {
    left: -100% !important;            /* off-screen: completely hidden */
    opacity: 1;
  }

  #tocToggle {
    display: flex !important;         /* MUST be visible on mobile — no exceptions */
    left: 0 !important;
    top: 0.75rem !important;
    position: fixed !important;       /* MUST remain fixed on mobile */
  }

  .main-content {
    margin-left: 0 !important;
    max-width: calc(100vw - 4rem) !important;
  }
  body.toc-hidden .main-content {
    max-width: calc(100vw - 4rem) !important;
  }
}
```

#### CSS MUST NOT Rules

The following are **blocking defects** if violated in generated HTML:

1. **MUST NOT** use `display: none` on `#tocToggle` at any viewport width
2. **MUST NOT** nest `#tocToggle` inside `nav.toc` or any child of `nav`
3. **MUST NOT** use `transform: translateX` on `.toc` for desktop viewports (≥961px)
4. **MUST NOT** use `position: relative` on `#tocToggle` — it must be `position: fixed`
5. **MUST NOT** apply `pointer-events: none` to `#tocToggle` at any time
6. **MUST NOT** use `transition: transform` on `.toc` unless specifically handling mobile-only off-canvas behavior with a separately-verified toggle button

#### Canonical Mechanism (Single Source of Truth)

**Desktop and mobile share the same `left`-based transition mechanism.** The toggle button is always `position: fixed` at `left: 0`. The nav uses `left: 0` when open and `left: -100%` when closed.

**Rationale:** `transform` on an ancestor creates a new containing block, causing all `position: fixed` descendants to become `position: absolute` relative to that ancestor. This breaks the toggle button's fixed positioning relative to the viewport. Using `left` transitions avoids this pitfall entirely.

If a future implementation needs off-canvas animation on mobile, it MUST:
1. Keep `#tocToggle` outside and independent of the nav's positioning context
2. Verify with a runtime assertion that the button remains fixed and reachable after the nav is closed

#### Initialization Contract

At page load, before any user interaction:

1. `initTocToggle()` MUST be called on `DOMContentLoaded`
2. The JS MUST reconcile `body.classList` with the actual `nav.classList` state — if they disagree, body is corrected to match nav
3. `aria-expanded` is set to match the actual open/closed state of the nav
4. After init, the invariant `nav.classList.contains('collapsed') === body.classList.contains('toc-hidden')` MUST be true

#### Verification Contract

Every generated page MUST have runtime verification (Step 7) that confirms:

- `getComputedStyle(document.getElementById('tocToggle')).position === 'fixed'` at desktop viewport
- `getComputedStyle(document.getElementById('tocToggle')).display !== 'none'` at mobile viewport
- `getComputedStyle(document.querySelector('.main-content')).marginLeft` changes when the toggle is clicked
- No `transform: translateX` rule applies to `.toc` at desktop viewport

### Search UI (MANDATORY)

Artifacts MUST include client-side search across:

- section titles
- step names
- routing labels
- terminal states
- code/pre blocks where practical

Minimum behavior:
- input field
- incremental filtering/highlighting
- "no results" state
- clear button

### TOC / Section Deep-linking (MANDATORY)

- Every major section MUST have a stable `id`
- TOC links MUST target those IDs
- Hash navigation MUST scroll correctly
- Opening a deep link to a collapsed step MUST reveal that step

### Reset Button (mandatory)

Every Mermaid diagram with zoom controls MUST include reset.

### DOMContentLoaded + Module Script Timing

Module scripts are deferred. Initialization order MUST be explicit and deterministic.

### JS Lifecycle Rules (MANDATORY)

1. Never bind interaction listeners to Mermaid-generated SVG nodes.
2. Always `await mermaid.run()` before querying SVG or applying transforms.
3. Theme rerenders MUST preserve viewport state.
4. Per-diagram viewport state MUST live in a stable object keyed by diagram ID.
5. Wheel handlers MUST use `{ passive: false }`.
6. **Every async operation MUST have try/catch.** `navigator.clipboard.writeText`, `fetch`, `fetch` analogues — no unhandled promise rejection. Uncaught errors from async operations block the run.
7. **setTimeout/setInterval MUST be cleared on beforeunload or use AbortController.** Leak-prone timers are a blocking defect.
8. **No direct DOM mutation inside loops.** All `forEach`/`for` loops that append/mutate DOM nodes must use `DocumentFragment` or `requestAnimationFrame` to batch changes into a single reflow. Violation → blocking fail.
9. **All scroll/touch listeners MUST use `{ passive: true }` unless `preventDefault` is required.** Non-passive listeners block scroll performance.
10. **All interactive elements MUST be keyboard-accessible.** Accordion triggers need `role="button"` and `tabindex="0"` with Enter/Space keydown handlers. TOC links need `tabindex` management. Missing keyboard access → blocking fail.
11. **tocIsOpen state variable MUST be the single authoritative source of TOC open/closed state.** Toggle handler must flip state first, then call `applyTocState()` — never toggle directly in the click handler without a state variable.

### Advanced Viewport Mode (REQUIRED for dense diagrams)

Use advanced viewport mode for dense or multi-diagram pages.

**MUST include:**
- drag-to-pan
- cursor-centric wheel zoom
- zoom buttons
- reset
- persistent viewport state across rerenders

### Regression-Prevention Checklist

**These rules are MUST/MUST NOT. Violation of any rule blocks the artifact from being marked "verified".**

**TOC / Sidebar:**
- [ ] `#tocToggle` is a sibling of `.page-shell`, never nested inside `nav.toc`
- [ ] Toggle button is `position: fixed; left: 0` at all viewport widths
- [ ] No `display: none` on `#tocToggle` at any breakpoint
- [ ] `nav.classList.contains('collapsed') === body.classList.contains('toc-hidden')` at all times after init
- [ ] Toggle handler updates both `nav.classList` AND `body.classList` atomically
- [ ] `aria-expanded` reflects open state (not the collapsed class)
- [ ] Desktop uses `left` transitions only — no `transform` on `.toc` at viewport ≥961px
- [ ] Mobile uses `left: -100%` for off-canvas, not `transform: translateX(-100%)`

**Main Content Reflow:**
- [ ] `body:not(.toc-hidden) .main-content` has explicit `margin-left: var(--toc-width)`
- [ ] `body.toc-hidden .main-content` has `margin-left: 0` and `max-width` widened to fill viewport
- [ ] Reflow is measurable via `getComputedStyle().marginLeft` change, not just visual class toggle
- [ ] No layout shift animation on main content that does not also change the margin

**Mobile:**
- [ ] Breakpoint is exactly `max-width: 960px`
- [ ] Toggle is `display: flex` (visible) at ≤960px
- [ ] Toggle is `position: fixed` at ≤960px
- [ ] `pointer-events: none` on collapsed nav does NOT block the toggle button
- [ ] Resize from desktop to mobile preserves toggle visibility and position

**Proof Metadata:**
- [ ] `artifact-proof.json` exists and all fields are non-null
- [ ] No field uses "N/A", "not tested", or placeholder values
- [ ] `external_validator_passed` reflects actual Step 8 external validator result
- [ ] `validation_report_path` points to an existing file from the external validator
- [ ] `verification_matrix` has all 9 cells filled with `passed`, `reason`, and `screenshots`

**Anti-Self-Deception:**
- [ ] Generator and external validator are distinct LLM instances
- [ ] DOM class presence is NOT treated as proof of visible behavior
- [ ] Expected CSS is NOT treated as proof of actual rendered CSS
- [ ] Missing screenshots are NOT treated as passed tests
- [ ] Generic "ok" reasons are flagged as insufficient evidence

**Language:**
- [ ] Blocking sections use MUST/MUST NOT — no "should", "preferred", "where practical" in enforceable requirements
- [ ] Every "verify" in a mandatory check is followed by an explicit "how to verify" (a specific assertion or measurement)
- [ ] No prose check that cannot be mapped to a pass/fail boolean with a reason

***

## Output Requirements

Each stage emits its own JSON artifact. The final `index.html` is the only non-JSON output.

| Stage | Output | Consumed by |
|-------|--------|-------------|
| Stage A | `source-model.json` | Stages B, D, F |
| Stage B | `artifact-plan.json` | Stages C, E |
| Stage C | `diagram.mmd` | Stage D |
| Stage D | (critic gate) | blocks E if failed |
| Stage E | `index.html` | Stages F, G, H |
| Stage F | `static-validation.json` | (gate — blocks G if failed) |
| Stage G | `artifact-proof.json` | Stage H |
| Stage H | `validation-report.json` | blocks Stage I if failed |
| Stage I | (proof metadata) | final output |

Required artifact: `index.html` (next to target skill's SKILL.md)

Recommended artifacts:
- `source-model.json` (`.claude/.artifacts/{terminal_id}/doc-compiler/{target}/`)
- `artifact-plan.json` (same directory)
- `static-validation.json` (same directory)
- `diagram.mmd` (same directory)
- `artifact-proof.json` (same directory)
- `validation-report.json` (same directory)

***

## Routing Policy for doc-compiler Pipeline

**Rule 1 — JSON chain, no backdoors.**
Each stage receives exactly one JSON input and produces exactly one JSON output. No stage may read the source `SKILL.md` after Stage A. Content flows only forward.

**Rule 2 — Template-only HTML emission.**
Stage E produces HTML only by applying `artifact-plan.json` to a fixed HTML template. It must not infer, copy, or synthesize prose content from any other source.

**Rule 3 — Generator ≠ Validator.**
Stage E and Stage H must be performed by separate LLM instances. Self-validation (same LLM generating and validating) is a blocking defect.

**Rule 4 — Static gate before runtime.**
Stage F must complete and pass before Stage G begins. Runtime testing must not proceed on a structurally invalid artifact.

**Rule 5 — Screenshot evidence for all layout-affecting interactions.**
Every matrix cell in Stage E that affects layout requires a before/after screenshot. Missing screenshots are treated as failed assertions.

**Rule 6 — No generic reasons in proof.**
Every `passed: true` cell in `artifact-proof.json.verification_matrix` must have a `reason` field containing a specific measurement. Generic strings ("ok", "verified", "works") are treated as false positives and block the run.

**Rule 7 — External critic has veto authority.**
Stage F's `validation-report.json` determines whether proof metadata is emitted. If Stage F fails, no proof is emitted and the skill run is marked failed.

***

## Integration with skill-craft

skill-craft invokes `/doc-compiler` during EXECUTING when HTML output is needed:

```bash
/doc-compiler <target-skill>
```

The `skill-craft` HTML guidance should be reduced to:

> Delegate all HTML artifact generation to `/doc-compiler`.

This keeps HTML generation centralized, reusable, and verifiable.
