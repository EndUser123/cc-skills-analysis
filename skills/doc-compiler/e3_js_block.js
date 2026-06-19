const PALETTES = {
  "dark": {
    "step": {
      "fill": "#0f172a",
      "stroke": "#60a5fa",
      "color": "#f0f9ff",
      "stroke_width": 2.5
    },
    "gate": {
      "fill": "#1e1b4b",
      "stroke": "#fbbf24",
      "color": "#fef3c7",
      "stroke_width": 3
    },
    "terminal": {
      "fill": "#064e3b",
      "stroke": "#10b981",
      "color": "#f0fdf4",
      "stroke_width": 3
    },
    "routeOut": {
      "fill": "#3f0f5c",
      "stroke": "#d946ef",
      "color": "#faf5ff",
      "stroke_width": 2
    },
    "start": {
      "fill": "#172554",
      "stroke": "#818cf8",
      "color": "#c7d2fe",
      "stroke_width": 3
    }
  },
  "light": {
    "step": {
      "fill": "#f0f9ff",
      "stroke": "#0369a1",
      "color": "#0f172a",
      "stroke_width": 2.5
    },
    "gate": {
      "fill": "#fffbeb",
      "stroke": "#b45309",
      "color": "#78350f",
      "stroke_width": 3
    },
    "terminal": {
      "fill": "#f0fdf4",
      "stroke": "#047857",
      "color": "#064e3b",
      "stroke_width": 3
    },
    "routeOut": {
      "fill": "#faf5ff",
      "stroke": "#6d28d9",
      "color": "#3f0f5c",
      "stroke_width": 2
    },
    "start": {
      "fill": "#dbeafe",
      "stroke": "#1e40af",
      "color": "#172554",
      "stroke_width": 3
    }
  }
};

function isLightMode() {
      return window.matchMedia('(prefers-color-scheme: light)').matches;
    }

    function getActivePalette(paletteName) {
      const saved = localStorage.getItem('mermaid-palette') || 'tailwind-modern';
      const name = paletteName || saved;
      const palette = PALETTES[name] ? name : 'tailwind-modern';
      const mode = isLightMode() ? 'light' : 'dark';
      return PALETTES[palette][mode];
    }

    function buildClassDefs(palette) {
      return Object.entries(palette).map(([cls, vals]) =>
        `classDef ${cls} fill:${vals.fill},stroke:${vals.stroke},color:${vals.color},stroke-width:${vals.strokeWidth}`
      ).join('\n    ');
    }

