# MicroDrop Architecture Presentation — Developer Guide

This document provides full context for continuing work on `microdrop-architecture.html`, a self-contained HTML presentation about the MicroDrop software architecture and DropBot hardware communication.

## File Location

```
Microdrop-Next-Gen/microdrop-architecture.html
```

## What is MicroDrop?

**MicroDrop** is an open-source digital microfluidics (DMF) control system built by [Sci-Bots](https://sci-bots.com/). DMF uses electric fields to manipulate tiny droplets on a chip — think lab-on-a-chip for biology, chemistry, and diagnostics.

The software controls hardware platforms (currently **DropBot** and **OpenDrop**) that apply high voltage to electrode arrays on a chip, moving droplets by electrowetting.

### Supported Hardware

- **[DropBot](https://sci-bots.com/products/dropbot)** — Sci-Bots' own DMF platform. Teensy 3.x-based, communicates via USB serial RPC. Full capacitance sensing, short detection, and multi-channel actuation.
- **[OpenDrop](https://www.gaudi.ch/OpenDrop/)** — Open-source DMF platform by GaudiLabs. Simpler hardware, community-driven.

### Software Architecture (what the slides explain)

MicroDrop Next-Gen is a **three-layer, message-driven system**:

1. **Frontend** (PySide6/Qt6 GUI) — Interactive SVG device viewer where users click electrodes, plus a protocol grid for automated sequences. Built on the [Envisage](https://docs.enthought.com/envisage/) plugin framework.

2. **Message Server** (Redis + Dramatiq) — A pub/sub message router using MQTT-style topic matching. All communication between frontend and backend flows through here. The server can run on localhost, LAN, or cloud — enabling remote hardware control.

3. **Backend** (DropBot Controller) — Receives messages via Dramatiq workers, translates them into hardware commands via `SerialProxy` (auto-generated Python RPC client from C++ firmware via `arduino-rpc` + protobuf), and sends them over USB serial to the DropBot.

**Data flow**: User clicks electrode → frontend publishes `electrodes_state_change` (toggles on/off state, does NOT apply voltage) → Redis routes to backend worker → backend calls `proxy.state_of_channels = [...]` → SerialProxy sends RPC over USB → firmware applies high voltage → capacitance feedback flows back through the same pipeline → GUI updates.

### DropBot Python API

The DropBot can be controlled directly from Python:

```python
import dropbot as db
proxy = db.SerialProxy()  # auto-detects connected DropBot

# Read state
proxy.voltage              # current output voltage
proxy.frequency            # current output frequency
proxy.state_of_channels    # numpy array of on/off states
proxy.number_of_channels   # channel count

# Set state
proxy.voltage = 100
proxy.frequency = 1e4
proxy.hv_output_enabled = True
proxy.state_of_channels = channel_array  # 1D numpy array, 0/1

# Convenience method
proxy.update_state(hv_output_enabled=True, hv_output_selected=True,
                   voltage=100, frequency=10e3)

# Measurements
proxy.measure_voltage()
proxy.measure_capacitance()
proxy.measure_temperature()
proxy.detect_shorts()

# Signals (event-driven)
proxy.signals.signal('capacitance-updated').connect(callback_fn)
# Available: connected, disconnected, no-power, halted, shorts-detected,
#   capacitance-updated, capacitance-exceeded, channels-updated,
#   drops-detected, output_enabled, output_disabled

# Thread safety
with proxy.transaction_lock:
    # safe concurrent operations
    pass
```

### Key Repos

- **MicroDrop**: https://github.com/Blue-Ocean-Technologies-Inc/Microdrop
- **dropbot.py**: https://github.com/Blue-Ocean-Technologies-Inc/dropbot.py
- **Sci-Bots website**: https://sci-bots.com/
- **DropBot product page**: https://sci-bots.com/products/dropbot

Single self-contained HTML file — all CSS, JS, and SVG logos are inline. No external dependencies except Google Fonts (Orbitron, Lato, JetBrains Mono, Varela Round).

## Slide Overview (10 slides)

| # | Section Label | Title | Content |
|---|---------------|-------|---------|
| 1 | — | Title | µdrop logo (SVG), subtitle, tech tags (PySide6/Redis/Dramatiq/PySerial), supported hardware (DropBot + OpenDrop logos), Sci-Bots logo at bottom |
| 2 | Architecture | Three-Layer System | Frontend → Message Server → Backend stack diagram |
| 3 | Frontend | Plugin-Based GUI | 4-card grid: Device Viewer, Protocol Grid, Logger UI, Peripheral UI |
| 4 | Communication | Message Bus — Redis + Dramatiq | Request/signal flow diagrams, topic examples, MQTT wildcards |
| 5 | Hardware | Backend → DropBot Communication | 4-layer stack: Controller → SerialProxy → Firmware → DMF Chip |
| 6 | DropBot Python API | Connection & Properties | Code block + 2-column grid of attributes/setters |
| 7 | DropBot Python API | Methods & Signals | Methods list + signal tags + thread safety |
| 8 | DropBot Python API | Code Example — Turning on Channels | Code examples for channel activation + update_state + signal listening |
| 9 | End-to-End | User Click → Droplet Movement | 7-step pipeline from UI click to capacitance feedback |
| 10 | Design | Key Design Choices | 4-card grid: Decoupled F/B/Server, Plugin arch, Convention routing, Thread safety |

## Brand & Design System

### Sci-Bots Official Brand Kit

Source: `~/Downloads/product catalogue/Sci-Bots Inc. - Brand Kit.pdf`

#### Official Color Palette

| Name | Hex | RGB | Usage |
|------|-----|-----|-------|
| **Black** | `#000000` | 0, 0, 0 | Primary dark |
| **Carbon** | `#575757` | 87, 87, 87 | Secondary gray, body text on light backgrounds |
| **Alto** | `#D1D1D1` | 209, 209, 209 | Light gray, borders |
| **White** | `#FFFFFF` | 255, 255, 255 | Primary light |
| **Clover** | `#2F9A4A` | 47, 154, 74 | **Primary brand green** — use for accents, highlights, interactive elements |
| **Spring Rain** | `#A0CFA5` | 160, 207, 165 | Light green — secondary accent, hover states |

#### Official Brand Fonts

| Role | Font |
|------|------|
| **Headings** | Orbitron |
| **Body** | Lato |
| **Internal Use** | Arial |

#### Logo Variants

The Sci-Bots logo has several forms:
- **Primary logo**: Elongated — chip icon + "sci-bots" wordmark + "Little drops. Big science." tagline
- **Alternative logos**: Square chip icon only (with or without text below)
- **Color versions**: Full color (green `#059748` chip ring, `#4d4d4d` gray text), and inverse (all white on dark)
- Available as SVGs in `~/Downloads/product catalogue/scibots_logos_svg/`

#### Logo Color Details (from SVG source)

The colored logo uses these specific fills:
- Chip icon outer ring: `#90cd97` (light green)
- Chip icon inner shape: `#4d4d4d` (carbon gray)
- "Little drops. Big science." text: `#059748` (bright green)
- Text "Sci-Bots": `#4d4d4d` (carbon gray)

The inverse (BW) logo uses all `#fff` on dark backgrounds.

### Presentation Theme (adapted for dark background)

The presentation adapts the brand kit for a dark theme:

```css
/* Dark background (not in brand kit — custom for presentation) */
--bg-primary: #080c12;
--bg-secondary: #0d1420;
--bg-card: #121d2d;
--bg-card-hover: #162336;

/* Mapped from brand kit */
--green-primary: #2F9A4A;    /* Clover */
--green-bright: #059748;     /* From logo SVG */
--green-light: #A0CFA5;      /* Spring Rain */
--green-pale: #90cd97;       /* From logo SVG */
--carbon: #575757;           /* Carbon */
--alto: #D1D1D1;             /* Alto */

/* Derived for dark theme readability */
--text-primary: #f0f4f0;
--text-secondary: #a8b8a8;
--text-muted: #6b7f6b;
--border: rgba(47, 154, 74, 0.2);  /* Clover at 20% */
--glow: rgba(47, 154, 74, 0.3);    /* Clover at 30% */
```

### Fonts (in presentation)
| Role | Font | Source |
|------|------|--------|
| Headings (`h1`, `h2`, `h3`, `.section-label`) | **Orbitron** (700-800) | Google Fonts — matches brand kit |
| Body text | **Lato** (300-900) | Google Fonts — matches brand kit |
| Code / monospace | **JetBrains Mono** (400-700) | Google Fonts — added for code slides |
| OpenDrop logo text | **Varela Round** (400) | Google Fonts — matches OpenDrop website |

### OpenDrop Logo Style
CSS-only text logo matching gaudi.ch/OpenDrop branding:
- Font: `Varela Round`, sans-serif
- Color: `#E25A3E` (coral/red-orange)
- No image needed — pure CSS text

## Embedded SVG Logos

All SVGs are inline in the HTML (no external file references). There are three:

### 1. µdrop Logo (title slide)
- Class: `.microdrop-icon`
- ViewBox: `0 0 600 300`
- Uses scoped classes: `.md-green` (#37a953), `.md-gray` (#4d4d4d), `.md-white` (#fff), `.md-pale` (#90cd97)
- Contains the µdrop wordmark + "by Sci-Bots" chip icon underneath
- **Important**: Class names were renamed from `cls-1/2/3/4` to `md-*` to avoid conflicts with other inline SVGs

### 2. DropBot Logo (title slide, "Supported Hardware" section)
- Class: `.dropbot-logo-link svg`
- ViewBox: `0 0 538 228`
- Uses `cls-1` and `cls-2` classes (white fill, defined by parent `fill="#fff"`)
- Contains the "dropbot" wordmark + horizontal rules + "by Sci-Bots" chip icon + "Sci-Bots" text
- Source: derived from `microdrop_style/icons/dropbot.svg` but extended version with branding

### 3. Sci-Bots Elongated Logo (title slide bottom)
- Class: `.scibots-title-logo`
- ViewBox: `0 0 1351.31 330`
- White fill, uses `cls-1` class
- Contains "Sci-Bots" wordmark + chip icon + "Little drops. Big science." tagline

### 4. Sci-Bots Chip Icon (footer, slides 2-10)
- Class: `.slide-footer-logo`
- ViewBox: `60 10 210 230` (cropped to just the chip mark)
- White fill, no classes
- Appears in bottom-left of every content slide

## Title Slide Layout Structure

The title slide uses a special flex layout:

```
.slide.title-slide
  .title-glow (radial gradient background effect)
  .slide-content (flex column, justify-content: flex-end)
    .title-main (flex: 1, centers its children vertically)
      <a> µdrop SVG logo </a>
      <p> subtitle </p>
      .accent-line
      <div> tech tags (PySide6, Redis, Dramatiq, PySerial) </div>
      .accent-line
      <p> "Supported Hardware" </p>
      .hw-logos-row
        <a.dropbot-logo-link> DropBot SVG </a>
        .hw-logos-separator (vertical line)
        <a.opendrop-logo-link> "OpenDrop" text </a>
    <a.scibots-title-link> Sci-Bots elongated SVG logo </a>  ← margin-top: auto pushes to bottom
```

The `title-main` div takes `flex: 1` and centers content vertically. The Sci-Bots logo uses `margin-top: auto` to anchor at the bottom.

## Content Slide Layout Structure

```
.slide
  <a.slide-footer-link> Sci-Bots chip SVG (bottom-left) </a>
  .slide-content
    .section-label
    h2
    [content cards/grids]
  .slide-number (bottom-right)
```

## CSS Architecture

### Viewport Fitting (mandatory)
Every `.slide` is `height: 100vh; 100dvh; overflow: hidden; scroll-snap-align: start`. All typography and spacing uses `clamp()`. Responsive breakpoints at 700px, 600px, 500px height and 600px width.

### Reveal Animations
Elements with `.reveal` start hidden (`opacity: 0; translateY(16px)`) and animate in when the slide enters the viewport (IntersectionObserver). Stagger with `.reveal-delay-1` through `.reveal-delay-6`.

### Navigation
- Keyboard: Arrow keys, Space, Home/End
- Mouse wheel (throttled 800ms)
- Touch swipe
- Dot navigation (right side, `position: fixed`)
- Keyboard hint at bottom (`position: fixed`, auto-hides on first interaction)

### Code Blocks
Syntax highlighting via CSS classes on `<span>` elements:
- `.kw` — keywords (green-light)
- `.fn` — functions (#7dd3a0)
- `.str` — strings (#90cd97)
- `.cm` — comments (#4a6a4a)
- `.num` — numbers (#d4a574)
- `.op` — operators (alto gray)

## External Links

All open in new tabs (`target="_blank" rel="noopener"`):

| Element | URL |
|---------|-----|
| µdrop logo | https://github.com/Blue-Ocean-Technologies-Inc/Microdrop |
| "Digital Microfluidics" | https://sci-bots.com/pages/dmf |
| PySide6 tag | https://doc.qt.io/qtforpython-6/ |
| Redis tag | https://redis.io/ |
| Dramatiq tag | https://dramatiq.io/ |
| PySerial tag | https://pyserial.readthedocs.io/ |
| DropBot logo | https://sci-bots.com/products/dropbot |
| OpenDrop text | https://www.gaudi.ch/OpenDrop/ |
| All Sci-Bots logos | https://sci-bots.com/ |
| Envisage mentions | https://docs.enthought.com/envisage/ |
| SerialProxy mentions | https://github.com/Blue-Ocean-Technologies-Inc/dropbot.py |
| "DropBot" text (slides 2,5) | https://sci-bots.com/products/dropbot |

## Brand Assets (source files, not embedded)

These were used as source material and are available in the repo/local machine:

```
microdrop_style/icons/Microdrop_Icon_Trans.png     — MicroDrop icon (transparent)
microdrop_style/icons/Microdrop_Primary_Logo_*.png  — MicroDrop wordmark
microdrop_style/icons/dropbot.svg                   — DropBot wordmark (simple version)
```

Sci-Bots brand assets (outside repo):
```
~/Downloads/product catalogue/scibots_logos_svg/Scibots_Logos-07.svg  — Colored elongated
~/Downloads/product catalogue/scibots_logos_svg/Scibots_Logos-08.svg  — Colored square
~/Downloads/product catalogue/scibots_logos_svg/Scibots_Logos-15.svg  — BW elongated
~/Downloads/product catalogue/scibots_logos_svg/Scibots_Logos-16.svg  — BW square
~/Downloads/product catalogue/Sci-Bots Inc. - Brand Kit.pdf           — Full brand kit
```

## Key Technical Corrections Applied

These corrections were made based on owner feedback — do not revert:

1. **`electrodes_state_change` toggles on/off state only** — it does NOT apply high voltage. The backend then calls `proxy.state_of_channels = [...]` which triggers firmware voltage application.
2. **Architecture is three-way decoupled: Frontend / Backend / Server** — Redis can run on localhost, LAN, or cloud. Frontend can control the backend over a local network (different hosts).
3. **DropBot API slides** (6-8) reflect the actual Python API as documented by the owner.

## Known Issues / Improvement Areas

- The `cls-1` and `cls-2` classes in the DropBot SVG and Sci-Bots elongated SVG are global and could theoretically conflict. The MicroDrop SVG was already scoped to `md-*` classes. Consider scoping the others if adding more inline SVGs.
- The `presentation-assets/` folder was created during development but is no longer referenced — can be deleted.
- The `<br><br><br>` tags were removed; spacing is now handled by flexbox.
- `.md-gray` class uses `fill: #4d4d4d` which is dark on the dark background — this is intentional for the "by Sci-Bots" sub-text within the µdrop logo. If it's too dark, change to a lighter gray.
