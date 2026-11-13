# In-app tutorials

MicroDrop ships plain-language tutorials as single HTML files that open from
**Help ▸ Tutorials** in a `WebViewDialog` (QtWebEngine, with a system-browser
fallback). Each one is written as a slim *source* page, built into a
self-contained page by this folder's scripts, and contributed to the menu by
its own plugin.

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
pixi run python -m examples.tutorials.new_tutorial <plugin_package> <slug> "<Title>" --section <section>
# edit <plugin_package>/resources/<slug>.src.html, then
pixi run python -m examples.tutorials.build_tutorial <plugin_package>/resources/<slug>.src.html
pixi run python -m examples.tutorials.build_tutorial <src> --check   # is the built file current?
```

The scaffolder is idempotent. It:

1. creates `<plugin>/resources/<slug>.src.html` from the template (Overview,
   Quick walkthrough, Toolbar icons, Terms, Caveats, Glossary) unless it exists;
2. builds `<slug>.html` next to it;
3. adds `<SLUG>_TUTORIAL_HTML_PATH` to `<plugin>/consts.py`;
4. makes `<plugin>/plugin.py` contribute the page to the Help menu (see
   below): it adds the `tutorials` trait and `_tutorials_default` the first
   time, and one more `TutorialEntry` for each later tutorial, with the
   `order` of the `--section` you picked (see below).

Run `ruff check --fix` and `ruff format` on the touched `consts.py` and
`plugin.py` before committing; the pre-commit hooks finish import order and
section headers.

## How a tutorial reaches the Help menu

`user_help_plugin` offers the `TUTORIALS` extension point. A plugin
contributes `TutorialEntry` records to it, and Help ▸ Tutorials lists every
contribution in learning order. The menu follows plugins that are loaded or
unloaded while the app runs. `user_help_plugin` never imports the
contributing plugins.

```python
from traits.api import List
from user_help_plugin.consts import TUTORIAL_ORDER_HARDWARE, TUTORIALS, TutorialEntry
from .consts import HEATER_TUTORIAL_HTML_PATH

class HeaterPlugin(Plugin):
    tutorials = List(contributes_to=TUTORIALS)

    def _tutorials_default(self):
        return [
            TutorialEntry(
                title="Heater Tutorial",
                path=HEATER_TUTORIAL_HTML_PATH,
                order=TUTORIAL_ORDER_HARDWARE + 10,
            )
        ]
```

The title is both the menu label (with `...` appended; a `&` shows as
written) and the dialog title.

The `order` places the entry on the learning path. `user_help_plugin.consts`
names one section per hundred, and the menu puts a separator between
sections:

| Section | Constant | Bundled tutorials |
|---|---|---|
| Start here | `TUTORIAL_ORDER_START` (0) | Getting Started with MicroDrop |
| Device | `TUTORIAL_ORDER_DEVICE` (100) | Device Viewer, Camera & Alignment, Zones |
| Protocols | `TUTORIAL_ORDER_PROTOCOLS` (200) | Protocol Tree |
| Hardware | `TUTORIAL_ORDER_HARDWARE` (300) | Dropbot Status & Controls |
| Analysis | `TUTORIAL_ORDER_ANALYSIS` (400) | Image Analysis |
| Managing the app | `TUTORIAL_ORDER_MANAGEMENT` (500) | Plugin Management |
| Reference | `TUTORIAL_ORDER_REFERENCE` (600) | Shortcuts, Gamepad & Touch Assist; Help, Logs & Saved Files |

Add an offset to slot an entry within its section (the Device section uses
+0, +10, +20); entries with the same order are sorted by title. An entry
that sets no `order` gets `TUTORIAL_ORDER_DEFAULT` (1000): a section of its
own after all of these, sorted by title, so older plugins need no change.

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
| `<title>` | page title (an SVG's own `<title>` stays in the SVG) |
| `<nav data-contents>` | sidebar (and narrow-screen dropdown) listing every part's `h2` and its terms' `h3`; parts and terms then need an `id` |
| `<header data-hero>` | `header.hero` |
| `<section data-part>` | `section.part` |
| `<section data-term data-where="…">` | `article.term`; `data-where` becomes the grey note after its `h3` |
| `<div data-what>`, `data-when`, `data-read`, `data-typical` | rows of a `dl.facts`: *What it is*, *When to use it*, *How to read it*, *Typical value*; `data-fact="Label"` for any other row, and a value on the attribute overrides the label |
| `<figure data-demo="name">` | `figure.demo`, started by `Tutorial.demo("name", …)` |
| `<i data-glyph="ICON_X">` or `<i data-glyph="ligature">` | a toolbar button showing that glyph; add `data-on` for the switched-on look, `data-inline` for text size, `data-label="…"` to announce it |
| `<img src="figure.svg">`, `.png` | inlined as a data URI; `data-inline` on an SVG pastes its markup instead, so it can use the theme colours |
| `<style>` / `<script>` | moved after the kit's CSS / JS; a `<style>` with attributes (`media="print"`) keeps its own element. Scripts must be inline: `<script src>` fails the build |
| `<video data-clip poster="…"><source src="<slug>_media/clip.webm"></video>` | a real clip, left as a sidecar file (see *Clips* below); the `poster` is inlined |
| `<img data-media src="<slug>_media/still.webp" alt="…">` | a large still, left as a sidecar file instead of inlined (see *Clips* below) |
| `<a data-media href="<slug>_media/report.html">` | a link to a document shipped as a sidecar file (see *Linked documents* below) |

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

- No network: no `http(s)://` or `//` URL in any `src`, `srcset`, `href`,
  `poster`, `data` or `action` attribute or in a `<style>`'s or `style`
  attribute's CSS `url()`, and no `@import`. The build fails on one. A plain
  link (`<a href="https://â€¦">`) loads nothing and is allowed.
