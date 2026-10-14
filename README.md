# MSE Press × The Dot: Sponsorship Website

A one-page, animated sponsorship proposal from the **MSE Press Club** (Manouba School of Engineering)
inviting **The Dot** to become the official venue sponsor of our first podcast season.

## Run it
No build step. Open `index.html` in a browser, or serve the folder:

```bash
python3 -m http.server 8000   # then visit http://localhost:8000
```

It can be hosted for free on GitHub Pages (Settings → Pages → deploy from this branch, root folder).

## Structure
```
index.html        page content (all sections)
css/style.css     design system, layout, animations
js/main.js        interactions (network canvas, counters, slider, run-of-show, carousel, lightbox)
assets/logos/     drop logos here
assets/gallery/   drop photos here
```

## Adding your photos and logos
Every image slot shows an animated gradient placeholder until you add the real file.
Just save images with these exact names:

| File | Where it shows |
|---|---|
| `assets/logos/mse-press.png` | Nav logo (square works best) |
| `assets/logos/thedot.png` | The Dot logo on the video preview mock-up |
| `assets/gallery/thedot-cafe.jpg` | "Why The Dot" section, the café space |
| `assets/gallery/podcast-setup.jpg` | Background of the video preview mock-up |
| `assets/gallery/01.jpg` … `06.jpg` | "From our pages" gallery (01 = large tile, 04 = tall tile, 06 = wide tile) |

Photos from our Instagram (@mse.press) and Facebook pages are ideal for the gallery.
Ask The Dot for permission before using their photos or logo.