initMermaid();
    renderMermaid();

    // Re-render when OS theme changes
    window.matchMedia('(prefers-color-scheme: light)').addEventListener('change', () => {
      document.dispatchEvent(new CustomEvent('theme-toggle', {bubbles: true}));
    });

    // Copy buttons on <pre> blocks — create all in memory first, then batch-append
    const copyPairs = [];
    document.querySelectorAll('pre').forEach(pre => {
      if (pre.querySelector('.copy-btn')) return;
      const btn = document.createElement('button');
      btn.className = 'copy-btn';
      btn.type = 'button';
      btn.textContent = 'Copy';
      btn.setAttribute('aria-label', 'Copy code block');
      const capturePre = pre;
      btn.addEventListener('click', async () => {
        try {
          await navigator.clipboard.writeText(capturePre.innerText);
          btn.textContent = 'Copied!';
          btn.classList.add('copied');
          const t = setTimeout(() => { btn.textContent = 'Copy'; btn.classList.remove('copied'); }, 1200);
          window.addEventListener('beforeunload', () => clearTimeout(t), { once: true });
        } catch (err) {
          console.error('Clipboard write failed:', err);
          btn.textContent = 'Copy failed';
        }
      });
      copyPairs.push({ pre, btn });
    });
    copyPairs.forEach(({ pre, btn }) => pre.parentNode.insertBefore(btn, pre.nextSibling));

    // Hash tracking for :target
    if (window.location.hash) {
      const el = document.querySelector(window.location.hash);
      if (el) {
        const t = setTimeout(() => el.scrollIntoView({ behavior: 'smooth' }), 100);
        window.addEventListener('beforeunload', () => clearTimeout(t), { once: true });
      }
    }

    // TOC toggle — single state variable, idempotent
    window.initTocToggle = function() {
      const btn = document.getElementById('tocToggle');
      const toc = document.getElementById('toc');
      const main = document.querySelector('.main-content');
      if (!btn || !toc || !main) return;

      let tocIsOpen = window.matchMedia('(min-width: 961px)').matches; // open on desktop, closed on mobile

      function applyTocState() {
        if (tocIsOpen) {
          toc.classList.remove('collapsed');
          document.body.classList.remove('toc-hidden');
          main.classList.remove('toc-closed');
          main.classList.add('toc-open');
          btn.setAttribute('aria-expanded', 'true');
        } else {
          toc.classList.add('collapsed');
          document.body.classList.add('toc-hidden');
          main.classList.remove('toc-open');
          main.classList.add('toc-closed');
          btn.setAttribute('aria-expanded', 'false');
        }
      }

      applyTocState();

      btn.addEventListener('click', () => {
        tocIsOpen = !tocIsOpen; // flip state first
        applyTocState();         // then apply once
      });
    };

    // Accordion — keyboard accessible
    window.toggleStep = function(header) {
      const step = header.closest('.step');
      step.classList.toggle('open');
    };

    // Add keyboard support to accordion triggers
    document.querySelectorAll('.step-header').forEach(header => {
      header.setAttribute('role', 'button');
      header.setAttribute('tabindex', '0');
      header.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          window.toggleStep(header);
        }
      });
    });

    // Copy path
    window.copyPath = async function(btn, text) {
      try {
        await navigator.clipboard.writeText(text);
        btn.textContent = 'Copied!';
        btn.classList.add('copied');
        const t = setTimeout(() => { btn.textContent = 'Copy'; btn.classList.remove('copied'); }, 1500);
        window.addEventListener('beforeunload', () => clearTimeout(t), { once: true });
      } catch (err) {
        console.error('Clipboard write failed:', err);
        btn.textContent = 'Copy failed';
      }
    };

    // Search
    const searchInput = document.getElementById('searchInput');
    const clearBtn = document.getElementById('clearSearch');
    const noResults = document.getElementById('noResults');
    const allSteps = document.querySelectorAll('.step');
    searchInput.addEventListener('input', () => {
      const q = searchInput.value.toLowerCase();
      let visible = 0;
      allSteps.forEach(s => {
        const text = s.textContent.toLowerCase();
        const show = text.includes(q);
        s.style.display = show ? '' : 'none';
        if (show) visible++;
      });
      noResults.classList.toggle('show', visible === 0 && q.length > 0);
    });
    clearBtn.addEventListener('click', () => {
      searchInput.value = '';
      allSteps.forEach(s => s.style.display = '');
      noResults.classList.remove('show');
    });

    // Theme toggle
    let userToggledLight = null;
    document.getElementById('themeToggle').addEventListener('click', () => {
      const root = document.documentElement;
      const isDark = root.style.getPropertyValue('--bg') === '#0f1115' || root.style.getPropertyValue('--bg') === '';
      if (isDark) {
        userToggledLight = true;
        root.style.setProperty('--bg', '#f8fafc');
        root.style.setProperty('--surface', '#ffffff');
        root.style.setProperty('--surface-2', '#f1f5f9');
        root.style.setProperty('--surface-3', '#e2e8f0');
        root.style.setProperty('--text', '#0f172a');
        root.style.setProperty('--text-muted', '#475569');
        root.style.setProperty('--text-faint', '#94a3b8');
        root.style.setProperty('--border', 'rgba(0,0,0,0.10)');
        root.style.setProperty('--border-strong', 'rgba(0,0,0,0.16)');
        root.style.setProperty('--accent', '#0369a1');
        root.style.setProperty('--accent-soft', 'rgba(3,105,161,0.12)');
        root.style.setProperty('--shadow', '0 8px 24px rgba(0,0,0,0.10)');
        document.dispatchEvent(new CustomEvent('theme-toggle', {bubbles: true}));
      } else {
        userToggledLight = false;
        root.style.setProperty('--bg', '#0f1115');
        root.style.setProperty('--surface', '#151922');
        root.style.setProperty('--surface-2', '#1b2130');
        root.style.setProperty('--surface-3', '#222a3a');
        root.style.setProperty('--text', '#e8edf5');
        root.style.setProperty('--text-muted', '#a8b3c7');
        root.style.setProperty('--text-faint', '#7e889b');
        root.style.setProperty('--border', 'rgba(255,255,255,0.10)');
        root.style.setProperty('--border-strong', 'rgba(255,255,255,0.16)');
        root.style.setProperty('--accent', '#66b3ff');
        root.style.setProperty('--accent-soft', 'rgba(102,179,255,0.14)');
        root.style.setProperty('--shadow', '0 10px 30px rgba(0,0,0,0.22)');
        document.dispatchEvent(new CustomEvent('theme-toggle', {bubbles: true}));
      }
    });

    initTocToggle();

