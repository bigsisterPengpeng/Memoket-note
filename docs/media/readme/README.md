# README artwork

These assets present the application; they do not replace its interface.
The embedded screenshots are unmodified captures of the fictional Maple demo.
CSS frames and crops make the relevant controls and evidence easier to read.
No synthetic application screens or personal note data are used.

## Editable sources

- `artwork.html` and `artwork.css`: hero, memory and writing-agent panels.
- `connections.svg` and `connections-mobile.svg`: diagrams of explicit import and export paths.
- `demo.svg`: a link poster for the existing 80-second workflow video.
- `button-*.svg`: local link labels without external badge services.

Serve the repository over HTTP and open
`docs/media/readme/artwork.html?scene=hero`. Use `scene=memory` or `scene=agent`
for the feature panels. Export the complete page at these CSS pixel dimensions:

| Output | Scene | Width | Height |
|---|---|---:|---:|
| `hero.jpg` | `hero` | 1600 | 1240 |
| `hero-mobile.jpg` | `hero` | 960 | 1120 |
| `memory.jpg` | `memory` | 1600 | 1080 |
| `agent.jpg` | `agent` | 1600 | 1140 |

The hero changes composition below 1100 CSS pixels. The README uses a `picture`
element to select its narrower export on small screens. It also provides normal
text, image descriptions and direct media links outside the artwork.

The mark in the hero is adapted from the official Memoket website badge already
included at `../memoket-website.svg`. Memoket names and marks belong to their
owners; see [third-party notices](../../third-party-notices.md). Fonts use the
rendering system's installed typefaces; font files are not distributed here.
