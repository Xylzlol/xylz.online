---
name: xylz
description: Footage under a motion tracker, shown on one live LED wall. Four whole-page fields, one line weight, and every lock lands on a real destination.
colors:
  blown-white: "#F7F9FA"
  deep-black: "#050506"
  pale-sky: "#B8DCEB"
  magenta: "#FF2BD6"
  gap-white: "#FFFFFF"
  gap-black: "#000000"
  gap-sky: "#C5EBFB"
  gap-magenta: "#FF2EE5"
  soft-ink: "color-mix(in oklab, #050506 74%, #F7F9FA)"
  faint-ink: "color-mix(in oklab, #050506 10%, transparent)"
  bokeh-white-field: "rgba(184, 220, 235, 0.42)"
  bokeh-black-field: "rgba(247, 249, 250, 0.07)"
  bokeh-sky-field: "rgba(255, 255, 255, 0.3)"
  bokeh-magenta-field: "rgba(255, 255, 255, 0.22)"
typography:
  display:
    fontFamily: "Archivo, system-ui, sans-serif"
    fontSize: "clamp(4.5rem, 20vw, 6rem)"
    fontWeight: 900
    lineHeight: 0.8
    letterSpacing: "-0.03em"
    fontVariation: "'wdth' 100"
  headline:
    fontFamily: "Archivo, system-ui, sans-serif"
    fontSize: "clamp(3rem, 8.5vw, 6rem)"
    fontWeight: 800
    lineHeight: 0.9
    letterSpacing: "-0.02em"
    fontVariation: "'wdth' 62"
  title-large:
    fontFamily: "Archivo, system-ui, sans-serif"
    fontSize: "clamp(1.75rem, 4vw, 3rem)"
    fontWeight: 800
    lineHeight: 1.5
    letterSpacing: "-0.01em"
    fontVariation: "'wdth' 112"
  title:
    fontFamily: "Archivo, system-ui, sans-serif"
    fontSize: "clamp(1.25rem, 2.1vw, 1.8rem)"
    fontWeight: 800
    lineHeight: 1.1
    letterSpacing: "-0.01em"
    fontVariation: "'wdth' 112"
  report-title:
    fontFamily: "Archivo, system-ui, sans-serif"
    fontSize: "clamp(1.125rem, 1.5vw, 1.3rem)"
    fontWeight: 600
    lineHeight: 1.3
  caption:
    fontFamily: "Archivo, system-ui, sans-serif"
    fontSize: "clamp(1rem, 1.25vw, 1.2rem)"
    fontWeight: 700
    lineHeight: 1.3
    fontVariation: "'wdth' 112"
  body-lead:
    fontFamily: "Archivo, system-ui, sans-serif"
    fontSize: "1.125rem"
    fontWeight: 450
    lineHeight: 1.5
  body:
    fontFamily: "Archivo, system-ui, sans-serif"
    fontSize: "1.0625rem"
    fontWeight: 450
    lineHeight: 1.5
  note:
    fontFamily: "Archivo, system-ui, sans-serif"
    fontSize: "0.9375rem"
    fontWeight: 500
    lineHeight: 1.5
    fontFeature: "'tnum' 1"
  label:
    fontFamily: "Archivo, system-ui, sans-serif"
    fontSize: "0.8125rem"
    fontWeight: 700
    lineHeight: 1
    fontVariation: "'wdth' 112"
rounded:
  none: "0px"
  light: "50%"
spacing:
  line: "1px"
  wall-pitch-min: "6px"
  wall-pitch-max: "9px"
  dot-grid: "10px"
  gutter: "clamp(20px, 4.2vw, 64px)"
  step: "clamp(56px, 9vw, 136px)"
  rail-reserve: "110px"
  lock-pad: "8px"
  rail-gap: "22px"
components:
  target:
    textColor: "{colors.deep-black}"
    typography: "{typography.title}"
    rounded: "{rounded.none}"
    padding: "14px 0 6px"
  report-row:
    textColor: "{colors.deep-black}"
    typography: "{typography.report-title}"
    rounded: "{rounded.none}"
    padding: "20px 0 30px"
  close-link:
    textColor: "{colors.deep-black}"
    typography: "{typography.title-large}"
    padding: "4px 0"
  rail-link:
    textColor: "{colors.soft-ink}"
    typography: "{typography.label}"
    padding: "0 10px 0 0"
  rail-link-here:
    textColor: "{colors.deep-black}"
  rail-marker:
    rounded: "{rounded.none}"
    size: "7px"
  lock-caption:
    textColor: "{colors.deep-black}"
    typography: "{typography.label}"
  reticle:
    size: "26px"
  wall-cell:
    rounded: "{rounded.light}"
  list-button:
    backgroundColor: "#F0F0F0"
    textColor: "#000000"
    rounded: "{rounded.none}"
    padding: "0.25em 0.5em"
  skip-link:
    backgroundColor: "{colors.deep-black}"
    textColor: "{colors.blown-white}"
    padding: "10px 14px"
