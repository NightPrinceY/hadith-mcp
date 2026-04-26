(() => {
  "use strict";

  // Public REST API backing this frontend. Overridable via
  //   window.HADITH_API_BASE = "https://api.example.com";
  // (set in HTML before this script loads) for local dev / staging.
  const API_BASE = (typeof window !== "undefined" && window.HADITH_API_BASE)
    || "https://api.hadith-mcp.org";

  const CLAMP_OVERFLOW_PX = 4;
  const THEME_KEY = "hadith-search-theme";

  const state = {
    query: "",
    page: 1,
    perPage: 10,
    results: [],
    singleLookup: false,
  };

  // ─── Theme toggle (manual override of prefers-color-scheme) ─
  function applyTheme(theme) {
    const root = document.documentElement;
    if (theme === "dark" || theme === "light") {
      root.setAttribute("data-theme", theme);
    } else {
      root.removeAttribute("data-theme");
    }
  }

  function resolvedTheme() {
    const saved = localStorage.getItem(THEME_KEY);
    if (saved === "dark" || saved === "light") return saved;
    return window.matchMedia?.("(prefers-color-scheme: dark)").matches
      ? "dark"
      : "light";
  }

  function toggleTheme() {
    const next = resolvedTheme() === "dark" ? "light" : "dark";
    localStorage.setItem(THEME_KEY, next);
    applyTheme(next);
  }

  const savedTheme = localStorage.getItem(THEME_KEY);
  if (savedTheme === "dark" || savedTheme === "light") applyTheme(savedTheme);

  const searchInput = document.getElementById("searchInput");
  const searchBtn = document.getElementById("searchBtn");
  const clearBtn = document.getElementById("clearBtn");
  const collectionSelect = document.getElementById("collectionSelect");
  const provenanceSelect = document.getElementById("provenanceSelect");
  const statsText = document.getElementById("statsText");
  const resultsList = document.getElementById("resultsList");
  const pagination = document.getElementById("pagination");
  const prevPageBtn = document.getElementById("prevPageBtn");
  const nextPageBtn = document.getElementById("nextPageBtn");
  const pageText = document.getElementById("pageText");
  const resultTemplate = document.getElementById("resultTemplate");
  const loadingIndicator = document.getElementById("loadingIndicator");

  // Detail view elements
  const detailView = document.getElementById("detailView");
  const detailCard = document.getElementById("detailCard");
  const backToSearchBtn = document.getElementById("backToSearch");
  const crossRefsSection = document.getElementById("crossRefsSection");
  const crossRefsHeading = document.getElementById("crossRefsHeading");
  const crossRefsList = document.getElementById("crossRefsList");

  function setLoading(isLoading) {
    if (!loadingIndicator) return;
    loadingIndicator.hidden = !isLoading;
    if (isLoading) {
      // Blank the previous results + pager so the spinner isn't stacked on
      // top of stale cards from the last query.
      resultsList.replaceChildren();
      pagination.hidden = true;
      statsText.textContent = "Searching…";
    }
  }

  // ─── Lookup + fetch ──────────────────────────────────────
  function parseLookup(query) {
    const q = query.trim();
    const bare = q.match(/^#?(\d+)$/);
    if (bare) return { kind: "global", id: Number.parseInt(bare[1], 10) };
    const coll = q.match(/^([a-zA-Z_]+)\s*#?\s*(\d+)$/);
    if (coll) return { kind: "collection", slug: coll[1].toLowerCase(), idInBook: Number.parseInt(coll[2], 10) };
    return null;
  }

  async function getJson(url) {
    const r = await fetch(url);
    if (!r.ok) throw new Error(`Request failed (${r.status})`);
    return r.json();
  }

  async function loadCollections() {
    const data = await getJson(`${API_BASE}/api/collections`);
    for (const c of data.collections || []) {
      const option = document.createElement("option");
      option.value = c.slug;
      option.textContent = c.name_english;
      collectionSelect.appendChild(option);
    }
  }

  async function performSearch() {
    const q = state.query.trim();
    if (!q) {
      state.results = [];
      state.singleLookup = false;
      return;
    }
    const lookup = parseLookup(q);
    if (lookup?.kind === "global") {
      const data = await getJson(`${API_BASE}/api/hadith/${lookup.id}`);
      state.results = data.hadith ? [data.hadith] : [];
      state.singleLookup = true;
      return;
    }
    if (lookup?.kind === "collection") {
      const data = await getJson(`${API_BASE}/api/hadith/${encodeURIComponent(lookup.slug)}/${lookup.idInBook}`);
      state.results = data.hadith ? [data.hadith] : [];
      state.singleLookup = true;
      return;
    }
    const params = new URLSearchParams({ q, limit: "100" });
    if (collectionSelect.value) params.set("collection", collectionSelect.value);
    const data = await getJson(`${API_BASE}/api/search?${params.toString()}`);
    state.results = data.results || [];
    state.singleLookup = false;
  }

  // ─── Rendering helpers ───────────────────────────────────

  function shareUrl(item) {
    return `${location.origin}/?id=${item.id}`;
  }

  function formatNarrator(raw) {
    if (!raw) return "";
    const s = raw.trim();
    if (!s) return "";
    if (/^(narrated|reported|it was narrated)/i.test(s)) return s.endsWith(":") ? s : `${s}:`;
    return `Narrated ${s}:`;
  }

  function formatSimilarity(sim) {
    if (typeof sim !== "number" || !Number.isFinite(sim) || sim <= 0) return null;
    const pct = Math.round(sim * 100);
    if (pct <= 0) return null;
    return `${pct}% match`;
  }

  function englishTextOf(item) {
    return item.english || item.english_excerpt || "";
  }

  // Detect overflow after layout and toggle the "Show more" control.
  function setupClamp(bodyEl, textEl, expandBtn, expanded) {
    if (expanded) {
      textEl.classList.remove("is-clamped");
      expandBtn.hidden = true;
      return;
    }
    textEl.classList.add("is-clamped");
    requestAnimationFrame(() => {
      const overflow = textEl.scrollHeight - textEl.clientHeight > CLAMP_OVERFLOW_PX;
      if (overflow) {
        expandBtn.hidden = false;
        expandBtn.textContent = "Show more";
      } else {
        textEl.classList.remove("is-clamped");
        expandBtn.hidden = true;
      }
    });
  }

  async function copyToClipboard(text, btn) {
    try {
      await navigator.clipboard.writeText(text);
      if (btn) {
        btn.classList.add("is-copied");
        setTimeout(() => btn.classList.remove("is-copied"), 900);
      }
      showToast("Copied");
    } catch {
      showToast("Copy failed");
    }
  }

  let toastTimer = null;
  function showToast(msg) {
    let el = document.querySelector(".toast");
    if (!el) {
      el = document.createElement("div");
      el.className = "toast";
      document.body.appendChild(el);
    }
    el.textContent = msg;
    requestAnimationFrame(() => el.classList.add("is-visible"));
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => el.classList.remove("is-visible"), 1400);
  }

  function renderCard(item, { detail = false } = {}) {
    const card = resultTemplate.content.firstElementChild.cloneNode(true);
    if (detail) card.classList.add("is-detail");

    // Meta chips
    const collName = item.collection_name_english || item.collection_slug || "";
    card.querySelector(".chip-coll").textContent = collName;
    card.querySelector(".chip-num").textContent = `#${item.id_in_book}`;

    const chapterEl = card.querySelector(".chip-chapter");
    const chapterName = (item.chapter_name_english || "").trim();
    if (chapterName) {
      chapterEl.textContent = chapterName;
      chapterEl.hidden = false;
    }

    // DB id + provenance live in the top meta row now.
    const dbidEl = card.querySelector(".chip-dbid");
    if (item.id != null) {
      dbidEl.textContent = `DB ${item.id}`;
      dbidEl.hidden = false;
    }

    const provEl = card.querySelector(".chip-prov");
    const prov = (item.provenance || "").trim();
    if (prov) {
      provEl.textContent = prov;
      provEl.hidden = false;
    }

    const simEl = card.querySelector(".chip-sim");
    const simLabel = formatSimilarity(item.similarity);
    if (simLabel) {
      simEl.textContent = simLabel;
      simEl.hidden = false;
    }

    // Narrator (italic accent line)
    const narrEl = card.querySelector(".result-narrator");
    const narr = formatNarrator(item.narrator);
    if (narr) {
      narrEl.textContent = narr;
      narrEl.hidden = false;
    }

    // English body + smart clamp
    const bodyEl = card.querySelector(".result-body");
    const textEl = card.querySelector(".english-text");
    const expandBtn = card.querySelector(".expand-btn");
    textEl.textContent = englishTextOf(item);

    let expanded = detail;
    setupClamp(bodyEl, textEl, expandBtn, expanded);
    expandBtn.addEventListener("click", () => {
      expanded = !expanded;
      if (expanded) {
        textEl.classList.remove("is-clamped");
        expandBtn.textContent = "Show less";
      } else {
        textEl.classList.add("is-clamped");
        expandBtn.textContent = "Show more";
      }
    });

    // Arabic block
    if (item.arabic && item.arabic.trim()) {
      const arBlock = card.querySelector(".arabic-block");
      const arText = card.querySelector(".arabic-text");
      arText.textContent = item.arabic.trim();
      arBlock.hidden = false;
    }

    // Actions
    const openLink = card.querySelector(".open-link");
    openLink.href = item.url || shareUrl(item);

    card.querySelector(".copy-link-btn").addEventListener("click", (e) => {
      e.stopPropagation();
      copyToClipboard(shareUrl(item), e.currentTarget);
    });
    card.querySelector(".copy-text-btn").addEventListener("click", (e) => {
      e.stopPropagation();
      const header = `${collName} #${item.id_in_book}`;
      const body = [
        header,
        narr,
        "",
        englishTextOf(item),
        item.arabic ? `\n${item.arabic}` : "",
        `\n${shareUrl(item)}`,
      ].filter(Boolean).join("\n");
      copyToClipboard(body, e.currentTarget);
    });

    return card;
  }

  // ─── Detail view (single hadith + cross-references) ─────

  function enterDetailMode() {
    document.body.classList.add("is-detail-mode");
    resultsList.hidden = true;
    pagination.hidden = true;
    loadingIndicator && (loadingIndicator.hidden = true);
    detailView.hidden = false;
  }

  function exitDetailMode() {
    document.body.classList.remove("is-detail-mode");
    detailView.hidden = true;
    detailCard.replaceChildren();
    crossRefsList.replaceChildren();
    crossRefsSection.hidden = true;
    resultsList.hidden = false;
    history.replaceState(null, "", location.pathname);
    searchInput.value = "";
    state.query = "";
    state.results = [];
    state.singleLookup = false;
    state.page = 1;
    render();
    window.scrollTo({ top: 0 });
  }

  function renderCrossRefCard(xref) {
    const item = {
      id: xref.matched_hadith_id,
      id_in_book: xref.id_in_book,
      collection_slug: xref.collection_slug,
      collection_name_english: xref.collection_slug,
      english: xref.english_excerpt || "",
      english_excerpt: xref.english_excerpt || "",
      similarity: xref.similarity,
      url: xref.url,
    };
    const card = renderCard(item);
    card.classList.add("xref-card");
    card.addEventListener("click", (e) => {
      if (e.target.closest(".icon-btn, .expand-btn, a")) return;
      openDetailView(xref.matched_hadith_id);
    });
    return card;
  }

  async function openDetailView(hadithId) {
    enterDetailMode();
    detailCard.innerHTML = '<div class="loading-indicator"><span class="spinner" aria-hidden="true"></span><span class="loading-text">Loading…</span></div>';
    crossRefsSection.hidden = true;

    const currentId = new URLSearchParams(location.search).get("id");
    if (currentId !== String(hadithId)) {
      history.pushState({ hadithId }, "", `?id=${hadithId}`);
    }

    try {
      const [hadithData, xrefData] = await Promise.all([
        getJson(`${API_BASE}/api/hadith/${hadithId}`),
        getJson(`${API_BASE}/api/hadith/${hadithId}/cross-references`),
      ]);

      if (!hadithData.hadith) {
        detailCard.innerHTML = '<div class="empty">Hadith not found.</div>';
        return;
      }

      detailCard.replaceChildren(renderCard(hadithData.hadith, { detail: true }));

      const refs = xrefData.cross_references || [];
      if (refs.length) {
        crossRefsHeading.textContent = `Cross-references (${refs.length})`;
        const frag = document.createDocumentFragment();
        for (const xref of refs) frag.appendChild(renderCrossRefCard(xref));
        crossRefsList.replaceChildren(frag);
        crossRefsSection.hidden = false;
      }

      window.scrollTo({ top: 0, behavior: "smooth" });
    } catch (err) {
      detailCard.innerHTML = `<div class="empty">Failed to load: ${String(err)}</div>`;
    }
  }

  backToSearchBtn?.addEventListener("click", exitDetailMode);

  function filteredResults() {
    const prov = provenanceSelect?.value || "";
    if (!prov) return state.results;
    return state.results.filter((r) => (r.provenance || "") === prov);
  }

  function render() {
    const filtered = filteredResults();
    const total = filtered.length;
    if (total === 0) {
      const provActive = provenanceSelect?.value;
      if (state.results.length && provActive) {
        statsText.textContent = "No results match the selected provenance filter.";
      } else {
        statsText.textContent = state.query ? "No results found." : "Enter a query to start.";
      }
      resultsList.innerHTML = '<div class="empty">No hadith results.</div>';
      pagination.hidden = true;
      return;
    }

    // Single-item lookup: render in focused "detail" mode, no pagination.
    if (state.singleLookup && total === 1) {
      statsText.textContent = "Direct lookup.";
      resultsList.replaceChildren(renderCard(filtered[0], { detail: true }));
      pagination.hidden = true;
      return;
    }

    const pages = Math.max(1, Math.ceil(total / state.perPage));
    state.page = Math.min(state.page, pages);
    const start = (state.page - 1) * state.perPage;
    const end = Math.min(total, start + state.perPage);
    const rows = filtered.slice(start, end);
    statsText.textContent = `Showing ${start + 1}–${end} of ${total} result(s).`;

    const frag = document.createDocumentFragment();
    for (const item of rows) frag.appendChild(renderCard(item));
    resultsList.replaceChildren(frag);

    pagination.hidden = pages <= 1;
    prevPageBtn.disabled = state.page <= 1;
    nextPageBtn.disabled = state.page >= pages;
    pageText.textContent = `Page ${state.page} of ${pages}`;
  }

  async function submit() {
    state.query = searchInput.value.trim();
    state.page = 1;

    // Route direct lookups (#id, collection number) to the detail view
    const lookup = parseLookup(state.query);
    if (lookup?.kind === "global") {
      openDetailView(lookup.id);
      return;
    }
    if (lookup?.kind === "collection") {
      try {
        const data = await getJson(`${API_BASE}/api/hadith/${encodeURIComponent(lookup.slug)}/${lookup.idInBook}`);
        if (data.hadith?.id != null) {
          openDetailView(data.hadith.id);
          return;
        }
      } catch { /* fall through to normal search */ }
    }

    setLoading(true);
    try {
      await performSearch();
      render();
    } catch (err) {
      statsText.textContent = String(err);
      resultsList.innerHTML = '<div class="empty">Search failed.</div>';
      pagination.hidden = true;
    } finally {
      setLoading(false);
    }
  }

  searchBtn.addEventListener("click", submit);
  searchInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter") submit();
  });
  clearBtn.addEventListener("click", () => {
    state.query = "";
    state.results = [];
    state.singleLookup = false;
    state.page = 1;
    searchInput.value = "";
    if (provenanceSelect) provenanceSelect.value = "";
    render();
  });
  collectionSelect.addEventListener("change", () => {
    if (state.query) submit();
  });
  provenanceSelect?.addEventListener("change", () => {
    state.page = 1;
    if (state.results.length) render();
  });
  prevPageBtn.addEventListener("click", () => {
    state.page -= 1;
    render();
  });
  nextPageBtn.addEventListener("click", () => {
    state.page += 1;
    render();
  });

  function bootstrapFromUrl() {
    const params = new URLSearchParams(window.location.search);
    if (params.get("app") === "1") document.body.classList.add("is-embedded");

    // Direct ID lookup → detail view with cross-references
    const id = params.get("id");
    if (id && /^\d+$/.test(id.trim())) {
      openDetailView(Number.parseInt(id.trim(), 10));
      return true;
    }

    // Collection + number → fetch the hadith to get its DB id, then detail view
    const collection = (params.get("collection") || "").trim().toLowerCase();
    const number = (params.get("number") || "").trim();
    if (collection && /^\d+$/.test(number)) {
      (async () => {
        try {
          const data = await getJson(`${API_BASE}/api/hadith/${encodeURIComponent(collection)}/${number}`);
          if (data.hadith?.id != null) {
            openDetailView(data.hadith.id);
          } else {
            searchInput.value = `${collection} ${number}`;
            submit();
          }
        } catch {
          searchInput.value = `${collection} ${number}`;
          submit();
        }
      })();
      return true;
    }

    const q = params.get("q");
    if (q && q.trim()) {
      searchInput.value = q.trim();
      submit();
      return true;
    }
    return false;
  }

  window.addEventListener("popstate", () => {
    const params = new URLSearchParams(window.location.search);
    const id = params.get("id");
    if (id && /^\d+$/.test(id.trim())) {
      openDetailView(Number.parseInt(id.trim(), 10));
    } else if (document.body.classList.contains("is-detail-mode")) {
      exitDetailMode();
    }
  });

  const themeBtn = document.getElementById("themeToggle");
  themeBtn?.addEventListener("click", toggleTheme);

  const globalUsageStats = document.getElementById("globalUsageStats");

  function formatCount(n) {
    if (typeof n !== "number" || !Number.isFinite(n) || n < 0) return "0";
    if (n < 1000) return String(Math.floor(n));
    const tiers = [
      { v: 1e9, s: "b" },
      { v: 1e6, s: "m" },
      { v: 1e3, s: "k" },
    ];
    for (const { v, s } of tiers) {
      if (n >= v) {
        const t = n / v;
        return (t >= 10 ? t.toFixed(0) : t.toFixed(1)) + s;
      }
    }
    return String(n);
  }

  function statsUrlCandidates() {
    const u = new Set();
    try {
      if (typeof window !== "undefined" && window.location) {
        const p = String(window.location.protocol || "");
        if (p && p !== "file:") {
          u.add(new URL("/api/stats", window.location.origin).href);
          u.add(new URL("/api/stats/", window.location.origin).href);
        }
      }
    } catch {
      /* ignore */
    }
    u.add(`${API_BASE}/api/stats`);
    u.add(`${API_BASE}/api/stats/`);
    u.add("https://api.hadith-mcp.org/api/stats");
    return [...u];
  }

  async function loadGlobalUsageStats() {
    if (!globalUsageStats) return;
    for (const url of statsUrlCandidates()) {
      try {
        const res = await fetch(url, { cache: "default", mode: "cors" });
        if (!res.ok) continue;
        const j = await res.json();
        const s = j.total_searches ?? 0;
        const l = j.total_lookups ?? 0;
        const u = j.unique_visitors ?? 0;
        globalUsageStats.classList.remove("global-usage-pending", "global-usage-missing");
        globalUsageStats.textContent =
          `${formatCount(s)} searches  ·  ${formatCount(l)} lookups  ·  ${formatCount(u)} users`;
        return;
      } catch {
        /* try next */
      }
    }
    globalUsageStats.classList.add("global-usage-missing");
    globalUsageStats.classList.remove("global-usage-pending");
    globalUsageStats.textContent = "Stats unavailable (check /api and deploy)";
  }

  loadGlobalUsageStats();

  loadCollections()
    .catch(() => {
      statsText.textContent = "Could not load collections.";
    })
    .finally(() => {
      if (!bootstrapFromUrl()) render();
    });
})();
