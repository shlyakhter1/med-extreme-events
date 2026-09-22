/* Welcome / About: the dialog that opens over any page on a first visit, and the four-step
   guided tour of the Monitor.

   One localStorage key holds the version of the text that was seen, so bumping
   WELCOME_VERSION (views.py, rendered into data-version) shows it to everyone once more.
   The query string is read at parse time because playback.js rewrites the URL from its own
   state a moment later, dropping ?about= and ?tour=. */
(() => {
  const Q = new URLSearchParams(window.location.search || "");
  const SEEN = "mxe.welcome.seen";
  const HINTED = "mxe.welcome.hinted";

  const ls = {
    get(k) { try { return window.localStorage.getItem(k); } catch { return null; } },
    set(k, v) { try { window.localStorage.setItem(k, v); } catch { /* private browsing */ } },
  };
  const $ = (s) => document.querySelector(s);
  const clamp = (v, lo, hi) => Math.max(lo, Math.min(hi, v));
  const dlg = $("#welcome");
  const version = (dlg && dlg.dataset.version) || "0";
  // The pill is on every page, including /about, where no dialog is rendered.
  const tourUrl = ($("#about-btn") && $("#about-btn").dataset.tourUrl) || "/?tour=1";

  // ------------------------------------------------------------------ the dialog

  function openWelcome() {
    if (!dlg || dlg.open) return;
    dlg.showModal();
    document.body.classList.add("welcome-open");
    const h = dlg.querySelector("#welcome-title");
    if (h) h.focus();
  }

  /* Every exit is the same event: remember the version and close. ``stay`` is false when a
     link is about to navigate, so the hint is not spent on a page the visitor leaves. */
  function dismissWelcome(stay) {
    ls.set(SEEN, version);
    if (dlg && dlg.open) dlg.close();
    document.body.classList.remove("welcome-open");
    if (!stay) return;
    const btn = $("#about-btn");
    if (btn) btn.focus();
    showHint();
  }

  /* Said once, ever: where this screen lives now that it is gone. */
  function showHint() {
    const hint = $("#about-hint");
    if (!hint || ls.get(HINTED)) return;
    ls.set(HINTED, "1");
    hint.hidden = false;
    setTimeout(() => { hint.hidden = true; }, 4000);
  }

  document.addEventListener("click", (e) => {
    const t = e.target;
    if (!t || !t.closest) return;
    if (t.closest("#about-btn")) { e.preventDefault(); openWelcome(); return; }
    if (t.closest("[data-about-close]")) { e.preventDefault(); dismissWelcome(true); return; }
    if (t.closest("[data-about-go]")) dismissWelcome(false); // a real link: let it navigate
  });

  if (dlg) {
    dlg.addEventListener("cancel", (e) => { e.preventDefault(); dismissWelcome(true); });
    // A click on the ::backdrop is dispatched to the dialog itself, so it is outside the box.
    // Keyboard-activated clicks report detail 0 at (0,0) and must not read as a backdrop hit.
    dlg.addEventListener("click", (e) => {
      if (!e.detail) return;
      const r = dlg.getBoundingClientRect();
      const out = e.clientX < r.left || e.clientX > r.right || e.clientY < r.top || e.clientY > r.bottom;
      if (out) dismissWelcome(true);
    });
  }

  // ------------------------------------------------------------------ guided tour

  const STEPS = [
    {
      on: [".appbar .grp.transport", ".appbar .clock-grp"],
      title: "One clock drives everything",
      text: "This replay is Winter Storm Uri, Texas, February 2021. Press Play or step through time. The map, the cards and the timeline all update together.",
    },
    {
      on: ["#map-wrap"],
      title: "Where the event is",
      text: "Colored areas are active hazards: cold, storms, power outages. Dots are hospitals. Pink, violet and teal marks show which alert cards are firing there.",
    },
    {
      on: ["#side"],
      title: "Alert cards firing now",
      text: "Each card pairs a hazard with a patient group, for example a power outage with patients on dialysis. Open one to see the care-team steps, the patient guidance and how many patients it likely reaches.",
    },
    {
      on: ["footer.timeline"],
      title: "When each warning was active",
      text: "One lane per warning or data feed. The red line is now. Click anywhere to jump.",
    },
  ];
  const CARD_W = 320, GAP = 14, EDGE = 16, PAD = 4;
  let tour = null;

  /* The union of the step's targets, in viewport coordinates. */
  function targetRect(selectors) {
    let r = null;
    for (const sel of selectors) {
      const node = document.querySelector(sel);
      if (!node) continue;
      const b = node.getBoundingClientRect();
      if (!b.width && !b.height) continue;
      r = r
        ? { top: Math.min(r.top, b.top), left: Math.min(r.left, b.left),
            bottom: Math.max(r.bottom, b.bottom), right: Math.max(r.right, b.right) }
        : { top: b.top, left: b.left, bottom: b.bottom, right: b.right };
    }
    if (!r) return null;
    const vw = window.innerWidth, vh = window.innerHeight;
    return {
      top: clamp(r.top - PAD, 0, vh), left: clamp(r.left - PAD, 0, vw),
      bottom: clamp(r.bottom + PAD, 0, vh), right: clamp(r.right + PAD, 0, vw),
    };
  }

  /* Beside the target, never over it — except where the target is most of the screen (the
     map), which nothing can sit beside; there the card tucks into its top-left corner.
     On a phone it docks to the bottom instead, where a thumb already is. */
  function placeCard(card, r) {
    const vw = window.innerWidth, vh = window.innerHeight;
    if (vw < 700) {
      card.style.left = EDGE + "px";
      card.style.right = EDGE + "px";
      card.style.width = "auto";
      card.style.top = "auto";
      card.style.bottom = EDGE + "px";
      return;
    }
    card.style.right = "auto";
    card.style.bottom = "auto";
    card.style.width = CARD_W + "px";
    const h = card.offsetHeight || 200;
    const w = r.right - r.left, hgt = r.bottom - r.top;
    let top, left;
    if (hgt > h + 80 && w > CARD_W + 80) { top = r.top + 24; left = r.left + 24; }
    else if (vh - r.bottom - GAP - EDGE >= h) { top = r.bottom + GAP; left = r.left; }
    else if (r.top - GAP - EDGE >= h) { top = r.top - GAP - h; left = r.left; }
    else if (r.left - GAP - EDGE >= CARD_W) { left = r.left - GAP - CARD_W; top = r.top; }
    else if (vw - r.right - GAP - EDGE >= CARD_W) { left = r.right + GAP; top = r.top; }
    else { top = vh - h - EDGE; left = EDGE; }
    card.style.top = clamp(top, EDGE, Math.max(EDGE, vh - h - EDGE)) + "px";
    card.style.left = clamp(left, EDGE, Math.max(EDGE, vw - CARD_W - EDGE)) + "px";
  }

  /* Draw the step: text, dots, the hole in the dim layer, the ring, the card. Also the resize
     handler — placement is never cached, because the Monitor's panes move with the window. */
  function drawTour() {
    if (!tour) return;
    const el = tour.el, s = STEPS[tour.step], last = tour.step === STEPS.length - 1;
    el.querySelector(".tc-n").textContent = `${tour.step + 1} of ${STEPS.length}`;
    el.querySelector("#tour-title").textContent = s.title;
    el.querySelector(".tc-text").textContent = s.text;
    el.querySelector(".tc-next").textContent = last ? "Start exploring" : "Next";
    el.querySelector(".tc-back").disabled = tour.step === 0;
    el.querySelector(".tc-dots").innerHTML = STEPS.map(
      (_, i) => `<i${i === tour.step ? ' class="on"' : ""}></i>`).join("");

    const r = targetRect(s.on) || { top: 0, left: 0, bottom: 0, right: 0 };
    const px = (n) => n + "px";
    const dim = (side, css) => Object.assign(el.querySelector(`.tour-dim[data-e="${side}"]`).style, css);
    // Anchored to the overlay's own edges rather than sized from innerHeight, which is stale
    // for as long as the window is still settling: a short panel leaves a bright band.
    dim("t", { top: "0", left: "0", right: "0", bottom: "auto", height: px(r.top) });
    dim("b", { top: px(r.bottom), left: "0", right: "0", bottom: "0", height: "auto" });
    dim("l", { top: px(r.top), left: "0", right: "auto", width: px(r.left), height: px(r.bottom - r.top) });
    dim("r", { top: px(r.top), left: px(r.right), right: "0", width: "auto", height: px(r.bottom - r.top) });
    Object.assign(el.querySelector(".tour-ring").style, {
      top: px(r.top), left: px(r.left), width: px(r.right - r.left), height: px(r.bottom - r.top),
    });
    placeCard(el.querySelector(".tour-card"), r);
  }

  function startTour() {
    if (tour || !document.getElementById("map-wrap")) return;
    const el = document.createElement("div");
    el.className = "tour";
    el.innerHTML =
      '<div class="tour-dim" data-e="t"></div><div class="tour-dim" data-e="r"></div>' +
      '<div class="tour-dim" data-e="b"></div><div class="tour-dim" data-e="l"></div>' +
      '<div class="tour-ring"></div>' +
      '<div class="tour-card" role="dialog" aria-live="polite" aria-labelledby="tour-title">' +
      '<div class="tc-top"><span class="tc-n mono"></span>' +
      '<button type="button" class="tc-skip" data-tour="end">Skip tour</button></div>' +
      '<h3 id="tour-title"></h3><p class="tc-text"></p>' +
      '<div class="tc-foot"><div class="tc-dots"></div>' +
      '<button type="button" class="tc-back" data-tour="back">Back</button>' +
      '<button type="button" class="tc-next" data-tour="next"></button></div></div>';
    document.body.appendChild(el);
    tour = { el, step: 0 };
    drawTour();
    // Again once the Monitor has laid its panes out, so the first ring is not drawn around
    // where the map was before the scenario loaded.
    window.requestAnimationFrame(drawTour);
    window.addEventListener("load", drawTour);
    el.querySelector(".tc-next").focus();
    window.addEventListener("resize", drawTour);
    window.addEventListener("scroll", drawTour, true);
  }

  /* Finishing and skipping both count as having seen the welcome. */
  function endTour() {
    if (!tour) return;
    window.removeEventListener("resize", drawTour);
    window.removeEventListener("load", drawTour);
    window.removeEventListener("scroll", drawTour, true);
    tour.el.remove();
    tour = null;
    ls.set(SEEN, version);
    const btn = $("#about-btn");
    if (btn) btn.focus();
  }

  function stepTour(d) {
    if (!tour) return;
    const next = tour.step + d;
    if (next >= STEPS.length) { endTour(); return; }
    tour.step = Math.max(0, next);
    drawTour();
  }

  document.addEventListener("click", (e) => {
    const b = e.target && e.target.closest && e.target.closest("[data-tour]");
    if (!b) return;
    e.preventDefault();
    if (b.dataset.tour === "end") endTour();
    else stepTour(b.dataset.tour === "back" ? -1 : 1);
  });

  // Captured, so the Monitor's own ←/→ (step the clock) and Esc (close the detail) stay put
  // while the tour owns them.
  window.addEventListener("keydown", (e) => {
    if (!tour) return;
    const key = e.key;
    if (key !== "ArrowLeft" && key !== "ArrowRight" && key !== "Escape") return;
    e.preventDefault();
    e.stopPropagation();
    if (key === "Escape") endTour();
    else stepTour(key === "ArrowRight" ? 1 : -1);
  }, true);

  // ------------------------------------------------------------------ what opens on load

  if (Q.get("tour") === "1") {
    // The tour needs the Monitor's panes; from anywhere else, go there and start on arrival.
    if (document.getElementById("map-wrap")) { ls.set(SEEN, version); startTour(); }
    else window.location.replace(tourUrl);
  } else if (Q.get("about") === "1" || ls.get(SEEN) !== version) {
    openWelcome();
  }
})();
