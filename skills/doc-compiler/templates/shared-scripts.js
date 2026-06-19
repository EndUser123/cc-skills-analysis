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

// initMermaid/renderMermaid called in diagram-scripts.js after mermaid import resolves

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

    // initTocToggle called in diagram-scripts.js after TOC structure is ready