---

# Design System: xylz

## Overview

**Creative North Star: "The Tracked Footage"**

The page is footage under a motion tracker, and xylz is the one doing the tracking. One field colour owns the whole page at a time and changes by hard cut. The page itself is one live LED wall: a panel of round cells behind everything, every unlit cell faintly visible at its own still level, the name drawn by the wall as lit cells, and a soft giant echo of the name deeper behind. Over the wall, crisp 1px tracker line-work locks onto destinations and prints where they go. Behind it, a few out-of-focus discs of light show through the gaps between cells. Nothing on the page is decoration standing in for a fact: every printed label is a real host, path, handle or number.

The density is sparse and large: a huge name, four destinations, a short public record, three profile links. The world is built from a small set of materials (field, ink, light, 1px line, small bold wide-set caption) used everywhere at the same weight. Tracker motion is sampled rather than eased: geometry jumps in discrete steps. Light is the only thing allowed to soften or move freely: cells bloom on black, lit cells leave afterglow trails, the pointer is a lens on the wall, every field change pours out from the selected target around the letters, and the pointer stirs the panel like fluid. When nothing changes, the wall is still.

The world rejects the researcher default of a dark terminal bio over a row of links, and the handoff's rejected set: hacker neon, terminal costume, typing effects, fake status, decorative all-caps monospace labels, arbitrary coordinates, figure markers, mysterious filler, an animated entrance gate, and early-web OS dialog clichés.

**Key Characteristics:**
- Four whole-page fields (white, black, pale sky, magenta), cut hard, never faded, never mixed on screen.
- One LED wall behind the page, a 2D canvas (no WebGL): round cells at 6 to 9px pitch, unlit cells faintly visible with a still per-cell grain, the panel averaging to the field.
- The name is an exact set of lit cells on the wall's own grid; a soft 2.4x echo of it sits deeper, moving at 0.35 of the scroll.
- Brightness is distance: the lock at full ink, related items at 45%, afterimages sinking from 45% to nothing, the echo at 20%.
- One line weight (1px) for every rule, box, wire, outline and underline.
- Archivo variable only, 450 to 900 weight, 62% to 112% width.
- Square corners on everything drawn; circles belong only to light (bokeh discs and LED cells).
- Every label prints a real destination; no invented numbers.

## Colors

Four saturated-or-blown fields, each paired with a single ink and a gap colour, plus derived soft and faint inks and a per-field bokeh light.

### Primary
- **Blown White** (blown-white): the default field and the field for the Immunefi profile. Also the ink on the black field.
- **Deep Black** (deep-black): the ink on white, sky and magenta, and the field for GitHub. On the black field the ink inverts to Blown White.

### Secondary
- **Pale Sky** (pale-sky): the field for everything that lives on this page: Public work, the ENS competition and its reports.

### Tertiary
- **Tracker Magenta** (magenta): the field for X. It owns the whole page when it appears and is never used as an accent on another field.

### Neutral
- **Gap colours** (gap-white, gap-black, gap-sky, gap-magenta): what shows between the wall's round cells, one per field. Each sits a step lighter (or, on black, darker) than its field, so that gaps plus the faintly inked unlit cells average back to the field colour. With the wall on, the page background is the gap colour; theme-color stays the field.
- **Soft Ink** (soft-ink): 74% ink mixed into the current field in OKLab; notes under destinations, report metadata, resting rail labels. Recomputed per field (the frontmatter value is the white-field resolution).
- **Faint Ink** (faint-ink): 10% ink; the dots of the CSS dot screen that stands in when the wall cannot run.
- **Bokeh light** (bokeh-*-field): the out-of-focus discs far back, seen through the wall's gaps; sky-tinted on white, a 7% white on black, white at 30% on sky and 22% on magenta.
- **Glow**: a per-field number, 0.75 on black and 0 elsewhere, that sets how much the wall's lit cells bleed light. The bloom is drawn only on the black field.

### Named Rules
**The One Field Rule.** One field owns the entire page at a time: page background (as its gap colour), theme-color meta, scrollbar, selection and the wall all follow it. A field change is a hard cut of every token at once, never a fade, a gradient between fields, or a field-coloured panel inside another field.

**The Field Is A Destination Rule.** Each lockable item names its field, and the field reflects where it goes: white for the Immunefi profile, sky for this page's public work, black for GitHub, magenta for X. A new destination gets a field by that logic, not by taste.

**The One Ink Rule.** Text, line-work and fills use the field's single ink at full strength, or the derived Soft and Faint inks. No second accent colour. The wall mixes only field and ink per channel; the colour fringes it shows under the lens and during a cut are its red, green and blue channels pulling apart, not a palette, and they exist nowhere else.

