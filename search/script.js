(() => {
  "use strict";

  const state = {
    query: "",
    page: 1,
    perPage: 10,
    results: [],
  };

  const searchInput = document.getElementById("searchInput");
  const searchBtn = document.getElementById("searchBtn");
  const clearBtn = document.getElementById("clearBtn");
  const collectionSelect = document.getElementById("collectionSelect");
  const statsText = document.getElementById("statsText");
  const resultsList = document.getElementById("resultsList");
  const pagination = document.getElementById("pagination");
  const prevPageBtn = document.getElementById("prevPageBtn");
  const nextPageBtn = document.getElementById("nextPageBtn");
  const pageText = document.getElementById("pageText");
  const resultTemplate = document.getElementById("resultTemplate");

  const esc = (s = "") =>
    String(s).replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;");

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
    const data = await getJson("/api/collections");
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
      render();
      return;
    }
    const lookup = parseLookup(q);
    if (lookup?.kind === "global") {
      const data = await getJson(`/api/hadith/${lookup.id}`);
      state.results = [data.hadith];
      return;
    }
    if (lookup?.kind === "collection") {
      const data = await getJson(`/api/hadith/${lookup.slug}/${lookup.idInBook}`);
      state.results = [data.hadith];
      return;
    }
    const params = new URLSearchParams({ q, limit: "100" });
    if (collectionSelect.value) params.set("collection", collectionSelect.value);
    const data = await getJson(`/api/search?${params.toString()}`);
    state.results = data.results || [];
  }

  function hadithTitle(item) {
    return `${item.collection_name_english || item.collection_slug} #${item.id_in_book}`;
  }

  function shareUrl(item) {
    return `${location.origin}/?id=${item.id}`;
  }

  async function copy(text) {
    await navigator.clipboard.writeText(text);
  }

  function render() {
    const total = state.results.length;
    if (total === 0) {
      statsText.textContent = state.query ? "No results found." : "Enter a query to start.";
      resultsList.innerHTML = '<div class="empty">No hadith results.</div>';
      pagination.hidden = true;
      return;
    }
    const pages = Math.max(1, Math.ceil(total / state.perPage));
    state.page = Math.min(state.page, pages);
    const start = (state.page - 1) * state.perPage;
    const end = Math.min(total, start + state.perPage);
    const rows = state.results.slice(start, end);
    statsText.textContent = `Showing ${start + 1}-${end} of ${total} result(s).`;

    const frag = document.createDocumentFragment();
    for (const item of rows) {
      const card = resultTemplate.content.firstElementChild.cloneNode(true);
      card.querySelector(".collection").textContent = item.collection_name_english || item.collection_slug || "";
      card.querySelector(".number").textContent = `#${item.id_in_book}`;
      card.querySelector(".dbid").textContent = `DB ${item.id}`;
      card.querySelector(".provenance").textContent = item.provenance || "";
      card.querySelector(".result-title").textContent = hadithTitle(item);
      card.querySelector(".result-excerpt").textContent = item.english_excerpt || (item.english || "").slice(0, 280);

      const full = card.querySelector(".result-full");
      full.innerHTML = `
        <div>${esc(item.english || item.english_excerpt || "")}</div>
        ${item.arabic ? `<div class="arabic">${esc(item.arabic)}</div>` : ""}
      `;

      const toggle = card.querySelector(".toggle-btn");
      toggle.addEventListener("click", () => {
        const open = full.hidden;
        full.hidden = !open;
        toggle.textContent = open ? "Hide full text" : "Show full text";
      });

      card.querySelector(".copy-link-btn").addEventListener("click", async () => {
        await copy(shareUrl(item));
      });
      card.querySelector(".copy-text-btn").addEventListener("click", async () => {
        const body = `${hadithTitle(item)}\nDB ID: ${item.id}\n\n${item.english || item.english_excerpt || ""}\n\n${shareUrl(item)}`;
        await copy(body);
      });

      frag.appendChild(card);
    }

    resultsList.replaceChildren(frag);
    pagination.hidden = pages <= 1;
    prevPageBtn.disabled = state.page <= 1;
    nextPageBtn.disabled = state.page >= pages;
    pageText.textContent = `Page ${state.page} of ${pages}`;
  }

  async function submit() {
    state.query = searchInput.value.trim();
    state.page = 1;
    try {
      await performSearch();
      render();
    } catch (err) {
      statsText.textContent = String(err);
      resultsList.innerHTML = '<div class="empty">Search failed.</div>';
      pagination.hidden = true;
    }
  }

  searchBtn.addEventListener("click", submit);
  searchInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter") submit();
  });
  clearBtn.addEventListener("click", () => {
    state.query = "";
    state.results = [];
    state.page = 1;
    searchInput.value = "";
    render();
  });
  collectionSelect.addEventListener("change", () => {
    if (state.query) submit();
  });
  prevPageBtn.addEventListener("click", () => {
    state.page -= 1;
    render();
  });
  nextPageBtn.addEventListener("click", () => {
    state.page += 1;
    render();
  });

  loadCollections().then(render).catch(() => {
    statsText.textContent = "Could not load collections.";
  });
})();