import mermaid from 'https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.esm.min.mjs';

const PALETTES = {
      'tailwind-modern': {
        dark: {
          step:      { fill: '#0f172a', stroke: '#60a5fa', color: '#f0f9ff', strokeWidth: 2.5 },
          gate:      { fill: '#1e1b4b', stroke: '#fbbf24', color: '#fef3c7', strokeWidth: 3 },
          terminal:  { fill: '#064e3b', stroke: '#10b981', color: '#f0fdf4', strokeWidth: 3 },
          routeOut:  { fill: '#3f0f5c', stroke: '#d946ef', color: '#faf5ff', strokeWidth: 2 },
          start:     { fill: '#172554', stroke: '#818cf8', color: '#c7d2fe', strokeWidth: 3 },
        },
        light: {
          step:      { fill: '#f0f9ff', stroke: '#0369a1', color: '#0f172a', strokeWidth: 2.5 },
          gate:      { fill: '#fffbeb', stroke: '#b45309', color: '#78350f', strokeWidth: 3 },
          terminal:  { fill: '#f0fdf4', stroke: '#047857', color: '#064e3b', strokeWidth: 3 },
          routeOut:  { fill: '#faf5ff', stroke: '#6d28d9', color: '#3f0f5c', strokeWidth: 2 },
          start:     { fill: '#dbeafe', stroke: '#1e40af', color: '#172554', strokeWidth: 3 },
        },
      },
      'github-dark': {
        dark: {
          step:      { fill: '#0d1117', stroke: '#58a6ff', color: '#c9d1d9', strokeWidth: 2.5 },
          gate:      { fill: '#161b22', stroke: '#d29922', color: '#f0883e', strokeWidth: 3 },
          terminal:  { fill: '#0f5323', stroke: '#1f6feb', color: '#c6f6d5', strokeWidth: 3 },
          routeOut:  { fill: '#28244d', stroke: '#bc8ef9', color: '#e0c3fc', strokeWidth: 2 },
          start:     { fill: '#0d1117', stroke: '#79c0ff', color: '#79c0ff', strokeWidth: 3 },
        },
        light: {
          step:      { fill: '#f6f8fa', stroke: '#0969da', color: '#0d1117', strokeWidth: 2.5 },
          gate:      { fill: '#fff8c5', stroke: '#bf8700', color: '#161b22', strokeWidth: 3 },
          terminal:  { fill: '#dafbe1', stroke: '#1f6feb', color: '#0f5323', strokeWidth: 3 },
          routeOut:  { fill: '#f5e6ff', stroke: '#8957e5', color: '#28244d', strokeWidth: 2 },
          start:     { fill: '#cffaff', stroke: '#0969da', color: '#0d1117', strokeWidth: 3 },
        },
      },
      'nord': {
        dark: {
          step:      { fill: '#2e3440', stroke: '#81a1c1', color: '#eceff4', strokeWidth: 2.5 },
          gate:      { fill: '#3b4252', stroke: '#ebc77a', color: '#eceff4', strokeWidth: 3 },
          terminal:  { fill: '#3b4252', stroke: '#a3be8c', color: '#eceff4', strokeWidth: 3 },
          routeOut:  { fill: '#3b4252', stroke: '#b48ead', color: '#eceff4', strokeWidth: 2 },
          start:     { fill: '#3b4252', stroke: '#88c0f0', color: '#eceff4', strokeWidth: 3 },
        },
        light: {
          step:      { fill: '#eceff4', stroke: '#2e3440', color: '#2e3440', strokeWidth: 2.5 },
          gate:      { fill: '#eceff4', stroke: '#b45309', color: '#78350f', strokeWidth: 3 },
          terminal:  { fill: '#eceff4', stroke: '#047857', color: '#064e3b', strokeWidth: 3 },
          routeOut:  { fill: '#eceff4', stroke: '#6d28d9', color: '#3f0f5c', strokeWidth: 2 },
          start:     { fill: '#dbeafe', stroke: '#1e40af', color: '#172554', strokeWidth: 3 },
        },
      },
      'one-dark-pro': {
        dark: {
          step:      { fill: '#21222c', stroke: '#61afef', color: '#abb2bf', strokeWidth: 2.5 },
          gate:      { fill: '#2c2126', stroke: '#e5c07b', color: '#d19a66', strokeWidth: 3 },
          terminal:  { fill: '#1b1f17', stroke: '#98c379', color: '#98c379', strokeWidth: 3 },
          routeOut:  { fill: '#2c2137', stroke: '#c678dd', color: '#c678dd', strokeWidth: 2 },
          start:     { fill: '#21222c', stroke: '#56b6c2', color: '#56b6c2', strokeWidth: 3 },
        },
        light: {
          step:      { fill: '#fafafa', stroke: '#61afef', color: '#2c313a', strokeWidth: 2.5 },
          gate:      { fill: '#fff8c5', stroke: '#e5c07b', color: '#d19a66', strokeWidth: 3 },
          terminal:  { fill: '#f0fdf4', stroke: '#98c379', color: '#2c313a', strokeWidth: 3 },
          routeOut:  { fill: '#f5e6ff', stroke: '#c678dd', color: '#2c2137', strokeWidth: 2 },
          start:     { fill: '#dbeafe', stroke: '#61afef', color: '#2c313a', strokeWidth: 3 },
        },
      },
      'dracula': {
        dark: {
          step:      { fill: '#282a36', stroke: '#bd93f9', color: '#f8f8f2', strokeWidth: 2.5 },
          gate:      { fill: '#44475a', stroke: '#ffb86c', color: '#f8f8f2', strokeWidth: 3 },
          terminal:  { fill: '#282a36', stroke: '#50fa7b', color: '#f8f8f2', strokeWidth: 3 },
          routeOut:  { fill: '#44475a', stroke: '#ff79c6', color: '#f8f8f2', strokeWidth: 2 },
          start:     { fill: '#282a36', stroke: '#8be9fd', color: '#f8f8f2', strokeWidth: 3 },
        },
        light: {
          step:      { fill: '#fafafa', stroke: '#bd93f9', color: '#282a36', strokeWidth: 2.5 },
          gate:      { fill: '#fff8c5', stroke: '#ffb86c', color: '#78350f', strokeWidth: 3 },
          terminal:  { fill: '#f0fdf4', stroke: '#50fa7b', color: '#064e3b', strokeWidth: 3 },
          routeOut:  { fill: '#f5e6ff', stroke: '#ff79c6', color: '#3f0f5c', strokeWidth: 2 },
          start:     { fill: '#dbeafe', stroke: '#8be9fd', color: '#172554', strokeWidth: 3 },
        },
      },
      'material-ocean': {
        dark: {
          step:      { fill: '#1e1e2e', stroke: '#89b4fa', color: '#a6adc8', strokeWidth: 2.5 },
          gate:      { fill: '#1e1e2e', stroke: '#f9bc2c', color: '#cdd6f4', strokeWidth: 3 },
          terminal:  { fill: '#1e1e2e', stroke: '#94e2d5', color: '#a6adc8', strokeWidth: 3 },
          routeOut:  { fill: '#1e1e2e', stroke: '#cba6f7', color: '#a6adc8', strokeWidth: 2 },
          start:     { fill: '#1e1e2e', stroke: '#74c7ec', color: '#a6adc8', strokeWidth: 3 },
        },
        light: {
          step:      { fill: '#f5f5f5', stroke: '#1565c0', color: '#212121', strokeWidth: 2.5 },
          gate:      { fill: '#fff8e1', stroke: '#f9a825', color: '#4e342e', strokeWidth: 3 },
          terminal:  { fill: '#e8f5e9', stroke: '#2e7d32', color: '#1b5e20', strokeWidth: 3 },
          routeOut:  { fill: '#f3e5f5', stroke: '#7b1fa2', color: '#4a148c', strokeWidth: 2 },
          start:     { fill: '#e3f2fd', stroke: '#1565c0', color: '#0d47a1', strokeWidth: 3 },
        },
      },
    };

    function isLightMode() {
      return window.matchMedia('(prefers-color-scheme: light)').matches;
    }

    function getActivePalette(paletteName) {
      const saved = localStorage.getItem('mermaid-palette') || 'tailwind-modern';
      const name = paletteName || saved;
      const palette = PALETTES[name] ? name : 'tailwind-modern';
      const mode = isLightMode() ? 'light' : 'dark';
      return PALETTES[palette][mode];
    }

    function buildClassDefs(palette) {
      return Object.entries(palette).map(([cls, vals]) =>
        `classDef ${cls} fill:${vals.fill},stroke:${vals.stroke},color:${vals.color},stroke-width:${vals.strokeWidth}`
      ).join('\n    ');
    }

