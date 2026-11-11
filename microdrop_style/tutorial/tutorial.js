/*
  MicroDrop tutorial kit: shared script for the in-app HTML tutorials.
  Inlined into every built tutorial by examples/tutorials/build_tutorial.py.

  window.Tutorial
    demo(name, init)          run init(figure, Tutorial) for <figure data-demo="name">
    bind(input, fn, fmt)      call fn on every input event; mirror the value
                              into <output for="id"> (formatted by fmt)
    readout(table, rows, opt) Now / Start table with green up / red down markers
    plot(svg, opt)            framed line plot; returns its { sx, sy } scales
    el, text, clear, scale, linePath, frame   inline-SVG building blocks
    random(seed)              deterministic noise source for repeatable demos
    reduceMotion              true when the viewer asked for less motion
*/
(function () {
  "use strict";
  var SVGNS = "http://www.w3.org/2000/svg";
  var reduceMotion = !!(window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches);
  var demos = {};

  /* ---------------- inline SVG ---------------- */
  function el(tag, attrs, parent) {
    var node = document.createElementNS(SVGNS, tag);
    for (var key in attrs) { node.setAttribute(key, attrs[key]); }
    if (parent) { parent.appendChild(node); }
    return node;
  }

  function text(parent, x, y, content, attrs) {
    var node = el("text", Object.assign({ x: x, y: y }, attrs || {}), parent);
    node.textContent = content;
    return node;
  }

  function clear(node) { while (node.firstChild) { node.removeChild(node.firstChild); } }

  function scale(d0, d1, r0, r1) {
    return function (v) { return r0 + (v - d0) / (d1 - d0) * (r1 - r0); };
  }

  /* Path through (x, y) pairs, broken wherever y is NaN. */
  function linePath(xs, ys, sx, sy) {
    var d = "", pen = false;
    for (var i = 0; i < xs.length; i++) {
      if (ys[i] !== ys[i]) { pen = false; continue; }
      d += (pen ? "L" : "M") + sx(xs[i]).toFixed(1) + "," + sy(ys[i]).toFixed(1);
      pen = true;
    }
    return d;
  }

  function frame(svg, x0, y0, x1, y1) {
    el("rect", { x: x0, y: y0, width: x1 - x0, height: y1 - y0, class: "plotbg" }, svg);
    for (var k = 1; k < 4; k++) {
      var gy = y0 + (y1 - y0) * k / 4;
      el("line", { x1: x0, x2: x1, y1: gy, y2: gy, class: "gridline" }, svg);
    }
    el("line", { x1: x0, x2: x0, y1: y0, y2: y1, class: "axis" }, svg);
    el("line", { x1: x0, x2: x1, y1: y1, y2: y1, class: "axis" }, svg);
  }

  /* opt: { box: [x0, y0, x1, y1], x: [min, max], y: [min, max], title,
            series: [{ xs, ys, stroke, width, dash }] } */
  function plot(svg, opt) {
    var box = opt.box;
    var sx = scale(opt.x[0], opt.x[1], box[0], box[2]);
    var sy = scale(opt.y[0], opt.y[1], box[3], box[1]);
    frame(svg, box[0], box[1], box[2], box[3]);
    if (opt.title) { text(svg, box[0] + 6, box[1] + 14, opt.title); }
    (opt.series || []).forEach(function (s) {
      var attrs = { d: linePath(s.xs, s.ys, sx, sy), fill: "none", stroke: s.stroke || "var(--blue)", "stroke-width": s.width || 2 };
      if (s.dash) { attrs["stroke-dasharray"] = s.dash; }
      el("path", attrs, svg);
    });
    return { sx: sx, sy: sy };
  }

  /* ---------------- controls ---------------- */
  function bind(input, fn, fmt) {
    var node = typeof input === "string" ? document.getElementById(input) : input;
    var out = node.id ? document.querySelector('output[for="' + node.id + '"]') || document.getElementById(node.id + "-o") : null;
    function update() {
      if (out) { out.textContent = fmt ? fmt(node.value) : node.value; }
      fn(node.value);
    }
    node.addEventListener("input", update);
    node.addEventListener("change", update);
    if (out) { out.textContent = fmt ? fmt(node.value) : node.value; }
    return { input: node, refresh: update };
  }

  /* ---------------- Now / Start readout ---------------- */
  var MARKS = { up: ["↑", "increased"], down: ["↓", "decreased"], changed: ["•", "changed"] };

  function shown(value, row) {
    if (value === null || value === undefined || value !== value) { return null; }
    if (typeof value === "string") { return value; }
    return value.toFixed(row.digits || 0) + (row.unit ? " " + row.unit : "");
  }

  /* "up", "down", "changed" (to or from n/a) or "": a change must show at the
     displayed precision and clear the row's tolerance. */
  function moved(row) {
    var now = shown(row.now, row), start = shown(row.start, row);
    if (now === start) { return ""; }
    if (now === null || start === null || typeof row.now === "string") { return "changed"; }
    var delta = row.now - row.start;
    return Math.abs(delta) > (row.tolerance || 0) ? (delta > 0 ? "up" : "down") : "";
  }

  /* rows: [{ label, now, start, digits, unit, tolerance }]; null / NaN shows
     as "n/a" (or row.na). opt.headers overrides ["Quantity", "Now", "Start"]. */
  function readout(table, rows, opt) {
    var heads = (opt && opt.headers) || ["Quantity", "Now", "Start"];
    table.classList.add("small", "readout");
    var html = "<thead><tr><th>" + heads[0] + '</th><th class="num">' + heads[1] + '</th><th class="num">' + heads[2] +
      '</th><th></th></tr></thead><tbody>';
    rows.forEach(function (row) {
      var change = moved(row), mark = MARKS[change];
      var na = '<span class="na">' + (row.na || "n/a") + "</span>";
      var now = shown(row.now, row), start = shown(row.start, row);
      var sign = mark ? '<span role="img" aria-label="' + mark[1] + '" title="' + mark[1] + '">' + mark[0] + "</span>" : "–";
      html += "<tr" + (mark ? ' class="' + change + '"' : "") + "><td>" + row.label + '</td><td class="num now">' +
        (now === null ? na : now) + '</td><td class="num">' + (start === null ? na : start) + '</td><td class="mark">' + sign + "</td></tr>";
    });
    table.innerHTML = html + "</tbody>";
  }

  /* ---------------- deterministic noise ---------------- */
  function random(seed) {
    var state = seed || 7;
    return function () { state = (state * 16807) % 2147483647; return state / 2147483647; };
  }

  /* ---------------- contents ---------------- */
  function contents() {
    var list = document.getElementById("toc");
    var holder = document.querySelector("[data-toc-clone]");
    if (!list || !holder) { return; }
    holder.appendChild(list.cloneNode(true)).removeAttribute("id");
    var mobile = document.getElementById("toc-mobile");
    holder.addEventListener("click", function (event) {
      if (event.target.tagName === "A") { mobile.open = false; }
    });
    if (!("IntersectionObserver" in window)) { return; }
    var links = {};
    list.querySelectorAll("a").forEach(function (a) { links[a.getAttribute("href").slice(1)] = a; });
    var observer = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        if (!entry.isIntersecting) { return; }
        list.querySelectorAll("a.active").forEach(function (a) { a.classList.remove("active"); });
        var link = links[entry.target.id];
        if (link) { link.classList.add("active"); }
      });
    }, { rootMargin: "0px 0px -70% 0px" });
    Object.keys(links).forEach(function (id) {
      var target = document.getElementById(id);
      if (target) { observer.observe(target); }
    });
  }

  /* ---------------- demo mounts ---------------- */
  function demo(name, init) { demos[name] = init; }

  function startDemos() {
    document.querySelectorAll("figure[data-demo]").forEach(function (figure) {
      var name = figure.getAttribute("data-demo"), init = demos[name];
      if (!init) {
        console.error("Tutorial: no script registered for demo '" + name + "'");
        return;
      }
      try {
        init(figure, window.Tutorial);
      } catch (error) {
        console.error("Tutorial: demo '" + name + "' failed", error);
        var note = document.createElement("p");
        note.className = "demo-error";
        note.textContent = "This demo could not start.";
        figure.appendChild(note);
      }
    });
  }

  window.Tutorial = {
    demo: demo, bind: bind, readout: readout, plot: plot,
    el: el, text: text, clear: clear, scale: scale, linePath: linePath, frame: frame,
    random: random, reduceMotion: reduceMotion
  };

  /* Page scripts follow this one, so demos start once they have registered. */
  document.addEventListener("DOMContentLoaded", function () {
    contents();
    startDemos();
  });
})();