**The Panel Averages To The Field Rule.** Every field has its own unlit level, grain and gap colour, tuned so the wall at rest reads as the field itself, not a grey screen laid over it.

## Typography

**Display Font:** Archivo variable, self-hosted (archivo-var.woff2, OFL), weight 100 to 900 and width 62% to 125% axes (fallback system-ui, sans-serif)
**Body Font:** the same Archivo
**Label Font:** the same Archivo, wide set

**Character:** one grotesque family stretched across its width axis does all the voices: condensed 62% for section headlines, normal width for the name and running text, wide 112% for labels, captions and destination names. Kerning on, optimizeLegibility.

### Hierarchy
- **Display** (900, clamp(4.5rem, 20vw, 6rem), 0.8, -0.03em): the name "xylz" only. With JavaScript it is drawn by the LED wall as lit cells at the h1's width; the text stays in the DOM, visually hidden, for assistive tech and as the no-script fallback.
- **Headline** (800, width 62%, clamp(3rem, 8.5vw, 6rem), 0.9, -0.02em): section headings ("Public work", "Elsewhere"). They are also the wire anchors for their section.
- **Title Large** (800, width 112%, clamp(1.75rem, 4vw, 3rem), -0.01em): the closing profile links.
- **Title** (800, width 112%, clamp(1.25rem, 2.1vw, 1.8rem), 1.1, -0.01em): destination names in the first viewport.
- **Report Title** (600, clamp(1.125rem, 1.5vw, 1.3rem), 1.3, max 46ch, text-wrap pretty): published report titles.
- **Caption** (700, width 112%, clamp(1rem, 1.25vw, 1.2rem), 1.3): the line under the name.
- **Body Lead** (450, 1.125rem, max 30ch): the competition summary; the tally line uses the same size at 700.
- **Body** (450, 1.0625rem, 1.5): running text; long lines held to 52 to 60ch.
- **Note** (500, 0.9375rem, Soft Ink, tabular numerals): notes under destinations and report metadata. A severity word inside metadata steps up to 800, width 112%, full ink.
- **Label** (700, width 112%, 0.8125rem, line-height 1): tracker destination captions and rail labels. Sentence or lower case as written; never uppercased.

### Named Rules
**The Width Is The Voice Rule.** Roles are separated by the width axis as much as by size: 62% shouts a section, 100% names and reads, 112% labels and points. Never add a second family or a monospace to get a "technical" voice.

**The Small Bold Caption Rule.** Tracker and rail text is small (0.8125rem), bold (700), wide (112%), in open field, in the case it was written. No uppercase tracking-spaced labels.

## Layout

The page is a single column of three sections on a fluid gutter (clamp(20px, 4.2vw, 64px)) with vertical section padding of one step (clamp(56px, 9vw, 136px)). On wide screens every section reserves 110px on the right for the rail. The LED wall spans the full document width behind all of it; its pitch is the viewport width / 170, held to 6 to 9px.