function initMermaid() {
      mermaid.initialize({
        startOnLoad: false,
        theme: 'base',
        themeVariables: {},
        flowchart: { curve: 'basis', nodeSpacing: 60, rankSpacing: 80, htmlLabels: true },
        securityLevel: 'loose',
      });
    }

    async function renderMermaid(force) {
      const pre = document.getElementById('mermaidSource');
      if (!pre) return;
      const stage = document.getElementById('diagramStage');
      if (!stage) return;

      // Update classDefs with current palette before rendering
      const pal = getActivePalette();
      const classDefLines = buildClassDefs(pal).split('\n');
      const lines = pre.textContent.split('\n');
      const newLines = [];
      let inClassDefs = false;
      let classDefCount = 0;
      for (const line of lines) {
        const trimmed = line.trim();
        // classDef lines: enter skip mode
        if (trimmed.startsWith('classDef')) { inClassDefs = true; classDefCount++; continue; }
        // Exit skip mode on blank lines or lines that are NOT class assignments
        if (inClassDefs && (trimmed === '' || !trimmed.startsWith('class '))) {
          inClassDefs = false;
          newLines.push(...classDefLines);
        }
        // Always output non-classDef lines
        newLines.push(line);
      }
      // If no classDef block found, insert before "Start("
      if (classDefCount === 0) {
        const idx = newLines.findIndex(l => l.includes('Start('));
        if (idx > 0) newLines.splice(idx, 0, ...classDefLines);
      }
      const updatedSource = newLines.join('\n');

      // Remove old SVG
      const oldSvg = stage.querySelector('svg');
      if (oldSvg) oldSvg.remove();

      try {
        const id = 'mermaid-' + Date.now();
        const { svg } = await mermaid.render(id, updatedSource);
        const errDiv = document.getElementById('diagramError');
        if (!svg || svg.trim() === '') {
          if (errDiv) { errDiv.textContent = 'Mermaid returned empty output.'; errDiv.classList.add('visible'); }
          return;
        }
        const wrapper = document.createElement('div');
        wrapper.innerHTML = svg;
        const newSvg = wrapper.querySelector('svg');
        if (!newSvg) {
          if (errDiv) { errDiv.textContent = 'No SVG in mermaid output: ' + svg.slice(0, 120); errDiv.classList.add('visible'); }
          return;
        }
        // Keep pre in DOM (hidden) so subsequent renders can still find it by ID
        pre.style.display = 'none';
        newSvg.style.display = 'block';
        newSvg.style.transformOrigin = 'top left';
        if (errDiv) { errDiv.classList.remove('visible'); errDiv.textContent = ''; }
        stage.appendChild(newSvg);
        applyCurrentTransform();
      } catch (err) {
        console.error('Mermaid render error:', err);
        const errDiv = document.getElementById('diagramError');
        if (errDiv) { errDiv.textContent = 'Render error: ' + err.message; errDiv.classList.add('visible'); }
      }
    }

