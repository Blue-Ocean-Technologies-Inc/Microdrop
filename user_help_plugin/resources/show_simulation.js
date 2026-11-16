/*
  Tutorial Simulations pane: show one demo figure of a built tutorial page.

  Run by the pane after the page has loaded, so every demo has already
  started on the full page and keeps its measured layout. Defines
  window.microdropShowSim(name), which hides everything but
  <figure data-demo="name"> and the elements leading down to it; calling it
  again switches figures without a reload, so each demo keeps its state.
  Scripts, styles and SVG sprites stay, as figures draw from them.
*/
(function () {
  "use strict";

  if (window.microdropShowSim) { return; }

  var hidden = [];
  var style = document.createElement("style");

  style.textContent = [
    "html.sim-only .layout { display: block; max-width: none; }",
    "html.sim-only main { padding: 8px 10px; }",
    "html.sim-only section.part { padding-top: 0; }",
    "html.sim-only article.term { margin: 0; padding: 0; border: 0; box-shadow: none; background: none; }",
    "html.sim-only figure.demo { margin: 0; }"
  ].join("\n");
  document.head.appendChild(style);

  window.microdropShowSim = function (name) {
    var figure = document.querySelector('figure[data-demo="' + CSS.escape(name) + '"]');

    if (!figure) {
      console.error("Tutorial Simulations: no demo named '" + name + "'");
      return false;
    }

    hidden.forEach(function (node) { node.style.display = ""; });
    hidden = [];
    document.documentElement.classList.add("sim-only");

    for (var node = figure; node !== document.body; node = node.parentElement) {
      Array.prototype.forEach.call(node.parentElement.children, function (sibling) {
        var tag = sibling.tagName.toLowerCase();

        if (sibling === node || tag === "script" || tag === "style" || tag === "svg") { return; }

        if (sibling.style.display === "none") { return; }

        sibling.style.display = "none";
        hidden.push(sibling);
      });
    }

    window.scrollTo(0, 0);

    return true;
  };
})();
