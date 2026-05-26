/* audiobook-ish player (M5): page + bbox sync */

(async () => {
  const audio = document.getElementById("audio");
  const list = document.getElementById("sentence-list");
  const layout = document.getElementById("layout");
  const pageView = document.getElementById("page-view");
  const pageStage = document.getElementById("page-stage");
  const pageImage = document.getElementById("page-image");
  const pageEmpty = document.getElementById("page-empty");
  const overlay = document.getElementById("highlight-overlay");
  const pageNum = document.getElementById("page-num");
  const pageTotal = document.getElementById("page-total");
  const titleEl = document.getElementById("title");
  const scrubber = document.getElementById("scrubber");
  const tCurrent = document.getElementById("time-current");
  const tTotal = document.getElementById("time-total");
  const playPause = document.getElementById("play-pause");
  const prevBtn = document.getElementById("prev-sent");
  const nextBtn = document.getElementById("next-sent");
  const speed = document.getElementById("speed");
  const chapterWrap = document.getElementById("chapter-wrap");
  const chapterSelect = document.getElementById("chapter-select");
  const bookmarkAdd = document.getElementById("bookmark-add");
  const bookmarkSelect = document.getElementById("bookmark-select");
  const themeToggle = document.getElementById("theme-toggle");

  let manifest = null;
  let currentIdx = -1;
  let currentPage = null;
  const timeline = [];
  const sentencesByPage = new Map();
  const pageByNumber = new Map();
  let chapters = [];
  let bookmarks = [];
  let storagePrefix = "audiobook-ish:unknown";

  try {
    manifest = await loadManifest();
  } catch (err) {
    titleEl.textContent = "Could not load manifest data (manifest.js or manifest.json).";
    pageNum.textContent = "—";
    pageTotal.textContent = "—";
    console.error(err);
    return;
  }

  if (!Array.isArray(manifest.sentences) || manifest.sentences.length === 0) {
    titleEl.textContent = "Manifest loaded, but no sentences were found.";
    pageNum.textContent = "—";
    pageTotal.textContent = String(manifest.page_count ?? "—");
    return;
  }

  titleEl.textContent = manifest.source_pdf || "audiobook-ish";
  storagePrefix = `audiobook-ish:${manifest.source_pdf || "unknown"}`;
  const inferredTotalPages = manifest.page_count
    || Math.max(...manifest.sentences.map((s) => Number(s.page) || 0), 0)
    || "—";
  pageTotal.textContent = String(inferredTotalPages);
  if (Array.isArray(manifest.pages)) {
    for (const page of manifest.pages) {
      pageByNumber.set(Number(page.number), page);
    }
  }
  if (Array.isArray(manifest.chapters)) {
    chapters = manifest.chapters
      .map((c) => ({
        title: String(c.title || ""),
        sentence_id: Number(c.sentence_id),
        page: Number(c.page),
        start_sec: Number(c.start_sec),
      }))
      .filter((c) => Number.isFinite(c.sentence_id) && c.sentence_id >= 0);
  }

  // Build sentence list + lookup timeline.
  for (const s of manifest.sentences) {
    const start = Number(s.start_sec);
    const end = Number(s.end_sec);
    if (Number.isFinite(start) && Number.isFinite(end) && end > start) {
      timeline.push({ id: s.id, start, end });
    }
    const page = Number(s.page);
    if (Number.isFinite(page)) {
      if (!sentencesByPage.has(page)) sentencesByPage.set(page, []);
      sentencesByPage.get(page).push(s.id);
    }

    const li = document.createElement("li");
    li.textContent = s.text;
    li.dataset.id = String(s.id);
    li.addEventListener("click", () => {
      if (typeof s.start_sec === "number") {
        audio.currentTime = s.start_sec;
        audio.play();
      }
    });
    list.appendChild(li);
  }
  timeline.sort((a, b) => a.start - b.start);
  pageView.addEventListener("click", onPageClick);
  bookmarks = loadBookmarks();
  applySavedTheme();
  initChapterNav();
  renderBookmarks();

  audio.addEventListener("loadedmetadata", () => {
    scrubber.max = String(audio.duration || 0);
    tTotal.textContent = fmt(audio.duration);
  });

  audio.addEventListener("timeupdate", () => {
    const t = audio.currentTime;
    scrubber.value = String(t);
    tCurrent.textContent = fmt(t);
    syncSentence(t);
  });

  audio.addEventListener("play", () => (playPause.textContent = "⏸"));
  audio.addEventListener("pause", () => (playPause.textContent = "▶"));

  scrubber.addEventListener("input", () => {
    audio.currentTime = Number(scrubber.value);
  });

  playPause.addEventListener("click", () => (audio.paused ? audio.play() : audio.pause()));
  prevBtn.addEventListener("click", () => jumpRelative(-1));
  nextBtn.addEventListener("click", () => jumpRelative(+1));
  speed.addEventListener("change", () => (audio.playbackRate = Number(speed.value)));
  chapterSelect.addEventListener("change", onChapterSelect);
  bookmarkAdd.addEventListener("click", addBookmarkAtCurrent);
  bookmarkSelect.addEventListener("change", onBookmarkSelect);
  themeToggle.addEventListener("click", toggleTheme);

  document.addEventListener("keydown", (e) => {
    if (e.target instanceof HTMLInputElement || e.target instanceof HTMLSelectElement) return;
    switch (e.key) {
      case " ":
        e.preventDefault();
        audio.paused ? audio.play() : audio.pause();
        break;
      case "ArrowLeft": audio.currentTime = Math.max(0, audio.currentTime - 5); break;
      case "ArrowRight": audio.currentTime = Math.min(audio.duration, audio.currentTime + 5); break;
      case ",":
        setRate(audio.playbackRate - 0.1);
        break;
      case ".":
        setRate(audio.playbackRate + 0.1);
        break;
      case "j": jumpRelative(-1); break;
      case "k": jumpRelative(+1); break;
    }
  });
  window.addEventListener("resize", () => {
    if (currentIdx >= 0) {
      syncPageVisuals(manifest.sentences[currentIdx]);
    }
  });

  setRate(Number(speed.value) || 1);
  const initialIdx = indexForTime(0);
  if (initialIdx >= 0) setActive(initialIdx);

  function syncSentence(t) {
    const idx = indexForTime(t);
    if (idx === -1 || idx === currentIdx) return;
    setActive(idx);
  }

  function setActive(idx) {
    if (currentIdx >= 0) list.children[currentIdx]?.classList.remove("active");
    currentIdx = idx;
    const li = list.children[idx];
    if (!li) return;
    li.classList.add("active");
    li.scrollIntoView({ block: "nearest", behavior: "smooth" });
    const s = manifest.sentences[idx];
    pageNum.textContent = String(s.page);
    syncPageVisuals(s);
    syncActiveChapter(idx);
  }

  function jumpRelative(delta) {
    const next = Math.max(0, Math.min(manifest.sentences.length - 1, currentIdx + delta));
    const s = manifest.sentences[next];
    if (s && typeof s.start_sec === "number") audio.currentTime = s.start_sec;
  }

  function setRate(nextRate) {
    const rate = Math.min(3.0, Math.max(0.5, Math.round(nextRate * 100) / 100));
    audio.playbackRate = rate;
    syncRateSelect(rate);
  }

  function syncRateSelect(rate) {
    const target = Number(rate).toFixed(2).replace(/\.00$/, "");
    let option = [...speed.options].find((o) => o.value === target);
    if (!option) {
      option = document.createElement("option");
      option.value = target;
      option.textContent = `${target}x`;
      speed.appendChild(option);
    }
    speed.value = target;
  }

  function indexForTime(t) {
    if (timeline.length === 0) return -1;
    let lo = 0;
    let hi = timeline.length - 1;
    while (lo <= hi) {
      const mid = (lo + hi) >> 1;
      const seg = timeline[mid];
      if (t < seg.start) {
        hi = mid - 1;
      } else if (t >= seg.end) {
        lo = mid + 1;
      } else {
        return seg.id;
      }
    }
    if (t >= timeline[timeline.length - 1].end) {
      return timeline[timeline.length - 1].id;
    }
    return -1;
  }

  function syncPageVisuals(sentence) {
    const page = pageByNumber.get(Number(sentence.page));
    if (!page || !page.image) {
      layout.classList.add("text-only");
      pageEmpty.classList.remove("hidden");
      pageStage.classList.add("hidden");
      return;
    }
    layout.classList.remove("text-only");
    pageEmpty.classList.add("hidden");
    pageStage.classList.remove("hidden");

    const updateOverlay = () => placeOverlay(sentence, page);

    if (currentPage !== page.number || !pageImage.getAttribute("src")) {
      currentPage = page.number;
      pageImage.onerror = () => {
        layout.classList.add("text-only");
        pageEmpty.classList.remove("hidden");
        pageStage.classList.add("hidden");
        overlay.style.opacity = "0";
      };
      pageImage.onload = () => updateOverlay();
      pageImage.setAttribute("src", page.image);
      if (pageImage.complete) updateOverlay();
    } else {
      updateOverlay();
    }
  }

  function placeOverlay(sentence, page) {
    if (!Array.isArray(sentence.bbox) || sentence.bbox.length !== 4) {
      overlay.style.opacity = "0";
      return;
    }
    if (!pageImage.naturalWidth || !pageImage.naturalHeight) {
      overlay.style.opacity = "0";
      return;
    }
    const [x0, y0, x1, y1] = sentence.bbox.map((n) => Number(n));
    if (![x0, y0, x1, y1].every(Number.isFinite) || x1 <= x0 || y1 <= y0) {
      overlay.style.opacity = "0";
      return;
    }

    const sx = pageImage.clientWidth / Number(page.pdf_width_pt || 1);
    const sy = pageImage.clientHeight / Number(page.pdf_height_pt || 1);
    overlay.style.left = `${x0 * sx}px`;
    overlay.style.top = `${y0 * sy}px`;
    overlay.style.width = `${Math.max(1, (x1 - x0) * sx)}px`;
    overlay.style.height = `${Math.max(1, (y1 - y0) * sy)}px`;
    overlay.style.opacity = "1";
  }

  function onPageClick(event) {
    if (!pageImage.getAttribute("src") || currentPage == null) return;
    const page = pageByNumber.get(Number(currentPage));
    if (!page) return;
    const ids = sentencesByPage.get(Number(currentPage)) || [];
    if (ids.length === 0) return;

    const rect = pageImage.getBoundingClientRect();
    const xPx = event.clientX - rect.left;
    const yPx = event.clientY - rect.top;
    if (xPx < 0 || yPx < 0 || xPx > rect.width || yPx > rect.height) return;

    const xPt = (xPx / rect.width) * Number(page.pdf_width_pt || 1);
    const yPt = (yPx / rect.height) * Number(page.pdf_height_pt || 1);

    const containing = [];
    for (const id of ids) {
      const s = manifest.sentences[id];
      if (!Array.isArray(s?.bbox) || s.bbox.length !== 4) continue;
      const [x0, y0, x1, y1] = s.bbox.map((n) => Number(n));
      if (xPt >= x0 && xPt <= x1 && yPt >= y0 && yPt <= y1) {
        containing.push(id);
      }
    }

    let targetId = null;
    if (containing.length > 0) {
      targetId = containing.sort((a, b) => a - b)[0];
    } else {
      // Fallback: nearest bbox center on the current page.
      let bestDist = Infinity;
      for (const id of ids) {
        const s = manifest.sentences[id];
        if (!Array.isArray(s?.bbox) || s.bbox.length !== 4) continue;
        const [x0, y0, x1, y1] = s.bbox.map((n) => Number(n));
        const cx = (x0 + x1) / 2;
        const cy = (y0 + y1) / 2;
        const dx = cx - xPt;
        const dy = cy - yPt;
        const d2 = dx * dx + dy * dy;
        if (d2 < bestDist) {
          bestDist = d2;
          targetId = id;
        }
      }
    }

    if (targetId == null) return;
    const target = manifest.sentences[targetId];
    if (typeof target.start_sec === "number") {
      audio.currentTime = target.start_sec;
      if (audio.paused) {
        void audio.play().catch(() => {});
      }
    }
  }

  function initChapterNav() {
    if (!chapters.length) {
      chapterWrap.classList.add("hidden");
      return;
    }
    chapters.sort((a, b) => a.sentence_id - b.sentence_id);
    chapterWrap.classList.remove("hidden");
    chapterSelect.innerHTML = "";
    const placeholder = document.createElement("option");
    placeholder.value = "";
    placeholder.textContent = "Jump to chapter";
    chapterSelect.appendChild(placeholder);
    for (const ch of chapters) {
      const option = document.createElement("option");
      option.value = String(ch.sentence_id);
      option.textContent = ch.title;
      chapterSelect.appendChild(option);
    }
  }

  function onChapterSelect() {
    const id = Number(chapterSelect.value);
    if (!Number.isFinite(id)) return;
    const sentence = manifest.sentences[id];
    if (!sentence || typeof sentence.start_sec !== "number") return;
    audio.currentTime = sentence.start_sec;
    if (audio.paused) void audio.play().catch(() => {});
  }

  function syncActiveChapter(activeSentenceId) {
    if (!chapters.length) return;
    let chosen = "";
    for (const ch of chapters) {
      if (ch.sentence_id <= activeSentenceId) {
        chosen = String(ch.sentence_id);
      } else {
        break;
      }
    }
    chapterSelect.value = chosen;
  }

  function addBookmarkAtCurrent() {
    if (currentIdx < 0) {
      const recovered = indexForTime(Number(audio.currentTime) || 0);
      if (recovered >= 0) {
        setActive(recovered);
      } else if (manifest.sentences.length > 0) {
        setActive(0);
      }
    }
    if (currentIdx < 0) return;
    const sentence = manifest.sentences[currentIdx];
    const now = Number(audio.currentTime || sentence.start_sec || 0);
    const entry = {
      id: `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
      sentence_id: sentence.id,
      page: sentence.page,
      time: now,
      label: bookmarkLabel(sentence, now),
    };
    bookmarks.push(entry);
    bookmarks.sort((a, b) => a.time - b.time);
    saveBookmarks();
    renderBookmarks();
    bookmarkSelect.value = entry.id;
  }

  function onBookmarkSelect() {
    const id = bookmarkSelect.value;
    if (!id) return;
    const bm = bookmarks.find((b) => b.id === id);
    if (!bm) return;
    audio.currentTime = Number(bm.time) || 0;
    if (audio.paused) void audio.play().catch(() => {});
  }

  function renderBookmarks() {
    const prev = bookmarkSelect.value;
    bookmarkSelect.innerHTML = "";
    const placeholder = document.createElement("option");
    placeholder.value = "";
    placeholder.textContent = "Bookmarks";
    bookmarkSelect.appendChild(placeholder);
    for (const bm of bookmarks) {
      const option = document.createElement("option");
      option.value = bm.id;
      option.textContent = bm.label;
      bookmarkSelect.appendChild(option);
    }
    if (bookmarks.some((b) => b.id === prev)) {
      bookmarkSelect.value = prev;
    }
  }

  function bookmarkLabel(sentence, timeSec) {
    const text = (sentence.text || "").replace(/\s+/g, " ").trim();
    const snippet = text.length > 36 ? `${text.slice(0, 33)}...` : text;
    return `${fmt(timeSec)} | p${sentence.page} | ${snippet}`;
  }

  function bookmarksStorageKey() {
    return `${storagePrefix}:bookmarks`;
  }

  function themeStorageKey() {
    return `${storagePrefix}:theme`;
  }

  function saveBookmarks() {
    try {
      window.localStorage.setItem(bookmarksStorageKey(), JSON.stringify(bookmarks));
    } catch (_) {
      // Ignore storage failures (private mode, quota, etc.)
    }
  }

  function loadBookmarks() {
    try {
      const raw = window.localStorage.getItem(bookmarksStorageKey());
      if (!raw) return [];
      const parsed = JSON.parse(raw);
      if (!Array.isArray(parsed)) return [];
      return parsed.filter((b) => b && typeof b.id === "string");
    } catch (_) {
      return [];
    }
  }

  function toggleTheme() {
    const current = document.body.dataset.theme === "light" ? "light" : "dark";
    const next = current === "light" ? "dark" : "light";
    setTheme(next);
  }

  function applySavedTheme() {
    let saved = null;
    try {
      saved = window.localStorage.getItem(themeStorageKey());
    } catch (_) {
      saved = null;
    }
    if (saved !== "light" && saved !== "dark") {
      saved = "dark";
    }
    setTheme(saved, false);
  }

  function setTheme(theme, persist = true) {
    document.body.dataset.theme = theme;
    themeToggle.textContent = theme === "light" ? "Dark" : "Light";
    if (!persist) return;
    try {
      window.localStorage.setItem(themeStorageKey(), theme);
    } catch (_) {
      // ignore
    }
  }

  async function loadManifest() {
    if (window.AUDIOBOOK_ISH_MANIFEST) {
      return window.AUDIOBOOK_ISH_MANIFEST;
    }
    const response = await fetch("manifest.json", { cache: "no-store" });
    if (!response.ok) throw new Error(`manifest.json: ${response.status}`);
    return response.json();
  }

  function fmt(t) {
    if (!isFinite(t)) return "0:00";
    const total = Math.max(0, Math.floor(t));
    const h = Math.floor(total / 3600);
    const m = Math.floor((total % 3600) / 60);
    const s = total % 60;
    const mm = String(m).padStart(h ? 2 : 1, "0");
    const ss = String(s).padStart(2, "0");
    return h ? `${h}:${mm}:${ss}` : `${mm}:${ss}`;
  }
})();
