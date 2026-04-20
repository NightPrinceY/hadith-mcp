(() => {
  "use strict";

  const $ = (sel, root = document) => root.querySelector(sel);
  const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];

  const THEME_KEY = "hadith-theme";

  // ── Theme toggle (manual override of prefers-color-scheme) ──
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

  const themeBtn = $("#themeToggle");
  if (themeBtn) themeBtn.addEventListener("click", toggleTheme);

  // ── Nav scroll shadow ──
  const nav = $("#topNav");
  const onScroll = () => nav.classList.toggle("scrolled", window.scrollY > 10);
  window.addEventListener("scroll", onScroll, { passive: true });
  onScroll();

  // ── Mobile menu toggle ──
  const toggle = $("#navToggle");
  const links = $("#navLinks");
  toggle.addEventListener("click", () => {
    const open = links.classList.toggle("open");
    toggle.setAttribute("aria-expanded", open);
  });

  links.addEventListener("click", (e) => {
    if (e.target.tagName === "A") links.classList.remove("open");
  });

  // ── Setup tabs ──
  const tabs = $$(".tab");
  const panels = $$(".tab-panel");

  tabs.forEach((tab) => {
    tab.addEventListener("click", () => {
      tabs.forEach((t) => {
        t.classList.remove("active");
        t.setAttribute("aria-selected", "false");
      });
      panels.forEach((p) => p.classList.remove("active"));

      tab.classList.add("active");
      tab.setAttribute("aria-selected", "true");
      const panel = $(`#panel-${tab.dataset.tab}`);
      if (panel) panel.classList.add("active");
    });
  });

  // ── Copy buttons ──
  $$(".copy-btn").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const code = $("code", btn.closest(".code-block"));
      if (!code) return;

      try {
        await navigator.clipboard.writeText(code.textContent);
      } catch {
        const range = document.createRange();
        range.selectNodeContents(code);
        const sel = window.getSelection();
        sel.removeAllRanges();
        sel.addRange(range);
        document.execCommand("copy");
        sel.removeAllRanges();
      }

      btn.textContent = "Copied!";
      btn.classList.add("copied");
      setTimeout(() => {
        btn.textContent = "Copy";
        btn.classList.remove("copied");
      }, 1800);
    });
  });

  // ── Server status ping ──
  const statusDot = $("#statusDot");
  const statusLabel = $("#statusLabel");

  function setStatus(online) {
    statusDot.classList.toggle("online", online);
    statusDot.classList.toggle("offline", !online);
    statusLabel.textContent = online ? "Server online" : "Server unreachable";
    statusLabel.classList.toggle("online", online);
    statusLabel.classList.toggle("offline", !online);
  }

  async function checkServer() {
    try {
      const controller = new AbortController();
      const timeout = setTimeout(() => controller.abort(), 6000);
      await fetch("https://hadith-mcp.org/", {
        method: "HEAD",
        mode: "no-cors",
        cache: "no-store",
        signal: controller.signal,
      });
      clearTimeout(timeout);
      setStatus(true);
    } catch {
      setStatus(false);
    }
  }

  checkServer();
  setInterval(checkServer, 30000);

  // ── Server URL copy button ──
  const urlBtn = $(".copy-url-btn");
  if (urlBtn) {
    urlBtn.addEventListener("click", async () => {
      const val = $(".server-url-value");
      if (!val) return;
      try {
        await navigator.clipboard.writeText(val.textContent.trim());
      } catch {
        const range = document.createRange();
        range.selectNodeContents(val);
        const sel = window.getSelection();
        sel.removeAllRanges();
        sel.addRange(range);
        document.execCommand("copy");
        sel.removeAllRanges();
      }
      urlBtn.textContent = "Copied!";
      urlBtn.classList.add("copied");
      setTimeout(() => {
        urlBtn.textContent = "Copy";
        urlBtn.classList.remove("copied");
      }, 1800);
    });
  }

  // ── Search app redirect CTA ──
  const searchInput = $("#searchSiteQuery");
  const searchSubmit = $("#searchSiteSubmit");
  const SEARCH_APP_URL = "https://search.hadith-mcp.org/";

  function openSearchAppFromCta() {
    if (!searchInput) return;
    const q = searchInput.value.trim();
    const target = new URL(SEARCH_APP_URL);
    if (q) target.searchParams.set("q", q);
    window.open(target.toString(), "_blank", "noopener");
  }

  if (searchSubmit && searchInput) {
    searchSubmit.addEventListener("click", openSearchAppFromCta);
    searchInput.addEventListener("keydown", (e) => {
      if (e.key === "Enter") {
        e.preventDefault();
        openSearchAppFromCta();
      }
    });
  }

  // ── Smooth reveal on scroll ──
  const revealEls = $$(
    ".tool-card, .comparison-card, .steps li, .grounding-item, .setup-steps-list"
  );

  if ("IntersectionObserver" in window) {
    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) {
            entry.target.classList.add("visible");
            observer.unobserve(entry.target);
          }
        });
      },
      { threshold: 0.15 }
    );

    revealEls.forEach((el) => {
      el.classList.add("reveal");
      observer.observe(el);
    });
  }
})();
