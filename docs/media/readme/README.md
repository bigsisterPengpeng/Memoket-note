# README artwork

## Workflow overview

`workflow.svg` is an editable diagram of the complete writing workflow. It shows
supported note sources, common AI actions, KITE memory, the writing agent harness,
human review and export destinations. Its fictional Maple text illustrates the
flow. The button layout is schematic rather than a screenshot of the interface.

`workflow.gif` keeps the complete overview visible while highlighting common
AI actions, memory, the harness and export in turn. The README uses
`workflow-mobile.svg` on narrow screens and the static `workflow.svg` when the
viewer prefers reduced motion. Medium-width views also use the sharp SVG. The overview links to the SVG for closer reading.
The real application video remains linked separately.

To reproduce the animation, render `workflow.svg` at 1600 × 1120 with no class,
then with the root classes `phase-actions`, `phase-memory`, `phase-harness` and
`phase-export`. Hold the overview for three seconds, highlight each stage for
three to four seconds, then return to the overview. Export a looping GIF. Text
and positions stay fixed throughout the animation.

## Real application panels

`artwork.html` and `artwork.css` present the application's unmodified fictional
Maple screenshots in frames and crops. Serve the repository over HTTP and open
`docs/media/readme/artwork.html?scene=memory` or `?scene=agent`.

| Output | Scene | Width | Height |
|---|---|---:|---:|
| `memory.jpg` | `memory` | 1600 | 1080 |
| `agent.jpg` | `agent` | 1600 | 1140 |

The connection diagrams, video link poster and local link labels also retain
editable SVG sources here. No external badge service is required.

The workflow mark adapts the official Memoket website badge already included at
`../memoket-website.svg`. Memoket names and marks belong to their owners. See
[third-party notices](../../third-party-notices.md). Fonts use the rendering
system's installed typefaces; font files are not distributed here.
