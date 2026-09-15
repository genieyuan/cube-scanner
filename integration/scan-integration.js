/* The block a 3D cube page needs to consume the scanner hand-off. Taken from the demo cube page;
   adapt SCAN_SLOTS / FACE_NORMAL to your own model. Expects the page's cubies, renderCube(), setMessage(). */
  /* ---- Camera scanner support (added 2026-09-15) --------------------------------
     Patched INTO this file rather than replacing it. The first attempt copied a fork of
     app.js over the top and wiped four hours of the learner's work — the fork still queried
     #exampleStart, which he had removed, so the script threw and the cube never drew.
     Promote the CHANGE, never the whole file. */
  const SCAN_SLOTS = {
    F: [[-1,1,1],  [1,1,1],  [-1,-1,1],  [1,-1,1]],
    B: [[1,1,-1],  [-1,1,-1],[1,-1,-1],  [-1,-1,-1]],
    R: [[1,1,1],   [1,1,-1], [1,-1,1],   [1,-1,-1]],
    L: [[-1,1,-1], [-1,1,1], [-1,-1,-1], [-1,-1,1]],
    U: [[-1,1,-1], [1,1,-1], [-1,1,1],   [1,1,1]],
    D: [[-1,-1,1], [1,-1,1], [-1,-1,-1], [1,-1,-1]]
  };
  const FACE_NORMAL = { U:'0,1,0', D:'0,-1,0', F:'0,0,1', B:'0,0,-1', R:'1,0,0', L:'-1,0,0' };
  const SCAN_CONVENTION = '2026-09-14-lr-fixed';
  let lastScan = null;
  try {
    const ver = localStorage.getItem('cube-scan-version');
    const keep = localStorage.getItem('cube-scan-last');
    if (keep && ver === SCAN_CONVENTION) lastScan = JSON.parse(keep);
    else if (keep) { localStorage.removeItem('cube-scan-last'); localStorage.removeItem('cube-scan-cube'); }
  } catch (e) { /* no retained scan */ }

  function applyScan(faces){
    const next = createSolvedCube();
    const byPos = {};
    next.forEach(c => { byPos[c.pos.join(',')] = c; c.stickers = {}; });
    let placed = 0;
    Object.entries(SCAN_SLOTS).forEach(([face, slots]) => {
      const vals = faces[face];
      if (!vals) return;
      slots.forEach((pos, i) => {
        const cubie = byPos[pos.join(',')];
        if (!cubie || !vals[i]) return;
        cubie.stickers[FACE_NORMAL[face]] = vals[i];
        placed++;
      });
    });
    cubies = next;
    renderCube();
    return placed;
  }

  function rebuildLastScan(){
    if (!lastScan) return 0;
    const n = applyScan(lastScan);
    if (statusElement) statusElement.textContent = language === 'en'
      ? 'Rebuilt your last scan — ' + n + ' of 24 stickers placed.'
      : '已重建上次扫描 — 放好 ' + n + '/24 个格子。';
    return n;
  }

  function mountScanButtons(){
    const host = revertViewButton && revertViewButton.parentElement;
    if (!host || document.querySelector('#goScan')) return;
    const mk = (id, cls, en, zh, fn) => {
      const b = document.createElement('button');
      b.id = id; b.className = cls;
      b.textContent = language === 'en' ? en : zh;
      b.dataset.en = en; b.dataset.zh = zh;
      b.addEventListener('click', fn);
      host.appendChild(b);
      return b;
    };
    mk('goScan', 'primary', '📷 Scan my cube', '📷 扫描我的魔方',
       () => {
         /* Go straight to the secure address. The scan page can send itself there, but that
            depends on the browser running the current copy of it, and this server sends no
            cache headers at all — so a stale copy sits on http showing "the browser is
            blocking the camera" and the site looks broken. Deciding the destination HERE,
            at the moment of the click, cannot go stale. */
         const u = new URL('./scan.html', location.href);
         location.href = u.href;
       });
    if (lastScan) {
      mk('rebuildScan', 'secondary', '↻ Rebuild last scan', '↻ 重建上次扫描', rebuildLastScan);
      mk('clearScan', 'secondary', '🗑 Clear saved scan', '🗑 清除扫描记录', () => {
        try {
          localStorage.removeItem('cube-scan-last');
          localStorage.removeItem('cube-scan-cube');
          localStorage.removeItem('cube-scan-version');
        } catch (e) {}
        lastScan = null;
        ['rebuildScan','clearScan'].forEach(id => {
          const el = document.querySelector('#' + id); if (el) el.remove();
        });
        resetCubeState();
        if (statusElement) statusElement.textContent = language === 'en'
          ? 'Saved scan cleared.' : '已清除扫描记录。';
      });
    }
  }

  (function bootstrapScan(){
    /* Language carry-over (the maintainer, 2026-09-15): scan.html and this page share one remembered
       choice, localStorage 'cube-lang'. INSERTION ONLY - the learner's switchLanguage() is untouched:
       if the remembered language differs we press his button, and after every press we
       remember the result (read after his handler has run). */
    try {
      const btn = document.querySelector('#lang');
      if (btn) {
        if (localStorage.getItem('cube-lang') === 'zh' && language === 'en') btn.click();
        btn.addEventListener('click', () => { setTimeout(() => {
          try { localStorage.setItem('cube-lang', language); } catch (e) {}
        }, 0); });
      }
    } catch (e) { /* ignore */ }
    let raw = null;
    try {
      const q = new URLSearchParams(location.search).get('scan');
      raw = q ? decodeURIComponent(q) : localStorage.getItem('cube-scan-cube');
    } catch (e) { /* ignore */ }
    if (raw) {
      try {
        const faces = JSON.parse(raw);
        const n = applyScan(faces);
        lastScan = faces;
        try {
          localStorage.setItem('cube-scan-last', JSON.stringify(faces));
          localStorage.setItem('cube-scan-version', SCAN_CONVENTION);
          localStorage.removeItem('cube-scan-cube');
        } catch (e) {}
        if (statusElement) statusElement.textContent = language === 'en'
          ? 'Built from your camera scan — ' + n + ' of 24 stickers placed.'
          : '已根据扫描生成 — 放好 ' + n + '/24 个格子。';
      } catch (err) {
        console.error('[scan] could not build:', err);
      }
    }
    mountScanButtons();
  })();

