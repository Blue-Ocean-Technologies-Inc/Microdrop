# In-app tutorials

MicroDrop ships plain-language tutorials as single HTML files that open from
**Help ▸ Tutorials** in a `WebViewDialog` (QtWebEngine, with a system-browser
fallback). Each one is written as a slim *source* page and built into a
self-contained page by this folder's scripts.

| Piece | Where |
|---|---|
| Shared stylesheet, script | `microdrop_style/tutorial/tutorial.css`, `tutorial.js` |
| Glyph tracer | `microdrop_style/tutorial/glyphs.py` |
| Build | `examples/tutorials/build_tutorial.py` |
| Scaffolder and its template | `examples/tutorials/new_tutorial.py`, `template.src.html` |
| A worked example | `dropbot_status_and_controls/resources/dropbot_status.src.html` |

## Quick start

From `microdrop-py/src` (`QT_QPA_PLATFORM=offscreen` traces glyphs headless):

```bash
pixi run python -m examples.tutorials.new_tutorial <plugin_package> <slug> "<Title>"
# edit <plugin_package>/resources/<slug>.src.html, then
pixi run python -m examples.tutorials.build_tutorial <plugin_package>/resources/<slug>.src.html
pixi run python -m examples.tutorials.build_tutorial <src> --check   # is the built file current?
```

The scaffolder is idempotent. It:

1. creates `<plugin>/resources/<slug>.src.html` from the template (Overview,
   Quick walkthrough, Toolbar icons, Terms, Caveats, Glossary) unless it exists;
2. builds `<slug>.html` next to it;
3. adds `<SLUG>_TUTORIAL_HTML_PATH` to `<plugin>/consts.py`;
4. adds `("<Title>", <SLUG>_TUTORIAL_HTML_PATH)` to `TUTORIALS` in
   `user_help_plugin/menus.py`, importing the constant from the plugin's
   `consts` (the one cross-plugin import `.importlinter` allows), and creates
   the Tutorials submenu if the file has none.

Run ruff on the touched `consts.py` and `menus.py` before committing; the
pre-commit hooks finish import order and section headers.

## Commit both files

Commit the source **and** the built page. The page is what ships (no build
step at install or run time); the source is what you edit. The build is
deterministic, and `examples/tests/test_tutorial_kit.py` fails when a
committed page is stale. The previous build doubles as the glyph cache: each
`<symbol>` keeps the font text it was traced from, so rebuilding needs Qt only
when a new glyph appears (`--retrace` forces a fresh trace).

## Authoring format

A source is an HTML fragment: content only, no `<html>`, `<head>` or kit code.

```html
<!-- copyright comment: copied to the top of the built page -->
<title>Heater Tutorial</title>
<nav data-contents></nav>                       <!-- optional sidebar contents -->
<header data-hero><h1>Heater</h1><p>What it is for.</p></header>
<section data-part id="part-terms"><h2>Settings</h2>
  <section data-term id="setpoint" data-where="Setpoint box">
    <h3>Setpoint</h3><p>One plain sentence.</p>
    <div data-what><p>…</p></div><div data-typical><p>37 °C</p></div>
    <figure data-demo="setpoint"><input type="range" id="sp"><output for="sp"></output></figure>
  </section>
</section>
<script>Tutorial.demo("setpoint", function (figure, T) { /* … */ });</script>
```

What the build rewrites (everything else passes through unchanged; close
these elements explicitly):