let zoomLevel = 1.0;
    let panX = 0;
    let panY = 0;
    const MIN_ZOOM = 0.2;
    const MAX_ZOOM = 4.0;
    const ZOOM_STEP = 0.15;
    const MIN_PAN_BOUND = 0.1; // fraction of viewport that must remain visible

    const stage = document.getElementById('diagramStage');
    const viewport = document.getElementById('diagramViewport');
    const zoomPct = document.getElementById('zoomPct');

    function applyCurrentTransform() {
      const s = document.getElementById('diagramStage');
      const zp = document.getElementById('zoomPct');
      if (!s) return;
      s.style.transform = `translate(${panX}px, ${panY}px) scale(${zoomLevel})`;
      if (zp) zp.textContent = Math.round(zoomLevel * 100) + '%';
    }

    function clampPan() {
      const v = document.getElementById('diagramViewport');
      if (!v) return;
      const vw = v.clientWidth;
      const vh = v.clientHeight;
      // Prevent pan from dragging more than one viewport's worth in any direction
      panX = Math.max(-vw, Math.min(vw, panX));
      panY = Math.max(-vh, Math.min(vh, panY));
    }

    function zoomBy(factor, centerX, centerY) {
      const newZoom = Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, +(zoomLevel * factor).toFixed(3)));
      if (newZoom === zoomLevel) return;
      if (centerX !== undefined) {
        const v = document.getElementById('diagramViewport');
        if (v) {
          const rect = v.getBoundingClientRect();
          const cx = centerX - rect.left;
          const cy = centerY - rect.top;
          panX = cx - (cx - panX) * (newZoom / zoomLevel);
          panY = cy - (cy - panY) * (newZoom / zoomLevel);
        }
      }
      zoomLevel = newZoom;
      clampPan();
      applyCurrentTransform();
    }

    window.fitSvgToView = function() {
      requestAnimationFrame(() => {
        const s = document.getElementById('diagramStage');
        const v = document.getElementById('diagramViewport');
        if (!s || !v) return;
        const svg = s.querySelector('svg');
        if (!svg) return;
        const vw = v.clientWidth;
        const vh = v.clientHeight;
        if (!vw || !vh) return;
        const svgW = parseFloat(svg.getAttribute('width')) || 800;
        const svgH = parseFloat(svg.getAttribute('height')) || 400;
        const scaleX = (vw * 0.92) / svgW;
        const scaleY = (vh * 0.92) / svgH;
        zoomLevel = Math.min(1.0, Math.min(scaleX, scaleY));
        panX = 0;
        panY = 0;
        applyCurrentTransform();
      });
    };

    function resetZoom() {
      zoomLevel = 1.0;
      panX = 0;
      panY = 0;
      applyCurrentTransform();
      fitSvgToView();
    }

    // Button handlers
    document.getElementById('zoomIn')?.addEventListener('click', () => zoomBy(1 + ZOOM_STEP));
    document.getElementById('zoomOut')?.addEventListener('click', () => zoomBy(1 / (1 + ZOOM_STEP)));
    document.getElementById('zoomReset')?.addEventListener('click', resetZoom);
    document.getElementById('zoomFit')?.addEventListener('click', () => { if (typeof fitSvgToView === 'function') fitSvgToView(); });

    // Wheel zoom
    viewport?.addEventListener('wheel', (e) => {
      e.preventDefault();
      const factor = e.deltaY < 0 ? (1 + ZOOM_STEP) : (1 / (1 + ZOOM_STEP));
      zoomBy(factor, e.clientX, e.clientY);
    }, { passive: false });

    // Keyboard shortcuts
    viewport?.addEventListener('keydown', (e) => {
      const step = 40;
      if (e.key === '+' || e.key === '=') { e.preventDefault(); zoomBy(1 + ZOOM_STEP); }
      if (e.key === '-') { e.preventDefault(); zoomBy(1 / (1 + ZOOM_STEP)); }
      if (e.key === '0') { e.preventDefault(); resetZoom(); }
      if (e.key === 'ArrowLeft') { e.preventDefault(); panX += step; clampPan(); applyCurrentTransform(); }
      if (e.key === 'ArrowRight') { e.preventDefault(); panX -= step; clampPan(); applyCurrentTransform(); }
      if (e.key === 'ArrowUp') { e.preventDefault(); panY += step; clampPan(); applyCurrentTransform(); }
      if (e.key === 'ArrowDown') { e.preventDefault(); panY -= step; clampPan(); applyCurrentTransform(); }
    });

    // Drag-to-pan
    let isPanning = false;
    let lastX = 0, lastY = 0;
    viewport?.addEventListener('pointerdown', (e) => {
      if (e.button !== 0) return;
      isPanning = true;
      lastX = e.clientX;
      lastY = e.clientY;
      viewport.setPointerCapture(e.pointerId);
    });
    viewport?.addEventListener('pointermove', (e) => {
      if (!isPanning) return;
      const dx = e.clientX - lastX;
      const dy = e.clientY - lastY;
      panX += dx;
      panY += dy;
      lastX = e.clientX;
      lastY = e.clientY;
      clampPan();
      applyCurrentTransform();
    });
    viewport?.addEventListener('pointerup', () => { isPanning = false; });
    viewport?.addEventListener('pointercancel', () => { isPanning = false; });

    // Drag-to-resize the diagram pane
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
      if (e.key === 'ArrowUp' || e.key === 'ArrowRight') {
        e.preventDefault();
        const currentHeight = diagramViewport.clientHeight;
        diagramViewport.style.height = Math.min(MAX_HEIGHT, currentHeight + 40) + 'px';
      }
      if (e.key === 'ArrowDown' || e.key === 'ArrowLeft') {
        e.preventDefault();
        const currentHeight = diagramViewport.clientHeight;
        diagramViewport.style.height = Math.max(MIN_HEIGHT, currentHeight - 40) + 'px';
      }
    });

const paletteSelect = document.getElementById('paletteSelect');
    if (paletteSelect) {
      const saved = localStorage.getItem('mermaid-palette');
      if (saved) paletteSelect.value = saved;
      paletteSelect.addEventListener('change', () => {
        localStorage.setItem('mermaid-palette', paletteSelect.value);
        renderMermaid(true);
      });
    }

initMermaid();
renderMermaid();
// Re-render on theme toggle (fired from shared-scripts)
document.addEventListener('theme-toggle', () => { renderMermaid(true); });