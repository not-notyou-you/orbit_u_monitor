/* Renderer UML kecil berbasis SVG: use case diagram (notasi UML 2.x) dan activity diagram ber-swimlane.
   Tata letak ditentukan spesifikasi (kolom/baris), sehingga hasilnya stabil dan mudah ditiru di draw.io. */
(function () {
  const NS = "http://www.w3.org/2000/svg";
  const FONT = "Arial, Helvetica, sans-serif";
  const INK = "#1d1f22";

  function el(tag, attrs = {}, parent) {
    const e = document.createElementNS(NS, tag);
    for (const [k, v] of Object.entries(attrs)) if (v !== undefined && v !== null) e.setAttribute(k, v);
    if (parent) parent.append(e);
    return e;
  }
  function wrap(text, max) {
    const out = [];
    String(text).split("\n").forEach((para) => {
      let line = "";
      para.split(" ").forEach((w) => {
        if ((line + " " + w).trim().length > max && line) { out.push(line); line = w; }
        else line = (line + " " + w).trim();
      });
      out.push(line);
    });
    return out;
  }
  function textBlock(g, x, y, lines, opts = {}) {
    const lh = opts.lh || 15;
    const t = el("text", {
      x, y: y - ((lines.length - 1) * lh) / 2, "text-anchor": opts.anchor || "middle", "dominant-baseline": "central",
      "font-family": FONT, "font-size": opts.size || 12.5, fill: opts.fill || INK,
      "font-style": opts.italic ? "italic" : null, "font-weight": opts.bold ? "bold" : null,
    }, g);
    lines.forEach((ln, i) => { const s = el("tspan", { x, dy: i ? lh : 0 }, t); s.textContent = ln; });
    return t;
  }
  function defs(svg) {
    const d = el("defs", {}, svg);
    const open = el("marker", { id: "arrOpen", viewBox: "0 0 12 12", refX: 11, refY: 6, markerWidth: 11, markerHeight: 11, orient: "auto-start-reverse", markerUnits: "userSpaceOnUse" }, d);
    el("path", { d: "M1,1 L11,6 L1,11", fill: "none", stroke: INK, "stroke-width": 1.4 }, open);
    const fill = el("marker", { id: "arrFill", viewBox: "0 0 12 12", refX: 11, refY: 6, markerWidth: 10, markerHeight: 10, orient: "auto", markerUnits: "userSpaceOnUse" }, d);
    el("path", { d: "M0,1 L11,6 L0,11 z", fill: INK }, fill);
    const tri = el("marker", { id: "arrTri", viewBox: "0 0 16 16", refX: 15, refY: 8, markerWidth: 16, markerHeight: 16, orient: "auto", markerUnits: "userSpaceOnUse" }, d);
    el("path", { d: "M1,1 L15,8 L1,15 z", fill: "#fff", stroke: INK, "stroke-width": 1.3 }, tri);
  }

  function stickman(g, x, y, name) {
    // y = posisi kepala
    el("circle", { cx: x, cy: y, r: 9, fill: "#fff", stroke: INK, "stroke-width": 1.6 }, g);
    el("line", { x1: x, y1: y + 9, x2: x, y2: y + 34, stroke: INK, "stroke-width": 1.6 }, g);
    el("line", { x1: x - 15, y1: y + 18, x2: x + 15, y2: y + 18, stroke: INK, "stroke-width": 1.6 }, g);
    el("line", { x1: x, y1: y + 34, x2: x - 12, y2: y + 52, stroke: INK, "stroke-width": 1.6 }, g);
    el("line", { x1: x, y1: y + 34, x2: x + 12, y2: y + 52, stroke: INK, "stroke-width": 1.6 }, g);
    textBlock(g, x, y + 68, wrap(name, 16), { size: 12.5, bold: true });
  }

  function clipEllipse(cx, cy, rx, ry, px, py) {
    const dx = px - cx, dy = py - cy;
    const t = 1 / Math.sqrt((dx / rx) ** 2 + (dy / ry) ** 2);
    return [cx + dx * t, cy + dy * t];
  }

  /* ---------- Use case ---------- */
  function useCase(container, spec) {
    const ROW = spec.rowH || 62, PADT = 50;
    const col0 = spec.col0 || 400, col1 = spec.col1 || 720;
    const nodes = {};
    const main = spec.cases.filter((c) => !c.col);
    const sec = spec.cases.filter((c) => c.col);
    const ell = (c) => {
      const lines = wrap(c.name, c.wrap || 24);
      const longest = Math.max(...lines.map((l) => l.length));
      return { lines, rx: Math.max(70, longest * 3.6 + 26), ry: Math.max(22, lines.length * 8 + 12) };
    };
    main.forEach((c, i) => { nodes[c.id] = { ...c, ...ell(c), x: col0, y: PADT + 30 + i * ROW + (c.dy || 0) }; });
    let lastY = -1e9;
    sec.forEach((c) => {
      const srcs = spec.rel.filter((r) => r.to === c.id || r.from === c.id).map((r) => nodes[r.to === c.id ? r.from : r.to]).filter(Boolean);
      let y = srcs.length ? srcs.reduce((s, n) => s + n.y, 0) / srcs.length : PADT + 30;
      y = Math.max(y, lastY + ROW * 0.95);
      lastY = y;
      nodes[c.id] = { ...c, ...ell(c), x: c.x || col1, y: y + (c.dy || 0) };
    });
    const maxY = Math.max(...Object.values(nodes).map((n) => n.y + n.ry)) + 30;
    const hasSec = sec.length > 0;
    const bx = col0 - 150, bw = (hasSec ? col1 + 150 : col0 + 150) - bx;
    const leftActors = spec.actors.filter((a) => a.side !== "right");
    const rightActors = spec.actors.filter((a) => a.side === "right");
    const W = bx + bw + (rightActors.length ? 170 : 40);
    const H = Math.max(maxY + 20, 120 + spec.actors.length * 40);
    const svg = el("svg", { width: W, height: H, viewBox: `0 0 ${W} ${H}`, "font-family": FONT });
    defs(svg);
    el("rect", { width: W, height: H, fill: "#fff" }, svg);
    el("rect", { x: bx, y: 10, width: bw, height: H - 20, fill: "#fff", stroke: INK, "stroke-width": 1.4 }, svg);
    textBlock(svg, bx + bw / 2, 30, [spec.title || "Orbit-U: The Monitor"], { bold: true, size: 13.5 });

    const placeActors = (list, x) => {
      list.forEach((a, i) => {
        const linked = spec.links.filter((l) => l.a === a.id).map((l) => nodes[l.u]).filter(Boolean);
        let y = a.y || (linked.length ? linked.reduce((s, n) => s + n.y, 0) / linked.length : (H / (list.length + 1)) * (i + 1));
        a._x = x; a._y = y - 30;
      });
    };
    placeActors(leftActors, bx - 95);
    placeActors(rightActors, bx + bw + 80);

    const gl = el("g", {}, svg);
    spec.links.forEach((l) => {
      const a = spec.actors.find((x) => x.id === l.a), n = nodes[l.u];
      if (!a || !n) return;
      const ax = a._x + (a.side === "right" ? -18 : 18), ay = a._y + 26;
      const [ex, ey] = clipEllipse(n.x, n.y, n.rx, n.ry, ax, ay);
      el("line", { x1: ax, y1: ay, x2: ex, y2: ey, stroke: INK, "stroke-width": 1.2 }, gl);
    });
    (spec.gen || []).forEach((g) => {
      const c = spec.actors.find((x) => x.id === g.child), p = spec.actors.find((x) => x.id === g.parent);
      el("line", { x1: c._x, y1: c._y + (p._y < c._y ? -12 : 62), x2: p._x, y2: p._y + (p._y < c._y ? 80 : -12), stroke: INK, "stroke-width": 1.2, "marker-end": "url(#arrTri)" }, gl);
    });
    spec.rel.forEach((r) => {
      const f = nodes[r.from], t = nodes[r.to];
      const [x1, y1] = clipEllipse(f.x, f.y, f.rx, f.ry, t.x, t.y);
      const [x2, y2] = clipEllipse(t.x, t.y, t.rx, t.ry, f.x, f.y);
      el("line", { x1, y1, x2, y2, stroke: INK, "stroke-width": 1.1, "stroke-dasharray": "6 4", "marker-end": "url(#arrOpen)" }, gl);
      const mx = (x1 + x2) / 2, my = (y1 + y2) / 2;
      el("rect", { x: mx - 30, y: my - 9, width: 60, height: 16, fill: "#fff" }, gl);
      textBlock(gl, mx, my - 1, [`«${r.type}»`], { size: 11, italic: true });
    });
    Object.values(nodes).forEach((n) => {
      el("ellipse", { cx: n.x, cy: n.y, rx: n.rx, ry: n.ry, fill: "#fff", stroke: INK, "stroke-width": 1.4 }, svg);
      textBlock(svg, n.x, n.y, n.lines, { size: 12.2 });
    });
    spec.actors.forEach((a) => stickman(svg, a._x, a._y, a.name));
    container.append(svg);
    return svg;
  }

  /* Pohon generalisasi aktor (posisi manual). */
  function actorTree(container, spec) {
    const svg = el("svg", { width: spec.w, height: spec.h, viewBox: `0 0 ${spec.w} ${spec.h}`, "font-family": FONT });
    defs(svg);
    el("rect", { width: spec.w, height: spec.h, fill: "#fff" }, svg);
    const pos = Object.fromEntries(spec.actors.map((a) => [a.id, a]));
    spec.gen.forEach((g) => {
      const c = pos[g.child], p = pos[g.parent];
      el("line", { x1: c.x, y1: c.y - 14, x2: p.x, y2: p.y + 88, stroke: INK, "stroke-width": 1.3, "marker-end": "url(#arrTri)" }, svg);
    });
    spec.actors.forEach((a) => stickman(svg, a.x, a.y, a.name));
    (spec.notes || []).forEach((n) => textBlock(svg, n.x, n.y, wrap(n.text, n.wrap || 40), { size: 11.5, fill: "#555", italic: true }));
    container.append(svg);
    return svg;
  }

  /* ---------- Activity ber-swimlane ---------- */
  function activity(container, spec) {
    const LW = spec.laneW || 250, RH = spec.rowH || 74, TOP = 54, PADB = 30;
    const nLanes = spec.lanes.length;
    const W = LW * nLanes + 2;
    const maxRow = Math.max(...spec.nodes.map((n) => n.row));
    const H = TOP + (maxRow + 1) * RH + PADB;
    const svg = el("svg", { width: W, height: H, viewBox: `0 0 ${W} ${H}`, "font-family": FONT });
    defs(svg);
    el("rect", { width: W, height: H, fill: "#fff" }, svg);
    spec.lanes.forEach((l, i) => {
      el("rect", { x: 1 + i * LW, y: 1, width: LW, height: H - 2, fill: "#fff", stroke: INK, "stroke-width": 1.3 }, svg);
      el("rect", { x: 1 + i * LW, y: 1, width: LW, height: 34, fill: "#eef2f5", stroke: INK, "stroke-width": 1.3 }, svg);
      textBlock(svg, 1 + i * LW + LW / 2, 18, [l], { bold: true, size: 13 });
    });
    const N = {};
    spec.nodes.forEach((n) => {
      const cx = 1 + n.lane * LW + LW / 2 + (n.dx || 0) * LW;
      const cy = TOP + n.row * RH + RH / 2 - 6;
      let w = 0, h = 0, lines = [];
      if (n.type === "action") { lines = wrap(n.text, n.wrap || 28); w = Math.min(LW - 24, Math.max(120, Math.max(...lines.map((s) => s.length)) * 6.6 + 24)); h = lines.length * 15 + 18; }
      else if (n.type === "decision" || n.type === "merge") { w = 30; h = 30; }
      else if (n.type === "start") { w = h = 22; }
      else if (n.type === "end" || n.type === "flowEnd") { w = h = 26; }
      else if (n.type === "fork" || n.type === "join") { w = (n.span || 1) * LW - 60; h = 7; }
      N[n.id] = { ...n, cx: n.type === "fork" || n.type === "join" ? 1 + n.lane * LW + ((n.span || 1) * LW) / 2 : cx, cy, w, h, lines };
    });

    const ge = el("g", {}, svg);
    const port = (n, side) => {
      if (side === "b") return [n.cx, n.cy + n.h / 2];
      if (side === "t") return [n.cx, n.cy - n.h / 2];
      if (side === "l") return [n.cx - n.w / 2, n.cy];
      return [n.cx + n.w / 2, n.cy];
    };
    spec.edges.forEach((e) => {
      const a = N[e.f], b = N[e.t];
      let pts;
      const bx = b.type === "fork" || b.type === "join" ? (e.tx !== undefined ? 1 + e.tx * LW + LW / 2 : Math.min(Math.max(a.cx, b.cx - b.w / 2 + 10), b.cx + b.w / 2 - 10)) : b.cx;
      const ax = a.type === "fork" || a.type === "join" ? (b.type === "fork" || b.type === "join" ? a.cx : b.cx) : a.cx;
      if (e.loop) {
        // kembali ke atas lewat sisi kanan/kiri
        const side = e.loop === "l" ? -1 : 1;
        const s = port(a, side > 0 ? "r" : "l");
        const t = port(b, side > 0 ? "r" : "l");
        const xo = (e.loopX !== undefined ? 1 + e.loopX * LW : Math.max(s[0], t[0]) * (side > 0 ? 1 : 0) + Math.min(s[0], t[0]) * (side < 0 ? 1 : 0) + side * 26);
        pts = [s, [xo, s[1]], [xo, t[1]], t];
      } else if ((a.type === "decision" || a.type === "merge") && Math.abs(bx - a.cx) > 2 && !e.down) {
        const s = port(a, bx > a.cx ? "r" : "l");
        const ty = b.cy - b.h / 2;
        if (Math.abs(b.cy - a.cy) < 4) pts = [s, port(b, bx > a.cx ? "l" : "r")];
        else pts = [s, [bx, s[1]], [bx, ty]];
      } else {
        const s = [ax, a.cy + a.h / 2];
        const t = [bx, b.cy - b.h / 2];
        if (Math.abs(s[0] - t[0]) < 2) pts = [s, t];
        else if (b.cy - b.h / 2 > s[1] + 6) {
          const my = e.midY !== undefined ? TOP + e.midY * RH : t[1] - 16;
          pts = [s, [s[0], my], [t[0], my], t];
        } else {
          // tujuan bertumpang tindih vertikal dengan asal: garis mendatar pada ketinggian bersama
          const y = Math.min(Math.max(a.cy, b.cy - b.h / 2 + 8), b.cy + b.h / 2 - 8);
          const right = b.cx > a.cx;
          pts = [[a.cx + (right ? a.w / 2 : -a.w / 2), y], [b.cx + (right ? -b.w / 2 : b.w / 2), y]];
        }
      }
      el("polyline", { points: pts.map((p) => p.join(",")).join(" "), fill: "none", stroke: INK, "stroke-width": 1.3, "marker-end": "url(#arrFill)" }, ge);
      if (e.label) {
        const [p0, p1] = pts;
        const horiz = Math.abs(p1[1] - p0[1]) < 2;
        const lx = horiz ? p0[0] + (p1[0] > p0[0] ? 8 : -8) : p0[0] + 6;
        const ly = horiz ? p0[1] - 9 : p0[1] + 12;
        textBlock(ge, lx, ly, [`[${e.label}]`], { size: 11, anchor: horiz && p1[0] < p0[0] ? "end" : "start", fill: "#333" });
      }
    });

    Object.values(N).forEach((n) => {
      if (n.type === "start") el("circle", { cx: n.cx, cy: n.cy, r: 11, fill: INK }, svg);
      else if (n.type === "end") { el("circle", { cx: n.cx, cy: n.cy, r: 13, fill: "#fff", stroke: INK, "stroke-width": 1.6 }, svg); el("circle", { cx: n.cx, cy: n.cy, r: 8, fill: INK }, svg); }
      else if (n.type === "flowEnd") { el("circle", { cx: n.cx, cy: n.cy, r: 13, fill: "#fff", stroke: INK, "stroke-width": 1.6 }, svg); el("path", { d: `M${n.cx - 9},${n.cy - 9} L${n.cx + 9},${n.cy + 9} M${n.cx + 9},${n.cy - 9} L${n.cx - 9},${n.cy + 9}`, stroke: INK, "stroke-width": 1.6 }, svg); }
      else if (n.type === "action") {
        el("rect", { x: n.cx - n.w / 2, y: n.cy - n.h / 2, width: n.w, height: n.h, rx: 12, fill: n.db ? "#f3f7fa" : "#fff", stroke: INK, "stroke-width": 1.4 }, svg);
        textBlock(svg, n.cx, n.cy, n.lines, { size: 12 });
      } else if (n.type === "decision" || n.type === "merge") {
        el("path", { d: `M${n.cx},${n.cy - 15} L${n.cx + 15},${n.cy} L${n.cx},${n.cy + 15} L${n.cx - 15},${n.cy} z`, fill: "#fff", stroke: INK, "stroke-width": 1.4 }, svg);
        if (n.text) { const r = n.textSide === "r"; textBlock(svg, n.cx + (r ? 22 : -22), n.cy - 22, wrap(n.text, 24), { size: 11.5, anchor: r ? "start" : "end", italic: true }); }
      } else if (n.type === "fork" || n.type === "join") {
        el("rect", { x: n.cx - n.w / 2, y: n.cy - 3.5, width: n.w, height: 7, fill: INK }, svg);
      }
    });
    container.append(svg);
    return svg;
  }

  window.UML = { useCase, actorTree, activity };
})();
