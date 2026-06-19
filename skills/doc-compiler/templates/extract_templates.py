#!/usr/bin/env python3
"""Extract index.html into named template skeleton files."""
import re, os

BASE = "P:/packages/cc-skills-meta/skills/doc-compiler"
TPL = f"{BASE}/templates"
os.makedirs(TPL, exist_ok=True)

with open(f"{BASE}/index.html", "r") as f:
    content = f.read()

# ── Extract major blocks ───────────────────────────────────────────────────
style_match = re.search(r'<style>\s*(.*?)\s*</style>', content, re.DOTALL)
script_match = re.search(r'<script type="module">\s*(.*?)\s*</script>', content, re.DOTALL)
css = style_match.group(1)
js = script_match.group(1)

# ── CSS: split by section comments ────────────────────────────────────────
def split_css(css_text):
    parts = re.split(r'\n\s*/\* ── .*? ─{3,}\s*\*/\n', css_text)
    result = {}
    for part in parts:
        part = part.strip()
        if not part:
            continue
        # Extract section name from the /* ── Name ─── */ comment at the start
        m = re.match(r'/\* ── ([^─]+)', part)
        if m:
            key = m.group(1).strip()
            # Find the closing */ of the comment header line, then strip everything before it
            end_comment = part.find('*/', m.end())
            if end_comment != -1:
                content = part[end_comment + 2:].strip()
            else:
                content = part[m.end():].strip()
        else:
            # Non-section part (e.g. 'html { overflow-x: hidden; }' base rules)
            # Use the first line as key (truncated to 30 for readability)
            key = part.split('\n')[0].strip()[:30]
        # Strip the comment line from section content (leave base rules as-is)
        if not m:
            result[key] = part
        else:
            result[key] = content
    return result

css_secs = split_css(css)

def css_join(*keys):
    return "\n\n".join(css_secs.get(k, '') for k in keys)

# 1. shared-css.css ─────────────────────────────────────────────────────────
shared_css = css_join(
    'Variables',
    '@media (prefers-color-scheme: ',
    'html { overflow-x: hidden; }',
    '::selection { background-color',
    'button, input, select, textare',
    'h1 { font-size: clamp(1.9rem, ',
)
with open(f"{TPL}/shared-css.css", "w") as f:
    f.write(shared_css)
print(f"✓ shared-css.css  ({len(shared_css)} chars)")

# 2. toc-css.css ────────────────────────────────────────────────────────────
with open(f"{TPL}/toc-css.css", "w") as f:
    f.write(css_secs.get('.toc {', ''))
print(f"✓ toc-css.css  ({len(css_secs.get('.toc {', ''))} chars)")

# 3. section-css.css ───────────────────────────────────────────────────────
section_css = css_join(
    'section, .card, .panel {',
    '.hero {',
    '.quick-facts {',
    'pre {',
    '.copy-btn {',
    '.proof-summary {',
    '.step {',
    '.gate-badge {',
    '.label-row {',
    '.artifact-card {',
    '.card-grid {',
    '#searchWrap { display: flex; g',
    ':target {',
    '@media (max-width: 960px) {',
)
with open(f"{TPL}/section-css.css", "w") as f:
    f.write(section_css)
print(f"✓ section-css.css  ({len(section_css)} chars)")

# 4. diagram-css.css ────────────────────────────────────────────────────────
with open(f"{TPL}/diagram-css.css", "w") as f:
    f.write(css_secs.get('.diagram-shell {', ''))
print(f"✓ diagram-css.css  ({len(css_secs.get('.diagram-shell {', ''))} chars)")

# 5. mermaid-palettes.json ────────────────────────────────────────────────
start = js.find("const PALETTES = {")
# Find the closing }; that's followed by \n\n    function isLightMode
# (first }; after PALETTES = { is isLightMode closing, not PALETTES)
end_pattern = js.find('\n\n    function isLightMode', start)
end = end_pattern + 2  # position after the ;
pal_js = js[start:end]
# Convert JS object literal to pure JSON:
# 1. Remove 'const PALETTES = ' prefix
pal_json = re.sub(r'^const PALETTES = ', '', pal_js)
# 2. Quote unquoted keys (keys before colons that aren't already quoted)
pal_json = re.sub(r'(\w+):', r'"\1":', pal_json)
# 3. Convert single-quoted string values to double-quoted
pal_json = re.sub(r"'([^']*)'", r'"\1"', pal_json)
# 4. Convert camelCase strokeWidth to snake_case stroke_width
pal_json = re.sub(r'strokeWidth', 'stroke_width', pal_json)
# 5. Remove trailing commas before closing braces
pal_json = re.sub(r',(\s*[}])', r'\1', pal_json)
# 6. Remove the JavaScript trailing semicolon after the closing brace
pal_json = re.sub(r'\}\s*;\s*$', '}', pal_json, flags=re.MULTILINE)
# Fallback: also handle case where the regex above didn't catch it
pal_json = pal_json.strip()
if pal_json.endswith('};'):
    pal_json = pal_json[:-2].strip()
