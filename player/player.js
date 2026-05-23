/* audiobook-ish player (M4): text-only sync */

(async () => {
  const audio = document.getElementById("audio");
  const list = document.getElementById("sentence-list");
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
  const timeline = [];

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
  const inferredTotalPages = manifest.page_count
    || Math.max(...manifest.sentences.map((s) => Number(s.page) || 0), 0)
    || "—";
  pageTotal.textContent = String(inferredTotalPages);

  // Build sentence list + lookup timeline.
  for (const s of manifest.sentences) {
    const start = Number(s.start_sec);
    const end = Number(s.end_sec);
    if (Number.isFinite(start) && Number.isFinite(end) && end > start) {
      timeline.push({ id: s.id, start, end });
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
