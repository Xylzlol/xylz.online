# xylz

The personal site of **xylz**, an independent security researcher. One page, four links, built for xylz.online.

![Choosing GitHub: the black field pours out from the link, cell by cell, and works its way around the letters](media/pour.webp)

The whole page is one LED wall. Every surface you see is a lit or unlit cell, the name included, and over it sits the thin line-work of a motion tracker that locks onto whatever you point at. Choosing a destination changes the colour of the entire page. The new colour leaves the link you picked and finds its way across the wall the way water crosses uneven ground, and it goes around the letters because they are slow to cross.

It is plain HTML, CSS and JavaScript, about 4,100 lines without a framework, a build step or WebGL. There is one self-hosted variable font and a 3.5 MB neural network that only desktops download. The first view is 131 KB over the wire.

## What happens on the page

### The pour

Every pour is computed fresh:

1. The wall is a grid of cells over ground made of two octaves of value noise, with a new seed each time, so no two pours take the same shape.
2. Arrival times come from Dijkstra's algorithm over 8 neighbours. Step costs are quantised to 1/32 of a cell, which turns the priority queue into a ring of buckets ([Dial's algorithm](https://doi.org/10.1145/363269.363610)). That makes it linear time and allocation-free. The name's lit cells cost three times as much to cross.
3. A widest-path pass from the border finds the pockets the front is about to seal off. Each pocket floods inward from its own rim the moment it closes, so nothing is still changing when the pour ends.
4. Cells are timed by their *rank* in arrival order and spread over 1.1 s. That keeps the duration fixed whatever the distances, without the top-to-bottom sweep that bucketing times would cause.
5. Each block of text changes colour at the moment the front reaches its centre, together with the ground behind it, so it stays readable all the way through.

The routing takes about 13 ms in a worker. Usually it has already run before you click (see below).

![Choosing X after GitHub: magenta pours over black](media/pour-x.webp)

### It reads your aim

A pointer passing over a link hasn't chosen it yet, so hovering only previews a destination. The tracker moves at once and the colour waits. The pour starts when the movement ends the way an aimed movement ends:

- the pointer stops on the link for 60 ms
- it slows below 0.12 px/ms for 40 ms, the final corrective phase of a pointing movement
- it lingers slowly on the link for 400 ms

Sweeps across the row, passes on the way somewhere else, a page scrolled under a still pointer and a turn of the wheel commit nothing. While the pointer is still travelling, a cone of rays cast from its smoothed velocity predicts where it is going: a dashed lead marks the guess, and the wall computes that pour in advance.

`tools/pour_intent.py` checks all of this with real mouse input in Chrome: 13 scenarios, from fast and slow sweeps to aimed stops, clicks and keys.

### It guesses where you are looking, without a camera

![The gaze scanpath: fixations as boxes around solid squares that grow with dwell time, joined by saccade lines](media/scanpath.webp)

The tracker also follows your eyes, or a running estimate of them, worked out from the pointer and the page alone. It runs in its own worker.

A particle filter keeps 600 guesses of where your gaze is, in page coordinates. Between observations the guesses move the way eyes do. Fixations last a gamma-distributed ~225 ms on text and ~280 ms elsewhere. On a line of text, the next jump is a forward step of 7 to 9 characters, sometimes a short step back, and a sweep to the next line at the end. Elsewhere, the next fixation is drawn from where people tend to look on interfaces.

That comes from a neural network: [UNISAL](https://github.com/rdroste/unisal), a saliency model, fine-tuned on [UEyes](https://zenodo.org/record/8010312), a dataset of 1,980 interface screenshots eye-tracked with 62 participants. It was trained here on an RTX 4070 SUPER. On UEyes' held-out webpages:

|                | CC ↑  | NSS ↑ | KLD ↓ |
|----------------|-------|-------|-------|
| UNISAL, pretrained | 0.331 | 0.87 | 1.45 |
| fine-tuned on UEyes | 0.620 | 1.59 | 0.79 |

Stored as int8 weights, it scores CC 0.623 against 0.622 at full precision, in 3.5 MB. ONNX Runtime Web runs it in another worker, on a picture of your current view, in 110 to 150 ms.

The pointer is the evidence the guesses are weighed against. The hand lags the eyes by about 700 ms on average (Huang et al., as summarised by [Navalpakkam et al. 2013](https://doi.org/10.1145/2488388.2488471)). When you aim at a link your eyes are already on it, so the predicted target counts for more than the cursor. A cursor at rest says less the longer it rests.

This has a hard limit, and the page says so. The instantaneous eye and mouse positions correlate poorly (r² < 0.05 in Navalpakkam's study), so the label prints the estimate's own uncertainty: *gaze, 50% within N px*, the radius that holds half of everything the filter believes. Each fixation leaves a box with its real page position, sinking back as newer ones arrive. The scanpath shows on mouse-driven devices only and stops computing 1.5 s after your last input.

### The tab icon

A tab icon is 16 × 16 pixels, so it is drawn as a 16 × 16 LED panel spelling **xylz** in a hand-set LED face. Four-LED letters with one-LED gaps (the l is a single column) come to exactly sixteen columns. On load, the name scrolls into the tab.

The pour reaches the tab too. A page can't know where its tab is, but it can measure the browser frame around it. A thick side means vertical tabs on that side. Otherwise the tab is somewhere along a strip above, and since any spot is as likely as any other, the page aims at the middle of the strip. The pour leaves the page where the line from your link to that point crosses the edge of the window. When the wall reports the colour has arrived there, the icon floods through its LEDs at the same angle, and the address-bar colour changes with it. Chrome repaints tab icons about four times a second, so the icon moves in 250 ms steps.

![The tab icon, frame by frame in Chrome: the name scrolling in on load, then the pours to white, sky, black and magenta, each entering at its own angle](media/tab-icon.png)

### On a phone

A finger landing on a link is usually the start of a scroll, so on touch screens nothing happens on touch-down. A tap selects a destination (the lock, the pour); only the selected link shows an **open** control, 44 px tall, and only that leaves the page. `tools/touch_test.py` drives this with synthesized touch on a 390 px phone: 12 scenarios, including scrolls that start on every link and a fast swipe stopped by a tap.

## Measured

On a desktop Chrome (RTX 4070 SUPER), from `tools/perf_profile.py` and `tools/perf_ab3.py`:

| | |
|---|---|
| Main thread, idle | 0 % (everything stops 1.5 s after the last input) |
| Main thread, pointer circling the links | 9 % |
| Main thread, lens over the name | 6 % |
| Main thread, scrolling | 4 % |
| Worst frame while moving the pointer for 6 s | 13 to 18 ms |
| First view over the wire (brotli) | 131 KB |
| Neural model and runtime, desktops with 4+ cores, loaded when idle | 5.5 MB (brotli) |

Under `prefers-reduced-motion` the colour changes without pouring, and the gaze, fluid and afterimages are off. The pointer lens stays, because it only moves when you do.

## Run it

```bash
python -m http.server 8765 --directory site
```

Then open http://localhost:8765/. After editing anything in `site/`, bump the `?v=` cache key (it appears in `index.html`, `main.js`, `wall-worker.js` and `gaze-worker.js`) and rebuild the pre-compressed copies:

```bash
python tools/compress.py
```

In production, serve the `.br` and `.gz` files directly (`brotli_static` / `gzip_static` in nginx). Without them, the neural assets cost 18 MB instead of 5.5 MB.

## What is where

```
site/                 the page, ready to serve as static files
  index.html          markup: the stage, public work, elsewhere, the tracker overlay
  style.css           the four fields as tokens, every component
  main.js             the controller: lock, intent, hover/commit, touch, tab icon, gaze display
  wall.js             the LED wall: cells, gaps, bloom, lens, fluid, the pour
  wall-worker.js      runs wall.js on an OffscreenCanvas
  gaze.js             the gaze particle filter
  gaze-worker.js      runs it, draws the belief, decides fixations
  saliency-worker.js  runs the saliency network with ONNX Runtime Web
  tab-icon.js         the 16 x 16 LED tab icon
  models/  vendor/  fonts/  art/
tools/                headless-Chrome checks, recorders and build scripts
ml/                   training and export code for the saliency model
media/                the images in this file, recorded by tools/record.py
DESIGN.md             the design system: tokens, components, every rule and number
```

## Checking changes

Everything in `tools/` drives a real Chrome over the DevTools protocol. It needs Python 3.10+ with `websocket-client`, `Pillow`, `numpy`, `brotli` and `onnxruntime`.

| Script | What it checks |
|---|---|
| `pour_intent.py` | the 13 mouse scenarios for when a pour may start (must stay 13/13) |
| `touch_test.py` | the 12 touch scenarios on a phone (must stay 12/12) |
| `perf_profile.py`, `perf_ab3.py`, `circle.py` | main-thread load, worst frames, long tasks |
| `interact.py`, `capture.py`, `mobile_shots.py` | screenshots after scripted input, at desktop, laptop and phone sizes |
| `saliency_gap.py` | how much the page's own picture of the view changes the network's answer |
| `favicon_export.py`, `favicon_pour.py` | renders the icon set; records the tab icon through a pour |
| `record.py` | the animations in this README |

## Training the model

`ml/` holds what produced `site/models/ui_saliency.onnx`. `fetch_ueyes.py` pulls only the needed parts of the 13 GB UEyes archive with ranged requests. `train_ui.py` fine-tunes UNISAL with the dataset held on the GPU, in bf16 with OneCycle and early stopping. `export_onnx.py` and `weight_int8.py` produce the shipped file. The UNISAL code and pretrained weights come from its own repository and are not copied here.

## Credits

- [Archivo](https://github.com/Omnibus-Type/Archivo) by Omnibus-Type, SIL Open Font License 1.1 (`site/fonts/Archivo-OFL.txt`)
- [UNISAL](https://github.com/rdroste/unisal) by Droste, Jiao and Noble (ECCV 2020), Apache License 2.0 (`site/models/UNISAL-LICENSE.txt`)
- [UEyes](https://zenodo.org/record/8010312) by Jiang, Leiva, Tavakoli, Houssel, Kylmälä and Oulasvirta (CHI 2023), CC BY 4.0. The fine-tuned weights derive from it (`site/models/ATTRIBUTION.txt`)
- [ONNX Runtime Web](https://onnxruntime.ai/) 1.30.0, MIT License (`site/vendor/ort/LICENSE.txt`)

The site's own code and design: © xylz.