with open(f"{TPL}/mermaid-palettes.json", "w") as f:
    f.write(pal_json)
print(f"✓ mermaid-palettes.json  ({len(pal_json)} chars)")

# ── HTML: split by section comments ──────────────────────────────────────
# Find section comment boundaries in body
body_match = re.search(r'<body>(.*)</body>', content, re.DOTALL)
body = body_match.group(1)
# body_sections split by HTML comment markers like <!-- Hero -->
def split_body(body_text):
    parts = re.split(r'\n\s*<!-- [^-]+ -->', body_text)
    result = {}
    for part in parts:
        part = part.strip()
        if not part:
            continue
        first = part.split('\n')[0].strip()[:30]
        result[first] = part
    return result

body_secs = split_body(body)

# 6. base-shell.html ───────────────────────────────────────────────────────
# DOCTYPE + head (no style) + tocToggle button + page-shell wrapper
body_start = content.find('<body>')
shell_head = content[:body_start]
shell_head = re.sub(r'<style>.*?</style>\s*', '', shell_head, flags=re.DOTALL)
# button#tocToggle
toc_toggle_m = re.search(r'<button id="tocToggle"[^>]*>.*?</button>', content, re.DOTALL)
toc_toggle_html = toc_toggle_m.group(0) if toc_toggle_m else ''
# .page-shell wrapper
page_shell_m = re.search(r'<div class="page-shell">.*?</div><!-- .page-shell -->', body, re.DOTALL)
page_shell_html = page_shell_m.group(0) if page_shell_m else ''
base_shell = shell_head + '\n' + toc_toggle_html + '\n' + page_shell_html + '\n'
with open(f"{TPL}/base-shell.html", "w") as f:
    f.write(base_shell)
print(f"✓ base-shell.html  ({len(base_shell)} chars)")

# 7. toc.html ──────────────────────────────────────────────────────────────
toc_m = re.search(r'<nav id="toc"[^>]*>.*?</nav>', body, re.DOTALL)
toc_html = toc_m.group(0) if toc_m else ''
with open(f"{TPL}/toc.html", "w") as f:
    f.write(toc_html)
print(f"✓ toc.html  ({len(toc_html)} chars)")

# 8. mermaid-panel.html ────────────────────────────────────────────────────
diag_key = [k for k in body_secs if 'diagram' in k.lower()]
diag_html = body_secs.get(diag_key[0], '') if diag_key else ''
with open(f"{TPL}/mermaid-panel.html", "w") as f:
    f.write(diag_html)
print(f"✓ mermaid-panel.html  ({len(diag_html)} chars)")

# 9. hero.html ─────────────────────────────────────────────────────────────
hero_key = [k for k in body_secs if 'overview' in k.lower() or 'hero' in k.lower()]
hero_html = body_secs.get(hero_key[0], '') if hero_key else ''
with open(f"{TPL}/hero.html", "w") as f:
    f.write(hero_html)
print(f"✓ hero.html  ({len(hero_html)} chars)")

# 10. facts.html ───────────────────────────────────────────────────────────
facts_key = [k for k in body_secs if 'facts' in k.lower()]
facts_html = body_secs.get(facts_key[0], '') if facts_key else ''
with open(f"{TPL}/facts.html", "w") as f:
    f.write(facts_html)
print(f"✓ facts.html  ({len(facts_html)} chars)")

# 11. steps-accordion.html ─────────────────────────────────────────────────
steps_key = [k for k in body_secs if 'steps' in k.lower()]
steps_html = body_secs.get(steps_key[0], '') if steps_key else ''
with open(f"{TPL}/steps-accordion.html", "w") as f:
    f.write(steps_html)
print(f"✓ steps-accordion.html  ({len(steps_html)} chars)")

# 12. route-outs.html ─────────────────────────────────────────────────────
route_key = [k for k in body_secs if 'route' in k.lower()]
route_html = body_secs.get(route_key[0], '') if route_key else ''
with open(f"{TPL}/route-outs.html", "w") as f:
    f.write(route_html)
print(f"✓ route-outs.html  ({len(route_html)} chars)")

# 13. terminals.html ────────────────────────────────────────────────────────
term_key = [k for k in body_secs if 'terminal' in k.lower()]
term_html = body_secs.get(term_key[0], '') if term_key else ''
with open(f"{TPL}/terminals.html", "w") as f:
    f.write(term_html)