| Source | Built |
|---|---|
| `<title>` | page title |
| `<nav data-contents>` | sidebar (and narrow-screen dropdown) listing every part's `h2` and its terms' `h3`; parts and terms then need an `id` |
| `<header data-hero>` | `header.hero` |
| `<section data-part>` | `section.part` |
| `<section data-term data-where="…">` | `article.term`; `data-where` becomes the grey note after its `h3` |
| `<div data-what>`, `data-when`, `data-read`, `data-typical` | rows of a `dl.facts`: *What it is*, *When to use it*, *How to read it*, *Typical value*; `data-fact="Label"` for any other row, and a value on the attribute overrides the label |
| `<figure data-demo="name">` | `figure.demo`, started by `Tutorial.demo("name", …)` |
| `<i data-glyph="ICON_X">` or `<i data-glyph="ligature">` | a toolbar button showing that glyph; add `data-on` for the switched-on look, `data-inline` for text size, `data-label="…"` to announce it |
| `<img src="figure.svg">`, `.png` | inlined as a data URI; `data-inline` on an SVG pastes its markup instead, so it can use the theme colours |
| `<style>` / `<script>` | moved after the kit's CSS / JS |

Raw SVG can reuse a glyph with `<use href="#ic-<id>">`; the build includes
every glyph referenced that way. A glyph id is the `ICON_*` name without the
prefix, lower-cased (`ICON_DROP_EC` → `drop_ec`), or the ligature itself.

Useful classes from the kit: `p.intro`, `.ui` (a control's label),
`.callout` / `.callout.warn`, `ol.steps > li.step` with `figure.step-panel`
and `.step-text` (walkthrough), `table.small`, `table.icons-table` with
`td.icons` / `td.lbl`, `dl.glossary`, `.controls`, `.status` with `.good` /
`.bad`. Theme colours are CSS variables (`--accent`, `--ok`, `--down`,
`--warn`, `--muted`, `--blue`, `--orange`, …) defined for light and dark.

### Demo API (`window.Tutorial`, passed to each demo as `T`)

| Call | Does |
|---|---|
| `T.demo(name, init)` | runs `init(figure, T)` for `<figure data-demo="name">` once the page has loaded; a throwing demo logs to the console and says so in its figure, the rest of the page still works |
| `T.bind(input, fn, fmt)` | calls `fn(value)` on every input/change and writes `fmt(value)` into `<output for="id">` |
| `T.readout(table, rows, opt)` | the Now / Start table; each row `{label, now, start, digits, unit, tolerance, na}`; a rise shows a green ↑, a fall a red ↓, a change to or from n/a a •, each with an aria label |
| `T.plot(svg, {box, x, y, series, title})` | a framed line plot; returns `{sx, sy}` scales for markers |
| `T.el`, `T.text`, `T.clear`, `T.scale`, `T.linePath`, `T.frame` | inline-SVG building blocks |
| `T.random(seed)` | repeatable noise, so a demo looks the same every time |
| `T.reduceMotion` | true when the viewer asked for less motion: do not autoplay |

Scope element lookups to the figure (`figure.querySelector`).

## Offline and size rules

- No network: no `http(s)://` or `//` in any `src`, `href`, CSS `url()`, and
  no `@import`. The build fails on one; external links are out too.
- Under ~300 KB built (the build warns above that). Schematics as inline SVG,
  not screenshots.
- Light and dark both work through the theme variables; never hard-code a
  text or background colour.
- Respect `prefers-reduced-motion`; the kit stops `.pulse` and smooth scroll.

## Checklist for a good tutorial

- [ ] The walkthrough comes first: a few numbered steps from nothing to a result.
- [ ] Every setting and every number the pane shows has a term card, written
      from the real widget labels and tooltips.
- [ ] Each card answers what it is, when to use it, how to read it, and the
      starting value; skip a row rather than pad it.
- [ ] One small interactive where a slider teaches more than a paragraph.
- [ ] The toolbar section shows the real glyphs (`data-glyph`), named by tooltip.
- [ ] A caveats box lists the traps.
- [ ] Schematics, not screenshots: they stay right when the UI is restyled and
      follow the theme.
- [ ] Plain language; short beats complete. A glossary for the jargon.
- [ ] Checked at a dock-sized width (~560 px) and full width, light and dark,
      with an empty console.

## Tutorials for plugins in other repos

The heater, magnet and fluorescence plugins live in their own repos. Their
tutorials can use the same kit and build script (both import only
`microdrop_style`); where their pages are built and how they reach the Help
menu is not settled yet.
