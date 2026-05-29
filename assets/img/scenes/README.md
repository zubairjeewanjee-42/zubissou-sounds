# Scene Images — Drop-in Overrides

The window on the Listening Station rotates through five scenes. Each renders as pure-CSS illustration by default. **Drop an image file in this folder named after the scene's slug, and the page will swap it in automatically** — no code changes needed.

## How it works

On every page load, the JS tries to fetch each of:

```
assets/img/scenes/beach.{jpg,jpeg,png,webp}
assets/img/scenes/forest.{jpg,jpeg,png,webp}
assets/img/scenes/city.{jpg,jpeg,png,webp}
assets/img/scenes/rain.{jpg,jpeg,png,webp}
assets/img/scenes/garden.{jpg,jpeg,png,webp}
```

If a file exists, the page hides that scene's CSS illustration and shows your image (set as `background-size: cover; background-position: center`). The weather particles, scene dots, and temperature readout stay on top.

## What each slug represents

| Slug | Vibe | Auto-runs at |
|---|---|---|
| `beach` | Palms · ocean horizon · warm sand · bright sun | 10am–3pm |
| `forest` | Snow peak · row of pines · lake · grass | 3pm–6pm |
| `rain` | Magenta evening sky · always raining | 6pm–9pm |
| `garden` | Central snow-capped mountain · meadow · flower beds | 6am–10am |
| `city` | Nighttime skyline with lit windows | 9pm–6am |

Click any of the dots in the bottom-left of the window to manually switch scenes at any time.

## Recommended specs

- **Aspect**: ~ 8:1 to 4:1 (the window is wide and short — ~1240×160 desktop)
- **Resolution**: at least 1600×400 (scales down well; up scales poorly)
- **Format**: WebP first if possible (smaller, sharper), then JPG, then PNG
- **File size**: aim for <200KB per scene to keep page snappy

If your image is portrait or square, crop it before dropping — `background-size: cover` will fill the window but the centered portion is what shows.

## Where to get images

- **Take your own** — phone photos of compositions you like
- **Generate with AI** — Midjourney / DALL-E / Stable Diffusion with prompts like *"Japanese city pop poster, flat illustration, palm tree, sunset, hard horizon, no text"*
- **License from a stock site** — Shutterstock, Adobe Stock, etc.
- **Commission an illustrator** — if you want bespoke

Whatever the source, make sure you have the right to use the image privately before dropping it here.

## To revert to CSS art

Delete the file (or rename it). Next page load, the CSS scene comes back.
