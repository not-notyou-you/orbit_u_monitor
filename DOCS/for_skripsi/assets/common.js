/* Navigasi, penomoran gambar/tabel, dan ekspor (SVG, PNG, salin tabel, salin sumber). */
(function () {
  const PAGES = [
    ["index.html", "0", "Daftar isi"],
    ["01-alur-penelitian.html", "1", "Alur penelitian & metode"],
    ["02-analisis-sistem.html", "2", "Analisis sistem & masalah"],
    ["03-perencanaan.html", "3", "Perencanaan & definisi sistem"],
    ["04-erd-konseptual.html", "4", "ERD konseptual"],
    ["05-erd-logikal.html", "5", "ERD logikal & multiplicity"],
    ["06-normalisasi.html", "6", "Normalisasi"],
    ["07-erd-fisik.html", "7", "ERD fisik & kamus data"],
    ["08-keamanan.html", "8", "Keamanan, VIEW, indeks"],
    ["09-dbms.html", "9", "Pemilihan DBMS"],
    ["10-use-case.html", "10", "Use case diagram"],
    ["11-activity.html", "11", "Activity diagram"],
    ["12-sequence-class.html", "12", "Sequence & class diagram"],
    ["13-arsitektur.html", "13", "Arsitektur & alur data"],
    ["14-antarmuka.html", "14", "Desain antarmuka"],
    ["15-testing.html", "15", "Testing"],
  ];

  function buildNav() {
    const here = location.pathname.split("/").pop() || "index.html";
    const nav = document.createElement("nav");
    nav.className = "side";
    nav.innerHTML =
      '<div class="brand">Visual Skripsi<small>Orbit-U: The Monitor · GMLS</small></div><ol>' +
      PAGES.map(([f, n, t]) => `<li><a href="${f}" class="${f === here ? "on" : ""}"><span class="n">${n}</span>${t}</a></li>`).join("") +
      '</ol><div class="tools"><p>Setiap gambar punya tombol <b>SVG</b>/<b>PNG</b>; setiap tabel punya <b>Salin tabel</b> (tempel langsung ke Word).</p>' +
      '<button id="themeBtn">Ganti terang/gelap</button></div>';
    document.body.prepend(nav);
    document.getElementById("themeBtn").onclick = () => {
      const r = document.documentElement;
      const dark = r.dataset.theme ? r.dataset.theme === "dark" : matchMedia("(prefers-color-scheme: dark)").matches;
      r.dataset.theme = dark ? "light" : "dark";
      try { localStorage.setItem("skripsi.theme", r.dataset.theme); } catch (e) {}
    };
  }
  try { const t = localStorage.getItem("skripsi.theme"); if (t) document.documentElement.dataset.theme = t; } catch (e) {}

  function slug(s) { return (s || "gambar").toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "").slice(0, 60); }

  function download(name, blob) {
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = name;
    a.click();
    setTimeout(() => URL.revokeObjectURL(a.href), 2000);
  }

  function svgString(svg) {
    const clone = svg.cloneNode(true);
    clone.setAttribute("xmlns", "http://www.w3.org/2000/svg");
    const bb = svg.getBoundingClientRect();
    if (!clone.getAttribute("width")) clone.setAttribute("width", Math.ceil(bb.width));
    if (!clone.getAttribute("height")) clone.setAttribute("height", Math.ceil(bb.height));
    clone.style.maxWidth = "none";
    // latar putih supaya PNG tidak transparan di Word
    const bg = document.createElementNS("http://www.w3.org/2000/svg", "rect");
    bg.setAttribute("width", "100%"); bg.setAttribute("height", "100%"); bg.setAttribute("fill", "#ffffff");
    clone.insertBefore(bg, clone.firstChild);
    return new XMLSerializer().serializeToString(clone);
  }

  function svgSize(svg) {
    const vb = svg.viewBox && svg.viewBox.baseVal;
    const bb = svg.getBoundingClientRect();
    return { w: Math.ceil(bb.width || (vb && vb.width) || 800), h: Math.ceil(bb.height || (vb && vb.height) || 600) };
  }

  function toPng(svg, name, scale = 3) {
    const { w, h } = svgSize(svg);
    const str = svgString(svg).replace(/<svg([^>]*?) width="[^"]*"/, `<svg$1 width="${w}"`).replace(/<svg([^>]*?) height="[^"]*"/, `<svg$1 height="${h}"`);
    const img = new Image();
    img.onload = () => {
      const c = document.createElement("canvas");
      c.width = w * scale; c.height = h * scale;
      const ctx = c.getContext("2d");
      ctx.fillStyle = "#fff"; ctx.fillRect(0, 0, c.width, c.height);
      ctx.drawImage(img, 0, 0, c.width, c.height);
      c.toBlob((b) => download(name + ".png", b));
    };
    img.onerror = () => alert("PNG gagal dibuat di peramban ini. Pakai tombol SVG lalu buka di draw.io/Inkscape.");
    img.src = "data:image/svg+xml;charset=utf-8," + encodeURIComponent(str);
  }

  async function copyHtml(el, btn) {
    const html = el.outerHTML;
    try {
      await navigator.clipboard.write([new ClipboardItem({
        "text/html": new Blob([html], { type: "text/html" }),
        "text/plain": new Blob([el.innerText], { type: "text/plain" }),
      })]);
    } catch (e) {
      const r = document.createRange(); r.selectNode(el);
      const s = getSelection(); s.removeAllRanges(); s.addRange(r); document.execCommand("copy"); s.removeAllRanges();
    }
    flash(btn);
  }
  async function copyText(text, btn) {
    try { await navigator.clipboard.writeText(text); } catch (e) {
      const ta = document.createElement("textarea"); ta.value = text; document.body.append(ta); ta.select(); document.execCommand("copy"); ta.remove();
    }
    flash(btn);
  }
  function flash(btn) { const t = btn.textContent; btn.textContent = "Tersalin ✓"; setTimeout(() => (btn.textContent = t), 1200); }

  const counters = { Gambar: 0, Tabel: 0 };
  function decorate(fig) {
    if (fig.dataset.done) return;
    fig.dataset.done = 1;
    const kind = fig.dataset.kind || (fig.querySelector("table.t") && !fig.querySelector("svg,.mermaid,canvas") ? "Tabel" : "Gambar");
    const bab = document.body.dataset.bab || "";
    const num = `${kind} ${bab ? bab + "." : ""}${++counters[kind]}`;
    const cap = fig.dataset.cap || "";
    const name = slug(`${num} ${cap}`);
    const bar = document.createElement("div");
    bar.className = "bar";
    bar.innerHTML = `<span class="cap">${num} ${cap}</span>`;
    const body = fig.querySelector(".body");
    const add = (label, fn) => { const b = document.createElement("button"); b.textContent = label; b.onclick = () => fn(b); bar.append(b); };
    const getSvg = () => body.querySelector("svg");
    if (kind === "Gambar") {
      add("SVG", () => { const s = getSvg(); if (s) download(name + ".svg", new Blob([svgString(s)], { type: "image/svg+xml" })); else exportCanvas(); });
      add("PNG", () => { const s = getSvg(); if (s) toPng(s, name); else exportCanvas(); });
      function exportCanvas() { const c = body.querySelector("canvas"); if (c) c.toBlob((b) => download(name + ".png", b)); }
    }
    body.querySelectorAll("table.t").forEach((t, i) => add(i ? `Salin tabel ${i + 1}` : "Salin tabel", (b) => copyHtml(t, b)));
    const src = fig.querySelector("[data-src]") || (fig.dataset.src ? fig : null);
    if (src) add(src.dataset.srcLabel || "Salin sumber Mermaid", (b) => copyText(src.dataset.src, b));
    fig.prepend(bar);
    if (cap && !fig.dataset.nocap) {
      const c = document.createElement("div");
      c.className = "caption";
      c.innerHTML = `<b>${num}</b> ${cap}${fig.dataset.from ? `<br><span>Sumber: ${fig.dataset.from}</span>` : ""}`;
      fig.append(c);
    }
  }

  async function renderMermaid() {
    const blocks = [...document.querySelectorAll("pre.mermaid")];
    if (!blocks.length || !window.mermaid) return;
    blocks.forEach((b) => { b.dataset.src = b.textContent.trim(); });
    mermaid.initialize({
      startOnLoad: false, theme: "base", securityLevel: "loose",
      themeVariables: {
        background: "#ffffff", primaryColor: "#ffffff", primaryBorderColor: "#2b2f36", primaryTextColor: "#1d1f22",
        lineColor: "#2b2f36", secondaryColor: "#f3f6f8", tertiaryColor: "#ffffff", fontFamily: "Arial, sans-serif", fontSize: "14px",
        clusterBkg: "#fafbfc", clusterBorder: "#6b7280", edgeLabelBackground: "#ffffff",
        actorBkg: "#ffffff", actorBorder: "#2b2f36", noteBkgColor: "#fff8d6", noteBorderColor: "#b49b3c",
      },
      er: { useMaxWidth: false }, flowchart: { useMaxWidth: false, htmlLabels: true }, sequence: { useMaxWidth: false, mirrorActors: false },
      class: { useMaxWidth: false },
    });
    for (const b of blocks) {
      try { await mermaid.run({ nodes: [b] }); }
      catch (e) {
        console.error(e);
        b.outerHTML = `<div class="note render-error">Diagram gagal dirender: ${String(e.message || e).slice(0, 300)}</div>`;
      }
    }
  }
  window.addEventListener("error", (e) => {
    document.body.insertAdjacentHTML("afterbegin", `<div class="note render-error">Galat JS: ${e.message}</div>`);
  });

  window.Skripsi = {
    decorateAll() { document.querySelectorAll(".fig").forEach(decorate); },
    esc: (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c])),
    fmt: (n, d = 0) => Number(n).toLocaleString("id-ID", { minimumFractionDigits: d, maximumFractionDigits: d }),
  };

  document.addEventListener("DOMContentLoaded", async () => {
    buildNav();
    if (window.pageInit) await window.pageInit();
    try { await renderMermaid(); } catch (e) { console.error(e); }
    window.Skripsi.decorateAll();
  });
})();
