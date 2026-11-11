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
    chip(figure, opt)         animated chip with simulated droplets, played
                              from a declarative list of frames (see below)
    reduceMotion              true when the viewer asked for less motion
  Pages also get: <video data-clip> sidecar clips that play while on screen
  (never with less motion) and fall back to their poster and a note, and
  <img data-media> sidecar stills that fall back to a box with their alt
  text and a note, and <a data-media> links to sidecar documents that are
  disabled with a note when their folder is found missing.
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

  /* ---------------- chip player ----------------
     Draws a device's electrodes with simulated droplets and plays a list of
     frames. The geometry lives once in the page, as a hidden <g id="..."> of
     <polygon data-ch="channel" points="...">, and is cloned into each figure
     so the electrodes can light up per figure.

     opt: { geometry: "chip-90-pin",          id of the electrode <g>
            photo: "chip-90-pin-photo",       optional id of an <img> (inlined
                                              once by the build) drawn under
                                              the electrodes; its data-box
                                              "x y w h" places it in device units
            view: [x, y, w, h],               viewBox, default the whole chip
            numbers: true or [channel, ...],  channel numbers on the electrodes
            numberCorner: true,               put them in the top-left corner,
                                              clear of route lines
            frames: [frame, ...],
            label: "...",                     the figure's accessible name
            draw: function (layer, frame, api)  extra drawing per frame; api
                                              has center(channel) and el()
            onShow: function (index, frame)   called whenever a frame shows }
     frame: { on: [channel, ...],             actuated electrodes
              drops: [{ id, color, at: [part, ...], from: id }],
              routes: [{ through: [channel, ...], selected, area: [channel, ...],
                         tint, upto, color }],
              slug: { at: [channel, ...], color },   dashed outline, as the app
                                              draws the selected route's slug
              click: channel or [channel, ...],
              caption: "...", hold: ms, move: ms }
     part: a channel (liquid over that electrode), { ch, x0, y0, x1, y1 }
           (a fraction 0..1 of the electrode's box), { x, y, w, h } (a box in
           device units) or { x, y, r } (a round bead). Parts of one drop fuse
           into one flat-sided body with rounded corners and a darker rim. A
           new drop with `from` grows out of that drop, so a split reads as
           one body pulling apart.
     color: "green", "blue", "pink" or "yellow" (dye colours) or any CSS colour.
     Routes look like the Device Viewer's: chevrons along the line and a square
     at the start; the selected route is yellow, other paths green and loops
     orange (clockwise on screen) or red (counter-clockwise).
     Returns { show(index), play(), pause(), count }. */
  var DROP_COLORS = {
    green: "var(--drop-green)", blue: "var(--drop-blue)",
    pink: "var(--drop-pink)", yellow: "var(--drop-yellow)"
  };
  var DROP_INSET = 0.35;  /* device units between a drop and its electrode's edge */

  function gooFilter() {
    if (document.getElementById("tut-goo")) { return; }

    /* Blur, then sharpen the alpha: neighbouring boxes fuse into one liquid
       outline with rounded corners, a translucent body and a darker rim. */
    var holder = el("svg", { width: 0, height: 0, style: "position:absolute", "aria-hidden": "true" });
    var filter = el("filter", { id: "tut-goo", x: "-10%", y: "-10%", width: "120%", height: "120%" }, el("defs", {}, holder));

    el("feGaussianBlur", { in: "SourceGraphic", stdDeviation: 1.4, result: "blur" }, filter);
    el("feColorMatrix", { in: "blur", type: "matrix", values: "1 0 0 0 0 0 1 0 0 0 0 0 1 0 0 0 0 0 30 -14", result: "goo" }, filter);
    el("feComponentTransfer", { in: "goo", result: "body" }, filter).appendChild(el("feFuncA", { type: "linear", slope: 0.72 }));
    el("feMorphology", { in: "goo", operator: "erode", radius: 0.5, result: "inner" }, filter);
    el("feComposite", { in: "goo", in2: "inner", operator: "out", result: "edge" }, filter);
    el("feColorMatrix", { in: "edge", type: "matrix", values: "0.45 0 0 0 0 0 0.45 0 0 0 0 0 0.45 0 0 0 0 0 0.9 0", result: "rim" }, filter);

    var merge = el("feMerge", {}, filter);
    el("feMergeNode", { in: "body" }, merge);
    el("feMergeNode", { in: "rim" }, merge);
    document.body.appendChild(holder);
  }

  function chipElectrodes(geometry) {
    var source = document.getElementById(geometry);

    if (!source) { throw new Error("no chip geometry '" + geometry + "' in the page"); }

    var electrodes = {}, x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;

    source.querySelectorAll("[data-ch]").forEach(function (polygon) {
      var xs = [], ys = [];

      polygon.getAttribute("points").trim().split(/\s+/).forEach(function (pair) {
        var xy = pair.split(",");
        xs.push(+xy[0]);
        ys.push(+xy[1]);
      });

      var box = { x0: Math.min.apply(null, xs), y0: Math.min.apply(null, ys), x1: Math.max.apply(null, xs), y1: Math.max.apply(null, ys) };
      box.cx = (box.x0 + box.x1) / 2;
      box.cy = (box.y0 + box.y1) / 2;
      box.w = box.x1 - box.x0;
      box.h = box.y1 - box.y0;
      box.node = polygon;
      electrodes[polygon.getAttribute("data-ch")] = box;

      x0 = Math.min(x0, box.x0); y0 = Math.min(y0, box.y0);
      x1 = Math.max(x1, box.x1); y1 = Math.max(y1, box.y1);
    });

    return { electrodes: electrodes, bounds: [x0, y0, x1 - x0, y1 - y0] };
  }

  /* A part as a box { x, y, w, h, round } centred on (x, y); round 1 is a bead. */
  function partBox(part, electrodes) {
    if (part.r !== undefined) { return { x: part.x, y: part.y, w: 2 * part.r, h: 2 * part.r, round: 1, vol: part.vol }; }

    if (part.w !== undefined) { return { x: part.x + part.w / 2, y: part.y + part.h / 2, w: part.w, h: part.h, round: 0 }; }

    var spec = typeof part === "object" ? part : { ch: part };
    var box = electrodes[spec.ch];

    if (!box) { throw new Error("no electrode with channel " + spec.ch); }

    var fx0 = spec.x0 || 0, fy0 = spec.y0 || 0;
    var fx1 = spec.x1 === undefined ? 1 : spec.x1, fy1 = spec.y1 === undefined ? 1 : spec.y1;
    var left = box.x0 + fx0 * box.w + DROP_INSET, right = box.x0 + fx1 * box.w - DROP_INSET;
    var top = box.y0 + fy0 * box.h + DROP_INSET, bottom = box.y0 + fy1 * box.h - DROP_INSET;

    return { x: (left + right) / 2, y: (top + bottom) / 2, w: right - left, h: bottom - top, round: 0 };
  }

  function nearest(box, boxes) {
    var best = boxes[0], distance = Infinity;

    boxes.forEach(function (other) {
      var d = (other.x - box.x) * (other.x - box.x) + (other.y - box.y) * (other.y - box.y);
      if (d < distance) { distance = d; best = other; }
    });

    return best;
  }

  function seed(box) { return { x: box.x, y: box.y, w: 0, h: 0, round: box.round }; }

  /* Close the gap between boxes of one drop on neighbouring electrodes, so
     the liquid runs flat across them instead of pinching at the gap. */
  function fuse(boxes) {
    function edges(b) { return { l: b.x - b.w / 2, r: b.x + b.w / 2, t: b.y - b.h / 2, b: b.y + b.h / 2 }; }

    function set(box, e) {
      box.x = (e.l + e.r) / 2; box.w = e.r - e.l;
      box.y = (e.t + e.b) / 2; box.h = e.b - e.t;
    }

    function overlap(a0, a1, b0, b1, size) { return Math.min(a1, b1) - Math.max(a0, b0) > size / 2; }

    boxes.forEach(function (a, i) {
      boxes.forEach(function (b, j) {
        if (j <= i || a.round || b.round) { return; }

        var ea = edges(a), eb = edges(b), mid;

        if (overlap(ea.t, ea.b, eb.t, eb.b, Math.min(a.h, b.h))) {
          if (eb.l - ea.r >= 0 && eb.l - ea.r < 1.6) { mid = (eb.l + ea.r) / 2; ea.r = mid; eb.l = mid; }
          if (ea.l - eb.r >= 0 && ea.l - eb.r < 1.6) { mid = (ea.l + eb.r) / 2; ea.l = mid; eb.r = mid; }
        }

        if (overlap(ea.l, ea.r, eb.l, eb.r, Math.min(a.w, b.w))) {
          if (eb.t - ea.b >= 0 && eb.t - ea.b < 1.6) { mid = (eb.t + ea.b) / 2; ea.b = mid; eb.t = mid; }
          if (ea.t - eb.b >= 0 && ea.t - eb.b < 1.6) { mid = (ea.t + eb.b) / 2; ea.t = mid; eb.b = mid; }
        }

        set(a, ea);
        set(b, eb);
      });
    });

    return boxes;
  }

  /* Pair each box of a frame's drop with where it starts moving from. */
  function tweenDrops(before, after) {
    var moves = [];

    after.forEach(function (drop) {
      var old = before.filter(function (d) { return d.id === drop.id; })[0];
      var parent = !old && drop.from ? before.filter(function (d) { return d.id === drop.from; })[0] : null;
      var origin = old || parent;

      drop.boxes.forEach(function (box, k) {
        var start;

        if (old && old.boxes[k]) {
          start = old.boxes[k];
        } else if (origin) {
          var near = nearest(box, origin.boxes);
          start = { x: near.x, y: near.y, w: Math.min(near.w, box.w) * 0.6, h: Math.min(near.h, box.h) * 0.6, round: box.round };
        } else {
          start = seed(box);
        }

        moves.push({ id: drop.id, color: drop.color, from: start, to: box });
      });

      /* Boxes the drop no longer has drain into its nearest remaining one. */
      (old ? old.boxes.slice(drop.boxes.length) : []).forEach(function (box) {
        var near = nearest(box, drop.boxes);
        moves.push({ id: drop.id, color: drop.color, from: box, to: { x: near.x, y: near.y, w: near.w * 0.5, h: near.h * 0.5, round: near.round } });
      });
    });

    before.forEach(function (drop) {
      if (after.some(function (d) { return d.id === drop.id; })) { return; }

      drop.boxes.forEach(function (box) {
        moves.push({ id: drop.id, color: drop.color, from: box, to: seed(box) });
      });
    });

    return moves;
  }

  /* A bead off the plates is a cap, not a film: it may carry its own `vol`. */
  function boxArea(box) {
    if (box.vol !== undefined) { return box.vol; }

    return box.round ? Math.PI * box.w * box.h / 4 : box.w * box.h;
  }

  function sum(boxes) { return boxes.reduce(function (total, box) { return total + boxArea(box); }, 0); }

  /* Boxes that touch (side by side, as fuse() joins them) form one body. */
  function bodies(boxes) {
    var owner = boxes.map(function (box, k) { return k; });

    function find(k) { return owner[k] === k ? k : (owner[k] = find(owner[k])); }

    function near(a0, a1, b0, b1) { return Math.max(a0, b0) - Math.min(a1, b1) < 1.6; }

    boxes.forEach(function (a, i) {
      boxes.forEach(function (b, j) {
        if (j > i && near(a.x - a.w / 2, a.x + a.w / 2, b.x - b.w / 2, b.x + b.w / 2) &&
            near(a.y - a.h / 2, a.y + a.h / 2, b.y - b.h / 2, b.y + b.h / 2)) {
          owner[find(j)] = find(i);
        }
      });
    });

    var groups = {};

    boxes.forEach(function (box, k) { (groups[find(k)] = groups[find(k)] || []).push(box); });

    return Object.keys(groups).map(function (key) { return groups[key]; });
  }

  /* Scale boxes by k, each body about its own centre, so a stretched or
     overhanging drop stays one body and separate parts stay in place. */
  function scaled(boxes, k) {
    var out = [];

    bodies(boxes).forEach(function (body) {
      var total = sum(body), cx = 0, cy = 0;

      body.forEach(function (box) { cx += box.x * boxArea(box) / total; cy += box.y * boxArea(box) / total; });
      body.forEach(function (box) {
        out.push({ x: cx + (box.x - cx) * k, y: cy + (box.y - cy) * k, w: box.w * k, h: box.h * k, round: box.round });
      });
    });

    return out;
  }

  /* Liquid between two plates keeps its volume, and with the gap fixed its
     area: a drop has one area for its whole life. Parts given as boxes or
     beads are drawn as given; electrode parts are scaled so the drop keeps
     its area — stretched thinner over more electrodes than it fills,
     overhanging fewer. The area is the drop's `vol`, else what it had in
     the frame before, else what its electrodes hold when it first appears.
     A change of a drop's area, or of all the liquid on the chip, is only
     allowed where the frame says why: a new drop split `from` another, a
     drop that `merge`s others, `exchange: [ids]` trading liquid, or
     `adds: true` (pipetting); anything else is logged as a warning. */
  function droppedFrames(source, electrodes, name) {
    var volumes = {}, previousTotal = null, warnings = 0;

    function warn(index, message) {
      warnings += 1;

      if (window.console) { console.warn("Tutorial.chip volume check, " + name + ", step " + (index + 1) + ": " + message); }
    }

    var frames = source.map(function (frame, index) {
      var seen = {}, total = 0, exchange = {};

      (frame.exchange || []).forEach(function (id) { exchange[id] = true; });

      (frame.drops || []).forEach(function (drop) {
        if (drop.from) { exchange[drop.id] = exchange[drop.from] = true; }

        (drop.merge || []).forEach(function (id) { exchange[id] = exchange[drop.id] = true; });
      });

      var drops = (frame.drops || []).map(function (drop) {
        var targets = [], explicit = [];

        drop.at.forEach(function (part) {
          (typeof part === "object" ? explicit : targets).push(partBox(part, electrodes));
        });

        var natural = sum(targets) + sum(explicit), known = volumes[drop.id];
        var volume = drop.vol !== undefined ? drop.vol : (targets.length && known !== undefined && !exchange[drop.id] && !frame.adds ? known : natural);
        var boxes = explicit;

        if (targets.length) {
          var room = Math.max(volume - sum(explicit), 0.01);

          boxes = explicit.concat(scaled(targets, Math.sqrt(room / sum(targets))));
        } else if (Math.abs(natural - volume) > 0.03 * volume) {
          warn(index, "drop '" + drop.id + "' is drawn with area " + natural.toFixed(1) + " but holds " + volume.toFixed(1));
        }

        if (index && volumes[drop.id] !== undefined && Math.abs(volumes[drop.id] - volume) > 0.03 * volume && !exchange[drop.id] && !frame.adds) {
          warn(index, "drop '" + drop.id + "' changes from " + volumes[drop.id].toFixed(1) + " to " + volume.toFixed(1) + " with no split, merge or exchange");
        }

        seen[drop.id] = volume;
        total += volume;

        return {
          id: drop.id, from: drop.from, volume: volume,
          color: DROP_COLORS[drop.color] || drop.color || DROP_COLORS.green,
          boxes: fuse(boxes)
        };
      });

      if (previousTotal !== null && Math.abs(total - previousTotal) > 0.03 * Math.max(total, previousTotal) && !frame.adds) {
        warn(index, "the liquid on the chip goes from " + previousTotal.toFixed(1) + " to " + total.toFixed(1) + " without `adds`");
      }

      volumes = seen;
      previousTotal = total;

      return { source: frame, drops: drops };
    });

    frames.warnings = warnings;

    return frames;
  }

  function chip(figure, opt) {
    gooFilter();

    var device = chipElectrodes(opt.geometry), electrodes = device.electrodes;
    var view = opt.view || device.bounds, pad = 1.5;
    var svg = figure.querySelector("svg.chip") || el("svg", { class: "chip" }, figure);

    svg.setAttribute("viewBox", [view[0] - pad, view[1] - pad, view[2] + 2 * pad, view[3] + 2 * pad].join(" "));
    svg.setAttribute("role", "img");
    svg.setAttribute("aria-label", opt.label || "Chip diagram");

    var b = device.bounds, photo = opt.photo ? document.getElementById(opt.photo) : null;
    el("rect", { x: b[0] - 3, y: b[1] - 3, width: b[2] + 6, height: b[3] + 6, class: "chip-plate" }, svg);

    /* The photo's bytes stay in its one <img>; each figure only points at them. */
    if (photo) {
      var box = (photo.getAttribute("data-box") || b.join(" ")).split(/\s+/);
      el("image", { href: photo.getAttribute("src"), x: box[0], y: box[1], width: box[2], height: box[3], preserveAspectRatio: "none" }, svg);
      svg.classList.add("on-photo");
    }

    var layers = {};

    ["areas", "electrodes", "numbers", "drops", "slug", "routes", "extra"].forEach(function (name) {
      layers[name] = el("g", { class: "chip-" + name }, svg);
    });

    Object.keys(electrodes).forEach(function (ch) {
      var copy = electrodes[ch].node.cloneNode(false);
      copy.setAttribute("class", "electrode");
      layers.electrodes.appendChild(copy);
      electrodes[ch].copy = copy;
    });

    if (opt.numbers) {
      (opt.numbers === true ? Object.keys(electrodes) : opt.numbers).forEach(function (ch) {
        var e = electrodes[ch], size = Math.min(Math.min(e.w, e.h) * 0.5, 9);

        if (opt.numberCorner) {
          size = Math.min(Math.min(e.w, e.h) * 0.3, 5);
          text(layers.numbers, e.x0 + 0.7, e.y0 + 0.4 + size * 0.8, String(ch), { style: "font-size:" + size.toFixed(1) + "px" });
        } else {
          text(layers.numbers, e.cx, e.cy + size * 0.36, String(ch), { style: "font-size:" + size.toFixed(1) + "px", "text-anchor": "middle" });
        }
      });
    }

    var bar = document.createElement("div");
    bar.className = "controls chip-controls";
    bar.innerHTML = '<button type="button" data-act="play"></button><button type="button" data-act="step">Step ▸</button>' +
      '<button type="button" data-act="restart">↺ Restart</button><span class="chip-count"></span>';

    var caption = document.createElement("p");
    caption.className = "chip-caption";
    caption.setAttribute("aria-live", "polite");
    svg.parentNode.insertBefore(bar, svg.nextSibling);
    bar.parentNode.insertBefore(caption, bar.nextSibling);

    var frames = droppedFrames(opt.frames, electrodes, opt.label || "chip figure");
    figure.setAttribute("data-volume-warnings", String(frames.warnings));
    var index = 0, shown = [], playing = false, timer = null, raf = null, wantsPlay = !reduceMotion;

    function center(ch) {
      if (!electrodes[ch]) { throw new Error("no electrode with channel " + ch); }

      return electrodes[ch];
    }

    /* Signed area of a closed route: positive turns clockwise on screen (y down). */
    function turning(through) {
      var sum = 0;

      for (var k = 1; k < through.length; k++) {
        var a = center(through[k - 1]), z = center(through[k]);
        sum += a.cx * z.cy - z.cx * a.cy;
      }

      return sum;
    }

    function outline(chs, attrs, parent) {
      chs.forEach(function (ch) {
        var copy = center(ch).node.cloneNode(false);

        for (var key in attrs) { copy.setAttribute(key, attrs[key]); }

        parent.appendChild(copy);
      });
    }

    function drawRoutes(frame) {
      clear(layers.routes);
      clear(layers.areas);

      (frame.routes || []).forEach(function (route) {
        var through = route.through, last = through.length - 1;
        var points = through.slice(0, route.upto === undefined ? through.length : route.upto + 1).map(center);
        var loop = through.length > 2 && through[0] === through[last];
        var color = route.color || (route.selected ? "var(--route-selected)" : loop ? (turning(through) > 0 ? "var(--route-cw)" : "var(--route-ccw)") : "var(--route)");

        if (route.area) {
          outline(route.area, { class: "chip-area", style: "fill:" + (route.tint || "var(--slug-1)") }, layers.areas);
        }

        var g = el("g", { class: "chip-route", style: "stroke:" + color + ";fill:" + color }, layers.routes);
        el("path", { d: points.map(function (p, k) { return (k ? "L" : "M") + p.cx.toFixed(2) + "," + p.cy.toFixed(2); }).join(""), fill: "none" }, g);

        /* A chevron halfway along each step, pointing the way the drop moves. */
        for (var k = 1; k < points.length; k++) {
          var a = points[k - 1], z = points[k], angle = Math.atan2(z.cy - a.cy, z.cx - a.cx) * 180 / Math.PI;
          var ax = (a.cx + z.cx) / 2, ay = (a.cy + z.cy) / 2;
          el("path", { d: "M-1,-1.5L0.6,0L-1,1.5", class: "chip-route-arrow", transform: "translate(" + ax.toFixed(2) + "," + ay.toFixed(2) + ") rotate(" + angle.toFixed(1) + ")" }, g);
        }

        el("rect", { x: points[0].cx - 1.3, y: points[0].cy - 1.3, width: 2.6, height: 2.6, rx: 0.4, class: "chip-route-end" }, g);
      });
    }

    function drawSlug(frame) {
      clear(layers.slug);

      if (frame.slug) {
        outline(frame.slug.at, { class: "chip-slug", style: "stroke:" + (frame.slug.color || "var(--slug-1)") }, layers.slug);
      }
    }

    function drawClicks(frame) {
      var clicks = frame.click === undefined ? [] : [].concat(frame.click);

      clicks.forEach(function (ch) {
        var p = center(ch), r = Math.min(Math.min(p.w, p.h) * 0.45, 5);
        el("circle", { cx: p.cx, cy: p.cy, r: r, class: "chip-click" + (reduceMotion ? "" : " pulse") }, layers.extra);
        el("path", { d: "M" + (p.cx + 0.8) + "," + (p.cy + 0.8) + "l0,7l1.9,-1.9l1.5,3.2l1.3,-.6l-1.5,-3.1l2.7,0z", class: "chip-pointer" }, layers.extra);
      });
    }

    function lerp(a, z, t) { return a + (z - a) * t; }

    function drawDrops(moves, t) {
      clear(layers.drops);

      var groups = {};

      moves.forEach(function (move) {
        var w = lerp(move.from.w, move.to.w, t), h = lerp(move.from.h, move.to.h, t);

        if (w <= 0.05 || h <= 0.05) { return; }

        var x = lerp(move.from.x, move.to.x, t), y = lerp(move.from.y, move.to.y, t);
        var round = lerp(move.from.round, move.to.round, t), radius = round * Math.min(w, h) / 2;

        if (!groups[move.id]) {
          groups[move.id] = el("g", { style: "fill:" + move.color, filter: "url(#tut-goo)" }, layers.drops);
        }

        el("rect", { x: (x - w / 2).toFixed(2), y: (y - h / 2).toFixed(2), width: w.toFixed(2), height: h.toFixed(2), rx: radius.toFixed(2) }, groups[move.id]);

        /* A bead sitting proud of the plate catches the light. */
        if (round > 0.5 && w > 2) {
          el("ellipse", { cx: (x - w * 0.18).toFixed(2), cy: (y - h * 0.2).toFixed(2), rx: (w * 0.16).toFixed(2), ry: (h * 0.1).toFixed(2), class: "chip-shine" }, layers.drops);
        }
      });
    }

    function ease(t) { return t < 0.5 ? 2 * t * t : 1 - Math.pow(-2 * t + 2, 2) / 2; }

    function show(next, animate) {
      var frame = frames[next], source = frame.source;
      var moves = tweenDrops(shown, frame.drops);

      index = next;
      shown = frame.drops;

      var on = {};

      (source.on || []).forEach(function (ch) { on[ch] = true; });
      Object.keys(electrodes).forEach(function (ch) { electrodes[ch].copy.classList.toggle("on", !!on[ch]); });

      drawRoutes(source);
      drawSlug(source);
      clear(layers.extra);

      if (opt.draw) { opt.draw(layers.extra, source, { center: center, el: el, text: text }); }

      drawClicks(source);

      caption.textContent = source.caption || "";
      bar.querySelector(".chip-count").textContent = "Step " + (next + 1) + " of " + frames.length;

      if (opt.onShow) { opt.onShow(next, source); }

      if (raf) { cancelAnimationFrame(raf); raf = null; }

      var duration = animate && !reduceMotion ? (source.move || 700) : 0;

      if (!duration) { drawDrops(moves, 1); return; }

      var started = null;

      function tick(now) {
        if (started === null) { started = now; }

        var t = Math.min(1, (now - started) / duration);
        drawDrops(moves, ease(t));
        raf = t < 1 ? requestAnimationFrame(tick) : null;
      }

      raf = requestAnimationFrame(tick);
    }

    function schedule() {
      clearTimeout(timer);

      if (!playing) { return; }

      var last = index === frames.length - 1;

      timer = setTimeout(function () {
        show(last ? 0 : index + 1, !last);
        schedule();
      }, (frames[index].source.hold || 1800) + (last ? 1500 : 0));
    }

    function setPlaying(value) {
      var button = bar.querySelector('[data-act="play"]');

      playing = value;
      button.textContent = playing ? "❚❚ Pause" : "▶ Play";
      button.setAttribute("aria-pressed", playing ? "true" : "false");
      schedule();
    }

    bar.addEventListener("click", function (event) {
      var act = event.target.getAttribute && event.target.getAttribute("data-act");

      if (act === "play") { wantsPlay = !playing; setPlaying(wantsPlay); }

      if (act === "step") { wantsPlay = false; setPlaying(false); show((index + 1) % frames.length, index + 1 < frames.length); }

      if (act === "restart") { show(0, false); schedule(); }
    });

    show(0, false);
    setPlaying(false);

    /* Autoplay only while on screen, and never when less motion is asked for. */
    if ("IntersectionObserver" in window) {
      new IntersectionObserver(function (entries) {
        var visible = entries[0].isIntersecting;

        if (visible !== playing && (wantsPlay || !visible)) { setPlaying(visible && wantsPlay); }
      }, { threshold: 0.4 }).observe(svg);
    } else if (wantsPlay) {
      setPlaying(true);
    }

    return {
      count: frames.length,
      show: function (k) { show(k, false); },
      play: function () { wantsPlay = true; setPlaying(true); },
      pause: function () { wantsPlay = false; setPlaying(false); }
    };
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

  /* ---------------- real clips ----------------
     <video data-clip> plays a sidecar clip from the page's <slug>_media
     folder (see examples/tutorials/README.md). It plays only while on
     screen and never by itself when less motion is asked for; when the
     folder did not travel with the page, the poster stays and a note says
     where the clip lives. */
  /* Media folders found missing, and what to tell when one is. */
  var missingFolders = {}, folderWatchers = [];

  function folderMissing(folder) {
    if (missingFolders[folder]) { return; }

    missingFolders[folder] = true;
    folderWatchers.forEach(function (watch) { watch(folder); });
  }

  function clips() {
    document.querySelectorAll("video[data-clip]").forEach(function (video) {
      var noted = false;

      function missing() {
        if (noted) { return; }

        noted = true;

        var note = document.createElement("p"), source = video.querySelector("source") || video;
        var folder = (source.getAttribute("src") || "").split("/")[0];

        note.className = "clip-note";
        note.textContent = video.getAttribute("data-missing") ||
          "The clip is not available: it ships in the " + folder + " folder next to this page.";
        video.removeAttribute("controls");
        video.parentNode.insertBefore(note, video.nextSibling);
        folderMissing(folder);
      }

      video.addEventListener("error", missing);
      video.querySelectorAll("source").forEach(function (source) { source.addEventListener("error", missing); });

      /* A missing file may have failed before these listeners existed. */
      setTimeout(function () { if (video.networkState === 3 && video.readyState === 0) { missing(); } }, 1500);

      if (reduceMotion || !("IntersectionObserver" in window)) { return; }

      new IntersectionObserver(function (entries) {
        if (noted) { return; }

        if (entries[0].isIntersecting) {
          var playing = video.play();

          if (playing && playing.catch) { playing.catch(function () {}); }
        } else {
          video.pause();
        }
      }, { threshold: 0.5 }).observe(video);
    });
  }

  /* ---------------- sidecar stills ----------------
     <img data-media> shows a still from the page's <slug>_media folder.
     When the folder did not travel with the page, a box of the picture's
     shape (its width / height attributes, capped to the column) shows the
     alt text and says where the picture lives; an annotation <svg> beside
     it in a .still-wrap is hidden with it. */
  function stills() {
    document.querySelectorAll("img[data-media]").forEach(function (img) {
      var source = img.getAttribute("src") || "", replaced = false;

      if (!source) { return; }

      function missing() {
        if (replaced) { return; }

        replaced = true;

        var box = document.createElement("div"), alt = document.createElement("span"), note = document.createElement("p");
        var width = parseFloat(img.getAttribute("width")), height = parseFloat(img.getAttribute("height"));
        var wrap = img.parentNode;

        box.className = "still-missing";
        box.setAttribute("role", "img");
        box.setAttribute("aria-label", img.getAttribute("alt") || "Picture not available");

        if (width > 0) { box.style.width = width + "px"; }

        if (width > 0 && height > 0) { box.style.aspectRatio = width + " / " + height; }

        alt.className = "still-alt";
        alt.textContent = img.getAttribute("alt") || "";
        note.className = "clip-note";
        note.textContent = img.getAttribute("data-missing") ||
          "The picture is not available: it ships in the " + source.split("/")[0] + " folder next to this page.";
        box.appendChild(alt);
        box.appendChild(note);

        img.style.display = "none";
        wrap.insertBefore(box, img.nextSibling);

        if (wrap.classList && wrap.classList.contains("still-wrap")) {
          Array.prototype.forEach.call(wrap.children, function (child) {
            if (child.namespaceURI === SVGNS) { child.style.display = "none"; }
          });
        }

        folderMissing(source.split("/")[0]);
      }

      img.addEventListener("error", missing);

      /* A missing file may have failed before this listener existed. */
      if (img.complete && img.naturalWidth === 0) { missing(); }
    });
  }

  /* ---------------- linked documents ----------------
     <a data-media href> opens a document from the page's <slug>_media
     folder. A link cannot tell by itself whether its file is there, so it
     follows the page's clips and stills: once one of them shows its folder
     is missing, the link in that folder is disabled with the same note. In
     the single-file copy the href is a data: URI, which browsers will not
     open from a link, so a click opens it as a blob instead. */
  function links() {
    var anchors = Array.prototype.slice.call(document.querySelectorAll("a[data-media]"));

    function disable(folder) {
      anchors.forEach(function (a) {
        var href = a.getAttribute("href") || "";

        if (href.split("/")[0] !== folder || a.classList.contains("link-missing")) { return; }

        var note = document.createElement("span");

        note.className = "link-note";
        note.textContent = " " + (a.getAttribute("data-missing") ||
          "(not available: it ships in the " + folder + " folder next to this page)");
        a.classList.add("link-missing");
        a.removeAttribute("href");
        a.parentNode.insertBefore(note, a.nextSibling);
      });
    }

    anchors.forEach(function (a) {
      var href = a.getAttribute("href") || "";

      /* The in-app Help viewer opens followed links in the system browser,
         but opens no new windows: there a target would swallow the click. */
      if (/QtWebEngine/.test(navigator.userAgent)) { a.removeAttribute("target"); }

      if (href.indexOf("data:") !== 0) { return; }

      a.addEventListener("click", function (event) {
        event.preventDefault();
        fetch(href).then(function (response) { return response.blob(); }).then(function (blob) {
          window.open(URL.createObjectURL(blob), "_blank", "noopener");
        });
      });
    });

    folderWatchers.push(disable);
    Object.keys(missingFolders).forEach(disable);
  }

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
    random: random, chip: chip, reduceMotion: reduceMotion
  };

  /* Page scripts follow this one, so demos start once they have registered. */
  document.addEventListener("DOMContentLoaded", function () {
    contents();
    links();
    clips();
    stills();
    startDemos();
  });
})();