- Under ~300 KB built (the build fails above that). Schematics as inline SVG,
  not screenshots. Clips and `data-media` stills are the exception: sidecar
  files, with their own budget (see *Clips*).
- Light and dark both work through the theme variables; never hard-code a
  text or background colour.
- Respect `prefers-reduced-motion`; the kit stops `.pulse` and smooth scroll.

### Clips

Video is not inlined: it would not fit the page budget (nor would a large
screenshot, see `data-media` below). A clip ships as a sidecar file in a folder named after the page, beside it:
`<slug>.src.html` plays clips from `<slug>_media/`.

```html
<figure class="clip">
<video data-clip muted loop playsinline controls preload="metadata"
       poster="getting_started_media/split.webp" aria-label="…">
<source src="getting_started_media/split.webm" type="video/webm">
</video>
<figcaption><strong>Real example.</strong> What to watch for.</figcaption>
</figure>
```

- A `<video>` or `<source>` `src` must be a relative path inside that folder,
  and the file must exist; anything else, including a network URL, fails the
  build. The `poster` is inlined like an image, so the still shows even when
  only the HTML file is sent.
- Each media file stays under `MEDIA_CLIP_BUDGET_BYTES` (1.2 MB) and the
  whole folder, every file in it counted, under `MEDIA_FOLDER_BUDGET_BYTES`
  (8 MB); the build fails above either, as it does for the page.
- AV1 (or VP9) in WebM with no audio: QtWebEngine builds normally lack H.264,
  so no MP4. The pixi environment's `ffmpeg` has `libaom-av1`; encode with a
  constant quality (`-c:v libaom-av1 -crf 28 -b:v 0`), which keeps UI text
  sharp at a few hundred KB. Crop to the part of the window where the action
  is, at a scale where the text the reader must read is at least about 11 px
  tall, rather than shrinking the whole screen; keep posters small (a third of
  the clip's size is enough), since they are inlined into the page.
- The kit plays a `data-clip` only while it is on screen, never on its own
  under `prefers-reduced-motion`, and when the folder is missing it keeps the
  poster and says where the clip ships.

A large screenshot that would blow the page budget can ship the same way:
mark the `<img>` with `data-media` and point its `src` into the folder.

```html
<img data-media src="getting_started_media/chip.webp" width="960" height="540"
     alt="The chip seated in the DropBot, contact pads facing the pins">
```

- The `src` follows the clip rules above (a relative path inside the folder,
  the file present, within the per-file budget, counted in the folder's) and
  the build leaves the tag as written, `data-media` included. An `<img>`
  without `data-media` is inlined as before.
- Use it only for pictures too big to inline. A clip's poster stays inlined
  so the page still shows something on its own; a `data-media` still does
  not, so give it `alt` text that carries its meaning, and `width` /
  `height` so the page keeps its shape.
- When the folder is missing, the kit replaces the picture with a box of the
  same shape, capped to the column, showing the `alt` text and a note saying
  where the picture ships (`data-missing="…"` overrides the note). In a
  `.still-wrap`, the annotation `<svg>` over the picture is hidden with it.

### Linked documents

A real document the reader should be able to open, such as an example run
report, ships in the same folder and is linked with `data-media`:

```html
<a data-media href="getting_started_media/report.html" target="_blank"
   rel="noopener">Open the example report</a>
```

- The `href` follows the clip rules (a relative path inside the folder, the
  file present, within the per-file budget, counted in the folder's). The
  build checks the file, not what is in it: the linked document's own links
  and network loads are not the page's, so a report that loads a chart library
  from a CDN, or names files on the machine that made it, is allowed. Say so
  beside the link. An `<a>` without `data-media` is a plain link, not checked.
- A link cannot tell by itself whether its file is there. The kit follows the
  page's clips and stills instead: once one of them shows the folder is
  missing, the link into that folder is disabled with a note saying where the
  document ships (`data-missing="…"` overrides it). So link only into a folder
  the page also loads a clip or still from.

Ship the folder with the page: commit it beside the source and the built
page, and keep it in the plugin's package data.

### A single file to share

`--standalone <out>` writes a second copy of the page with every sidecar
file (clips, stills, linked documents) inlined as data URIs, so one HTML file
can be e-mailed:

    pixi run python -m examples.tutorials.build_tutorial <src> --standalone <out>

It builds the regular page as usual and then the copy, which is exempt from
the page budget (expect a few MB). It is a sharing artefact: do not commit
it or register it in a plugin. In the copy, a linked document opens from its
inlined data in a new tab (browsers will not open a `data:` link directly).

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

The heater, magnet and fluorescence plugins live in their own repos, but
their environment always contains MicroDrop, so they can do the same:

1. Write `<package>/resources/<slug>.src.html` in the plugin's repo and build
   it with this repo's script; it needs only `microdrop_style` for the kit:
   `pixi run python -m examples.tutorials.build_tutorial path/to/<slug>.src.html`
   (from MicroDrop's `src`). Commit the source and the built page there, and
   ship the built page as package data.
2. Contribute it from the plugin class exactly as above. The only MicroDrop
   import is `user_help_plugin.consts`, which every plugin's environment has.

`new_tutorial.py --root <their src root> <package> <slug> "<Title>"` does both
steps for a repo laid out like this one.