print(f"✓ terminals.html  ({len(term_html)} chars)")

# 14. artifacts.html ────────────────────────────────────────────────────────
art_key = [k for k in body_secs if 'artifact' in k.lower()]
art_html = body_secs.get(art_key[0], '') if art_key else ''
with open(f"{TPL}/artifacts.html", "w") as f:
    f.write(art_html)
print(f"✓ artifacts.html  ({len(art_html)} chars)")

# 15. proof-summary.html ──────────────────────────────────────────────────
proof_key = [k for k in body_secs if 'proof' in k.lower()]
proof_html = body_secs.get(proof_key[0], '') if proof_key else ''
with open(f"{TPL}/proof-summary.html", "w") as f:
    f.write(proof_html)
print(f"✓ proof-summary.html  ({len(proof_html)} chars)")

# ── JS: split by section comments ─────────────────────────────────────────
# Section boundaries in JS:
# 1. import mermaid
# 2. // ── Palette definitions ──────────────────────────────────────────
# 3. // ── Mermaid init & render ────────────────────────────────────────
# 4. // ── Zoom / pan via CSS transform ─────────────────────────────────
# 5. // ── Palette selector ────────────────────────────────────────────────
# 6. // ── Init ───────────────────────────────────────────────────────────

def split_js(js_text):
    parts = re.split(r'\n\s*// ── [^\n]+\n', js_text)
    return parts  # [import, PALETTES, initMermaid, zoomPan, palette, init]

js_parts = split_js(js)
print(f"\nJS parts: {len(js_parts)}")

# 16. shared-scripts.js ───────────────────────────────────────────────────
# Part 0: import
# Part 1: PALETTES
# Part 2: initMermaid + renderMermaid
# Part 3: zoom/pan + resize
# Part 4: palette selector
# Part 5: init (copy, TOC, accordion, search, theme, initTocToggle call)

# Shared = init code (part 5) EXCEPT the theme-toggle which calls renderMermaid
# We also include isLightMode, getActivePalette, buildClassDefs because
# theme-toggle uses them and they don't depend on mermaid module
init_part = js_parts[5].strip() if len(js_parts) > 5 else ''

# Remove renderMermaid call from theme toggle, replace with dispatchEvent
# The theme toggle in part 5 calls renderMermaid(true) - we replace with custom event
init_shared = re.sub(
    r'renderMermaid\(true\);',
    "document.dispatchEvent(new CustomEvent('theme-toggle', {bubbles: true}));",
    init_part
)

# Also remove the isLightMode / getActivePalette / buildClassDefs calls from part 2
# But keep those function DEFINITIONS in shared (not in diagram)
# Part 2 starts with initMermaid/renderMermaid; helpers are at the END of part 1
# Extract helpers from the END of part 1 (last lines before // ── Mermaid init...)
part1_lines = js_parts[1].strip().split('\n')
# Find the FIRST function line in part 1 (isLightMode, getActivePalette, buildClassDefs)
helper_start = 0
for i, line in enumerate(part1_lines):
    if line.strip().startswith('function '):
        helper_start = i
        break
palette_helpers = '\n'.join(part1_lines[helper_start:])

# Build shared-scripts.js = palette_helpers + init_part (with renderMermaid replaced)
shared_js = (palette_helpers + '\n\n' + init_shared).strip()
with open(f"{TPL}/shared-scripts.js", "w") as f:
    f.write(shared_js)
print(f"✓ shared-scripts.js  ({len(shared_js)} chars)")

# 17. diagram-scripts.js ──────────────────────────────────────────────────
# Parts 0 (import) + part 1 (PALETTES with helpers stripped) + part 2 (initMermaid + renderMermaid)
# + part 3 (zoom/pan) + part 4 (palette selector) + init calls
diagram_js = (
    js_parts[0].strip() + '\n\n' +  # import mermaid
    js_parts[1].strip() + '\n\n' +  # PALETTES (full, helpers included)
    js_parts[2].strip() + '\n\n' +  # initMermaid + renderMermaid
    js_parts[3].strip() + '\n\n' +  # zoom/pan
    js_parts[4].strip() + '\n\n' +  # palette selector
    'initMermaid();\n' +
    'renderMermaid();\n' +
    '// Re-render on theme toggle (fired from shared-scripts)\n' +
    "document.addEventListener('theme-toggle', () => { renderMermaid(true); });"
)
with open(f"{TPL}/diagram-scripts.js", "w") as f:
    f.write(diagram_js)
print(f"✓ diagram-scripts.js  ({len(diagram_js)} chars)")

print("\nAll templates extracted.")
