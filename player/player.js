/*
 * audiobook-ish player — barebones.
 *
 * Loads manifest.json + audiobook.mp3 (and pages/*.png referenced inside the
 * manifest). Highlights the current sentence on the text panel and overlays a
 * yellow rectangle on the rendered PDF page.
 *
 * Wire-up details to flesh out in M4/M5; this stub gets the structure right.
 */

(async () => {
  const audio = document.getElementById("audio");
  const list = document.getElementById("sentence-list");
  const pageImage = document.getElementById("page-image");
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

  let manifest = null;
  let currentIdx = -1;
  let pageById = new Map();

  try {
    manifest = await fetch("manifest.json", { cache: "no-store" }).then((r) => {
      if (!r.ok) throw new Error(`manifest.json: ${r.status}`);
      return r.json();
    });
  } catch (err) {
    titleEl.textContent = "Could not load manifest.json — open this player from inside a generated example folder.";
    console.error(err);
    return;
  }

  titleEl.textContent = manifest.source_pdf || "audiobook-ish";
  pageTotal.textContent = String(manifest.page_count ?? "—");
  pageById = new Map((manifest.pages || []).map((p) => [p.number, p]));

  // Render the sentence list.
  for (const s of manifest.sentences) {
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

  document.addEventListener("keydown", (e) => {
    if (e.target instanceof HTMLInputElement || e.target instanceof HTMLSelectElement) return;
    switch (e.key) {
      case " ":
        e.preventDefault();
        audio.paused ? audio.play() : audio.pause();
        break;
      case "ArrowLeft": audio.currentTime = Math.max(0, audio.currentTime - 5); break;
      case "ArrowRight": audio.currentTime = Math.min(audio.duration, audio.currentTime + 5); break;
      case "j": jumpRelative(-1); break;
      case "k": jumpRelative(+1); break;
    }
  });

  function syncSentence(t) {
    // TODO(M4): binary search instead of linear scan.
    const idx = manifest.sentences.findIndex(
      (s) => typeof s.start_sec === "number" && typeof s.end_sec === "number" && t >= s.start_sec && t < s.end_sec,
    );
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
    showPage(s);
  }

  function showPage(s) {
    const page = pageById.get(s.page);
    if (!page) return;
    if (!pageImage.src.endsWith(page.image)) pageImage.src = page.image;
    pageImage.onload = () => positionOverlay(s, page);
    if (pageImage.complete) positionOverlay(s, page);
  }

  function positionOverlay(s, page) {
    if (!Array.isArray(s.bbox) || s.bbox.length !== 4) {
      overlay.style.opacity = "0";
      return;
    }
    const rect = pageImage.getBoundingClientRect();
    const stage = pageImage.parentElement.getBoundingClientRect();
    const sx = pageImage.clientWidth / page.pdf_width_pt;
    const sy = pageImage.clientHeight / page.pdf_height_pt;
    const [x0, y0, x1, y1] = s.bbox;
    overlay.style.left = `${(rect.left - stage.left) + x0 * sx}px`;
    overlay.style.top = `${(rect.top - stage.top) + y0 * sy}px`;
    overlay.style.width = `${(x1 - x0) * sx}px`;
    overlay.style.height = `${(y1 - y0) * sy}px`;
    overlay.style.opacity = "1";
  }

  function jumpRelative(delta) {
    const next = Math.max(0, Math.min(manifest.sentences.length - 1, currentIdx + delta));
    const s = manifest.sentences[next];
    if (s && typeof s.start_sec === "number") audio.currentTime = s.start_sec;
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