- **Stage (first viewport):** at least 100svh, a three-row grid: the name, the caption, then the destinations pushed to the bottom. The name is left-aligned and sized by width, min(100%, 74vw, max(300px, (100svh - 330px) x 2.8)), so on short screens the destinations stay inside the first viewport. Destinations sit in four equal columns with a gap of clamp(16px, 2.4vw, 40px), each topped by a 1px rule.
- **Public work:** a 5fr / 7fr grid (gap clamp(32px, 6vw, 112px)): competition summary on the left, published reports on the right as a ruled list (a rule above each row, and one below the last).
- **Elsewhere:** a wrapping row of large profile links. The section closes the page; there is no footer. (The artist concept marker was removed on 2026-10-12 at the user's request; the artist route is not on the page for now.)
- **Name echo:** the 2.4x echo starts 10% of the viewport width left of the name and 92% of a viewport down, so it peeks in at the bottom of the first screen and rises behind Public work and Elsewhere.
- **Rail:** fixed, vertically centred, clamp(12px, 1.6vw, 28px) from the right edge, items 22px apart, one 1px vertical rule on its right edge.
- **Responsive (860px and below):** the rail is hidden and its 110px reserve released; the name takes the full width; destinations fall to two columns; the public-work grid becomes one column; the stage loses its wire (the lock still lands, its caption moves inside the lock's top-right corner). **420px and below:** destinations stack in one column with no row gap, each still separated by its rule.

### Named Rules
**The Destinations In View Rule.** On any viewport, the four destinations are reachable in the first screen; the name gives up width before the destinations give up the fold.

**The Open Field Rule.** Captions and wires are placed in empty field: the stage wire is routed to a lit cell of the name whose path clears the caption by 14px, and its caption prints below the lowest lit cell it would otherwise sit on; section wires run from a heading's end or drop in the margin beneath it. Line-work never crosses text.

## Elevation & Depth

No shadows. Depth is planes separated by focus, scroll speed and brightness, the way the reference footage separates out-of-focus light from crisp overlays.

- **Far plane:** six still discs of Bokeh light, fixed to the viewport behind everything (z -2), blurred 10px, placed around the edges (mostly top-right and right, one bottom-left). They are seen through the wall's gaps.
- **Wall plane (z -1):** the LED wall, anchored to the document so it scrolls with the text and never swims. Inside it, depth is brightness and sharpness: the unlit panel at its per-field level, the name echo at 20% with soft-edged cells moving at 0.35 of the scroll, the name crisp at full ink. Behind the cells, on black only, a 10px-blurred copy of the same signal bleeds light at the field glow.
- **Page plane:** text and 1px rules.
- **Near plane (z 10):** the tracker: lock, wires, nodes, related boxes, afterimages, reticle, destination caption. The rail sits at z 15.

### Shadow Vocabulary
None. The only blurs are light: the far discs (10px), the wall's bloom (10px, opacity = field glow), and the echo's soft cell edges.

### Named Rules
**The Brightness Is Distance Rule.** Full ink belongs to the current lock and the name alone. Related boxes and their wires sit at 45%; afterimages start at 45% and sink to 0; the echo sits at 20%. Anything set back is set back by opacity or cell level, never by a shadow or a lighter colour token.

**The Light Only Blurs Rule.** Blur is reserved for light sources (bokeh, wall bloom, the echo's soft cells). Line-work, text and boxes are always crisp (crispEdges on SVG geometry).

## Shapes

Square-cornered, 1px, open. Every drawn shape is a rectangle or a straight line: lock boxes, related boxes, nodes, rail markers, rules under and above rows. Corners are marked with small filled squares (7px on the lock and afterimages, 5px on related boxes) or open 7px brackets (the reticle). Circles exist only as light: bokeh discs and LED cells (a round mask of radius 0.4 x pitch with a 0.75px edge). The one dashed line in the system marks the artist concept box, meaning "not a real destination yet".

### Named Rules
**The One Line Rule.** Every stroke is 1px: rules, boxes, outlines, wires, link underlines, focus outlines. Where a box meets a ruled target, it sits on the target's own hairline and ends on the next one: one line, never two parallel ones.

**The Square Corner Rule.** No border-radius on any box. Roundness means light.

## Components

### Lock Target
The core interactive unit: a real link the tracker can lock onto.
- **Shape:** an open block topped by a 1px ink rule (padding 14px 0 6px) in the stage; report rows carry the same rule with 20px 0 30px padding; inline targets are bold with a 1px underline at 0.22em offset.
- **Content:** a wide 800 name over a Soft Ink note; external links end with a small outward-arrow SVG drawn as a line, not a glyph.
- **States:** hover locks at once (mouse and pen; touch does not lock on hover). On the four top destinations that lock is only a preview: the field and its pour follow when the pointer settles there the way an aimed movement ends (stops for 60ms; slower than 0.12px/ms for 40ms; or 400ms on it while slower than 0.25px/ms), or at once on press, click, focus or a key. Sweeps and drifts across the row, passes on the way elsewhere, a page scrolled under a still pointer (no commit until the pointer moves 4px on the target) and a wheel turned while a preview waits commit nothing; leaving before a commit puts the tracker back on the chosen destination after 120ms. Scrolling never changes the field: back at the top, the tracker returns to the chosen destination. Checked with 13 scripted mouse scenarios (sweeps at 0.35 to 1.6px/ms, passes, scrolls, aimed stops, clicks, keys). Focus locks and writes the target's key into the URL hash. Arrow keys move the selection through all targets with wrap-around; Home and End jump to the ends; Enter or click opens. Selection and activation are separate.
- **Focus:** the lock box is the focus indicator. Without JavaScript, a 1px ink outline at 6px offset.

### Tracker Lock (signature)
- **Box:** 1px ink outline around the target, padded 8px (horizontally only on ruled targets), with four 7px filled corner squares offset 4px out.
- **Jump:** position and size move in 110ms, 3 steps, never eased.
- **Lit patch:** the wall cells inside the lock box rise 0.08 above their unlit level, so the lock reads on the wall as well as in line-work.
- **Afterimage:** the box it left stays behind as a 1px box with corner squares, sinking from 45% to 0 over 700ms; at most four on screen.
- **Wire:** a 1px line from a tracked point to the lock's top corner. On the stage the tracked point is a real lit cell of the name; in sections it is the end of the section heading (a diagonal) or a drop 12px under it. Both ends carry a node: a 15px outline square around a 7px filled one.
- **Related items:** listed relations in the same section get tick-only boxes (four 5px corner squares, no outline) at 45%, joined corner-to-corner to the lock by 45% wires with nodes. Side-by-side boxes join top corner to top corner so the wire stays above the text. A related wire shorter than 48px is not drawn.
- **Destination caption:** Label type, printed 14px off the tracked point on the side the wire does not leave from (on the stage, also clear of the name's lit cells by 16px); with no wire, inside the lock's top-right corner at 12px inset. The text is the destination itself ("immunefi.com/profile/xylz", "github.com/Xylzlol", "x.com/xylz__1", "reports.immunefi.com, #92963", "on this page").
- **Scroll pick-up:** when the locked item leaves the viewport, the lock moves to the first target of the section most in view (over 35% visible).

### LED Wall (signature)
One panel of LED cells behind the whole page, drawn on a 2D canvas (no WebGL).
- **Construction:** a signal buffer with one pixel per cell, scaled up pixel-exact (image-rendering: pixelated) under a round-cell mask. The canvas covers the viewport plus half a viewport above and below and is anchored to the document; when the reader nears its edge a re-centred frame is drawn, and the canvas moves only after that frame is committed.
- **Unlit cells:** each keeps its own still level, the field's base plus or minus its amplitude from a fixed per-cell hash (white 0.055 ± 0.02, black 0.08 ± 0.025, sky and magenta 0.07 ± 0.02, as a mix from field toward ink). The grain never animates.
- **Lit cells:** full ink scaled by a fixed per-cell factor of 0.88 to 1.0, like LEDs from different batches.
- **The name:** an exact set of lit cells on the wall's own grid. A cell is lit when its centre and at least two of four samples a third of a pitch away fall inside the letter; a lit cell with no lit neighbour is dropped. No half-lit edge cells. Every stage wire lands on one of these cells.
- **The echo:** the name again at 2.4x, 20% strength, its coverage averaged over a 3 x 3 sample spread of 0.8 pitch so its cells come out soft-edged, moving at 0.35 of the scroll.
- **Bloom:** on black only, the same signal behind the cells, blurred 10px, at the field glow.
- **Pointer lens:** within 150px of the pointer the wall is glass: cells sample from closer in (up to 2x at the centre, falling off as 1 - 0.5f²), the red and blue channels pull apart along the radius by up to 1.4 pitches at mid-radius, and unlit cells lift by up to 0.05. Mouse and pen only.
- **Afterglow:** a cell that goes dark fades by 0.075 per rendered frame instead of switching off, so the lens and the cut leave short trails.
- **Pour (field change):** three passes, computed in the worker (precomputed on predicted intent). (1) Routing: Dijkstra over the cell grid, 8 neighbours, ground cost 0.35 + 2.2·g² from value noise (0.1 and 0.25 cells⁻¹, weights 0.85/0.15, fresh seed per pour), the name's lit cells cost 3×, so the colour routes around the letters. (2) Enclosure: a widest-path pass from the panel border gives the last time each cell is still connected to the outside through unreached cells; a cell enclosed before the pour reaches it sits in a pocket. (3) Pockets: every pocket floods in from its rim the moment it closes (a poison variant that left small pockets unpoured was tried and removed, user 2026-10-12; `POISON = false` in wall.js). Routing and enclosure use bucket queues (Dial's algorithm, costs quantised to 1/32 cell): ~13ms per pour in the worker. Cells are timed by rank in fill order over 1100ms; every block of text and the cells under it take the arrival time of the block's centre, so text flips with its ground and keeps contrast; a wake band 3.5% wide travels with the front and shrinks to nothing at the end; cells switch in one step (no crossfade); nothing changes after the last cell turns (user, 2026-10-12; verified 0 changed pixels after completion). 
- **Intent (pointer heading):** pointer velocity is smoothed (time-weighted, about 50ms) and cast forward as three rays (the heading and ±7°) with a reach of 240 to 900px growing with speed; the first destination the cone enters (rect padded 14px) is the predicted target. Below 0.35px/ms, or 140ms after the pointer stops, there is no prediction. Prediction never selects: a dashed 1px line runs from the pointer to the target's nearest edge at 55% ink, open corner brackets mark the target, and the worker precomputes that target's pour so it starts the instant the pointer lands.
- **Gaze estimate (no camera, gaze.js):** a particle filter of 600 gaze hypotheses (300 on coarse pointers) in document coordinates. Motion: fixations with gamma(k=3) durations, mean 225ms on text and 280ms elsewhere; on a text line, forward reading saccades of 7±2 characters, 12% regressions, return sweeps to the next line (line boxes read from the DOM); otherwise saccades to a layout saliency map (weights per element type, sqrt area, central bias, inhibition of return with 1.8s decay), a 35% pull to fresh onsets within 600ms, or a small corrective refixation. Evidence: pointer likelihood, anisotropic (σx 110px, σy 60px, both widening with idle time, floor 0.12 to 0.84), shifted toward the intent target while the pointer moves (eyes lead the hand), a click is a 40px fix; evidence tempered by frame time, systematic resampling below ESS N/2. Estimate: mean shift (70px bandwidth) from the heaviest particle; stated precision = the radius around the estimate that holds 50% of the whole belief (weighted median distance), uncapped. Display: the belief binned onto the wall grid as ink cells in open field (cells on a text line are skipped; alpha 0.08 to 0.6 relative to the densest cell, 30fps), drawn within min(110px, 1.6 × r50) of the estimate and never under the label. Over it, the scanpath, drawn the way the reference trackers mark points: each fixation is a node, a 1px box (36 to 96px, widening gently with r50; ink 86% at 36px down to 50% at 96px, so certainty reads as brightness) around a solid square (55% of the box, max 34px) whose size is the dwell: it grows from 35% in four steps over 360ms and stops. The square is a difference blend of --swap (|field − ink| per channel), so inside it field and ink trade places exactly and text under it stays legible; on the black field a plain radial gradient (132px, laid over the square) blooms around the current one. No blurred box-shadow on the blended squares: it cost Chrome 30 to 45ms frames. A node jumps only after the estimate has moved clearly away for 90ms (fixation-like), crossing in three steps over 90ms; when the loop goes still, a pending jump is made at once so the last picture and the last node agree. The fixation it leaves becomes a ghost, its square frozen at the dwell it reached; six ghosts are kept, box and square sinking together at √(age weight) (1, 0.7, 0.52, 0.38, 0.27, 0.18, 0.1), joined in order by 1px saccade lines at the older end's weight. Labels print real numbers only: the node's page position "x:N y:N", and on the current node a second line "gaze, 50% within Npx" (the exact 50% radius, uncapped). On a jump the current readout prints twice for 180ms, the copy offset 7px right and 5px down and fading in two steps. A label takes the first of eight spots, beside the square first and then around the box, that keeps a 12px margin from all text, the name, the lock and its caption, the rail, every connector wire, every saccade line, the 48px band above any heading, and every other label, within the box's reach + 40px; otherwise it is hidden (a ghost keeps its box and square). Obstacles are measured at layout time, not per jump. The path starts over on resize. Runs in gaze-worker.js with the belief drawn on an OffscreenCanvas; the page only receives jumps. Fine pointers only (no evidence on touch). Hidden while the intent lead shows. The loop stops 1.5s after the last input. Off under reduced motion. Nothing is stored or sent.
- **Field changes:** only the four destinations at the top change the field and pour; every other lock keeps the colour it finds (user, 2026-10-12: no snapping when scrolling or hovering lower down).
- **Pour continuity:** the wall's gaps are drawn per cell by the wall itself (wall-gaps layer), so they pour with the cells; each cell remembers which field it shows, so a new pour mid-pour starts from what is on screen; re-centring the panel while scrolling shifts the pour, trails and fluid by the same rows instead of resetting them; blocks of text keep their colour until the pour reaches their centre (arrival times reported by the worker).
- **Neural gaze prior (saliency-worker.js, models/ui_saliency.onnx):** UNISAL (3.7M parameters) fine-tuned on UEyes webpage and desktop eye-tracking (3s heatmaps), weights stored int8 per output channel and dequantised at load (3.5MB, 3.1MB brotli; held-out webpage CC 0.623 vs 0.622 at fp32), run by self-hosted ONNX Runtime Web (CPU, one worker thread, ~110 to 150ms per pass). The viewport picture reaches the worker as a transferred ImageBitmap. Skipped when data saving is on. The page draws a 448×288 picture of the current viewport (field colour, the name's lit cells, rules, the lock box, every visible word in its own font, width and colour) and the worker returns a 112×72 probability map whenever the view changes (scroll, resize, new lock, field). The map is the gaze filter's saccade target distribution (80% of non-reading saccades; landing on a text line starts the reading model there) and a weak prior on every hypothesis (weight × (map+0.05)^0.25 per 100ms). Loaded only on fine pointers with 4+ cores, after idle; otherwise the layout heuristics stand in. Held-out UEyes test, webpages: CC 0.331 → 0.620, NSS 0.87 → 1.59, KLD 1.45 → 0.79 (pretrained → fine-tuned). Attribution and licences in models/ATTRIBUTION.txt. Training code in ml/ (not shipped).
- **Gaze display:** only cells holding at least 15% of the densest cell's mass are drawn, so the cloud reads as a prediction rather than noise across the page. The scanpath elements (six ghost slots, the current node, its glow and one echo) are made once and reused; a jump only moves, resizes and fades them. They are DOM elements in the tracker (which has no stacking context of its own, so each square's difference blend reaches the page behind it).
- **Fluid (pointer):** a stable-fluids solver (semi-Lagrangian advection, 18 Jacobi pressure iterations, damping 0.982) on a grid at half the cell resolution. Pointer movement over the panel adds velocity; each cell's sampling position rides the flow (displacement damped 0.972 per step), so the name smears and curls under the pointer and springs back. Runs only while the flow has energy. No flow is fired at selections.
- **Rest:** the wall renders only while something changes and stops 450ms after the last change (and while the tab is hidden). At rest it is a still image.
- **Runtime:** in a worker on an OffscreenCanvas where available, otherwise the same code on the main thread.
- **Fallbacks:** with no wall, the name is drawn on its own canvas as an LED dot panel (lit cells radius 0.42 x pitch, unlit cells at 9% ink) and the middle plane is the CSS dot screen (1px Faint Ink dots on a 10px grid, drifting at a third of the scroll). Without JavaScript the name is plain Archivo 900.

### Reticle
The pointer is tracked too: a 26px square of four open 7px 1px corner brackets, snapped to a 2px grid and moved in 50ms steps (20 samples a second). Hidden over a target (the lock takes over) and for touch.

### Rail (Navigation)
Three items (xylz, public work, elsewhere), right-aligned, Label type in Soft Ink, each followed by a 7px 1px outline square that sits on the rail's 1px vertical rule. The section most in view, and any hovered item, goes full ink with a filled square. Keyboard focus underlines the label at 4px offset. Hidden at 860px and below.

### Section Heading
Condensed 62% Headline, fit to its text, doubling as the wire anchor for its section.

### Demonlist Note
The demonlist moved from the root of xylz.online to /list. A note in the empty corner above the name, for every visitor: "Looking for the demonlist?" in Label type and the list's own button (its .button-54: Open Sans falling back to Arial, 11px caps spaced 2px, #F0F0F0, a 2px black border, a black shadow stepped out 1 to 3px, rgb(200,200,205) on hover where hover exists, pressed flat) with its 16px pixel banana, reading "xylz.online/list". It keeps those colours in every field. Below 860px the stage makes 52px of room for it, below 420px 70px (it wraps to two lines). Nothing else on the page mentions the list (user, 2026-10-12); old list URLs are handled by server redirects on xylz.online. (Until 2026-10-13 it was meant for returning list visitors only, but a display rule overrode its hidden attribute, so everyone saw it; the user chose to keep it on that basis, and it is now shown to all on purpose.)

### Touch
On a touch device (main.js adds .touch-ui from (hover: none) and (pointer: coarse), and from the last pointer used, so a touch laptop switches as it is used) the four destinations are selected and opened in two steps, because a finger going down on them is usually a scroll starting: a touch-down does nothing; a tap selects (the lock, the pour, the caption); only the selected destination shows an "open" control (Label type, 1px ink border, at least 80 x 44px, inverting while pressed; "go" with a down arrow for Public work) and only that opens it. Mouse and pen keep the hover preview and press-to-commit; Enter and assistive activation (a click with no pointer) open at once. Scrolling never moves the lock on touch. The tracker's caption steps aside on touch (the destination's own note names it and the control sits where the caption would). Below 860px the name shrinks with the viewport height (a phone on its side keeps the destinations in view). Checked by tools/touch_test.py (12 scenarios: scrolls starting on each destination, a hesitant scroll, a fast swipe stopped by a tap, scrolling across Elsewhere, tap selects, open opens, Public work's go jumps, the load-time selection is safe, activation without a pointer, control size) and tools/mobile_shots.py (390, 320, 844 x 390 landscape, 700 tablet; no horizontal overflow).

### Tab Icon
The wall writes the name in the tab. A tab icon is 16 x 16 CSS px, so the icon is a 16 x 16 LED panel, one LED per pixel, spelling "xylz" in a hand-set LED face (tab-icon.js): 4-LED letters (the l one LED) with single gaps make exactly 16 columns; x-height 5 (rows 6 to 10), the l's ascender from row 4 and the y's descender to row 11; the x and z have two-LED diagonals. The ground is a rounded tile (radius 20%) of the field, the lit LEDs ink. Up to 48px every LED is a crisp square (round dots that small only blur); from 64px they are round (radius 0.44 pitch) and the unlit ones show at 8% ink, as on the wall.

Limits it is built around (researched 2026-10-12): the tab icon is always 16 CSS px (16, 20, 24 or 32 device px); Chrome repaints a tab icon about four times a second, and about once a second in a background tab; Chrome shows animated GIF or SVG icons as a still; Chrome, Firefox and Edge take SVG icons, Safari 26 too but it ignores media queries in them (WebKit bug 309949); Google Search shows the icon at 16px and wants a square of at least 8px, preferably over 48px. No API says where the tab is.

Live: main.js redraws the icon in the current field at the tab's device size, in 250ms steps. On arrival the name scrolls in from the right (shifts 12, 8, 4, 0 columns). The pour reaches it last. Where the tab is cannot be known, so main.js estimates it (tabPoint): the browser frame around the page is measured (outer minus inner size, and from the first mouse event screenX − clientX against window.screenX, which side it is on). Side chrome over 120px means vertical tabs on that side, expected in the upper part of the list (28% down the window). Top chrome of 40px or more means a tab strip above; the tab's place along it is taken as equally likely anywhere, so the expected point is the strip's middle (after 80px on the left for the macOS window buttons, or 150px on the right for the Windows caption buttons). Otherwise (fullscreen, an installed app) the pour goes straight up. The pour's way out (tabRoute) is the line from the chosen destination to that point; where it crosses the viewport's edge is the probe the wall answers in "arrivals", and from that moment the icon pours through the LEDs in four 250ms steps at the line's angle: the edges facing that direction seed a straight front at that angle, which spreads by cheapest path with lit LEDs costing 2.6 times unlit ones, timed by rank; theme-color changes at that moment too. Without a pour (reduced motion, no wall) both change at once; under reduced motion there is no scroll-in.

Static: favicon.ico (16, 32, 48), favicon.svg (the same LEDs as crisp rectangles), apple-touch-icon.png (180, square, opaque; iOS rounds it), icon-192/512.png in manifest.webmanifest, all rendered from tab-icon.js in Chrome by tools/favicon_export.py.

### Skip Link
Ink block, field-coloured bold text, 10px 14px padding; hidden above the viewport until focused.

- **Gloss:** each cell is a domed lens: a white highlight at 37%/33% (0.26 alpha, 0.06 to 0.17 pitch) and a dark rim (0.07 alpha, 0.26 to 0.41 pitch), at 0.7 opacity on black.

## Do's and Don'ts

### Do:
- **Do** cut the whole page to the destination's field on lock, at most one cut per 340ms (under three a second); a newer request during the wait replaces the pending one.
- **Do** pour every field change from the selected target, and let the pointer stir the panel; nothing else moves on selection besides the tracker.
- **Do** keep the wall still when nothing changes: render while the lens or fluid moves, a pour runs or trails fade, then stop 450ms after the last change.
- **Do** draw the name as whole lit cells on the wall's own grid, and land every stage wire on one of them.
- **Do** tune each field's unlit level, grain and gap colour so the panel at rest averages to the field.
- **Do** keep every stroke 1px and every drawn corner square; mark corners with 7px (lock) or 5px (related) filled squares.
- **Do** set back secondary elements by opacity or cell level: 45% for related boxes and wires, 45% to 0 over 700ms for afterimages, 20% for the echo.
- **Do** move tracker geometry in discrete steps: 110ms in 3 steps for the lock, 50ms samples for the reticle.
- **Do** print the real destination in every tracker caption, and only numbers taken from the public record (placement, counts, report IDs, dates).
- **Do** say where the demonlist went as wayfinding, with the list's own button (see Demonlist Note), never with an explanatory sentence. Old list URLs are handled by server redirects on xylz.online.
- **Don't** make the demonlist part of the identity: nothing in the top four, no game imagery beyond the list's own banana on its own button.
- **Do** under reduced motion keep the field cuts as plain colour changes and drop the motion that plays by itself: the lock's stepped travel (it jumps directly), the afterimages, the pour (cuts stay plain), the pointer fluid and the echo parallax. The lens and its afterglow trail stay on, because they move only with the visitor's own pointer (user decision, 2026-10-12).
- **Do** hide the rail and drop the stage wire at 860px and below.

### Don't:
- **Don't** fade, blend or gradient between fields, or place a field-coloured card inside another field.
- **Don't** use expanding rings, punch-in zooms of the name, flows pulled toward the selection, lock-on frame animations, hard-stepped 30fps motion, colour splits or glitch tears for selection (user, 2026-10-12); the RGB split belongs to the pointer lens only.
- **Don't** animate the wall's grain or let it shimmer at rest.
- **Don't** light half cells or stray single cells in the name.
- **Don't** use WebGL for the wall; it is a 2D canvas signal under a round-cell mask.
- **Don't** use box shadows or blur on anything that is not light.
- **Don't** ease tracker movement or let it drift; only light (afterimage fade, afterglow, lens, bloom) may soften over time.
- **Don't** print invented coordinates, fake status, counters or figure markers as tracker labels.
- **Don't** add terminal costume, code or binary as decoration, monospace or uppercase tracked labels, typing effects, neon or an entrance gate.
- **Don't** round box corners, or draw any second line weight.
- **Don't** add a second accent colour or a second typeface.
