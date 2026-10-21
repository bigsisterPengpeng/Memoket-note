# MEMOKET NOTE UI conventions

This document records the application's interface rules. New interface work
should follow these conventions. Change the convention here when a design
decision changes, and explain why in the corresponding change.

The visual identity follows Memoket. The note application's information
architecture remains its own: launcher, note tree, tabs, editor, context panels,
ribbon and status bar. A visual refresh must preserve keyboard shortcuts,
selection, drag-and-drop and undo behavior unless the task explicitly changes them.

## 1. Design tokens

`frontend/src/design-tokens.css` defines source colors, typography, weights,
spacing, radii, shadows and stacking levels. `shell.css` and `styles.css` expose
semantic aliases for existing components. Reuse those names rather than adding
component-specific copies of the same values.

The current light surfaces are neutral. Brand color belongs on small accents,
selected states and primary actions. Use `--brand-fill` for filled controls with
white labels, and `--brand` for links, icons and borders.

| Role | Token or convention |
|---|---|
| Brand accent | `--brand`, `--brand-text`, `--brand-weak` |
| Filled primary action | `--brand-fill`, `--brand-press` |
| Window, card, editor, sidebar | `--mk-bg`, `--mk-surface`, `--mk-paper`, `--mk-sidebar` |
| Primary and secondary text | `--ink`, `--ink-2` |
| Decorative text and placeholders | `--ink-3` |
| Borders and hover | `--mk-line`, `--mk-line-2`, `--mk-hover` |
| Danger and recording | `--live` |
| Revision additions and deletions | `--ins`, `--del` |
| Screen-activity categories | `--jn-1` through `--jn-8` |

Keep activity category colors distinct from brand colors. Preserve semantic
addition/deletion colors in revisions. Do not recolor these systems as decoration.

### 1.1 Theme behavior

Dark mode follows `@media (prefers-color-scheme: dark)`. Electron drives the system
preference through `nativeTheme.themeSource`; web builds can follow the host
system. Define both light and dark values when adding a token or component.
Do not introduce a separate `[data-theme]` switching mechanism.

### 1.2 Contrast and readable text

Use `--ink-2` or a stronger text token for labels, counts and explanations.
`--ink-3` is reserved for placeholders and decoration. Check contrast against the
actual surface, including translucent surfaces and disabled controls.

Normal readable text should reach 4.5:1 contrast. Decorative elements covered by
the existing design policy may use the 3:1 threshold. Filled controls need their
own contrast check in both themes; a brighter brand accent is not automatically
a suitable button fill.

### 1.3 Typography and scale

Use the `--t-*` type scale and `--w-*` weight scale. UI labels generally use
`--w-semi`; long-form editor text uses `--w-normal`. Reading text has a separate
scale (`--t-read`, `--lh-read`, `--t-read-h1` through `--t-read-h3`). Large titles
use the display font family; body controls use the text family.

Icon size comes from `--icon-*`, independently of text size. Use `--s-*` for
spacing, `--r-*` for shape and named `--z-*` levels for overlays. Changing text
readability must not resize every icon or disturb unrelated layout dimensions.

Use tabular numerals for changing counts, durations, statistics and status values.

## 2. Component conventions

### 2.1 Buttons

Standard buttons are 33px high, with a 28px compact variant. They use the shared
radius, label and spacing tokens. Default buttons are quiet ghost controls;
primary controls use `--brand-fill` and white text. Dangerous actions use the
semantic danger color and provide undo when the operation supports it.

A disabled primary action uses its disabled surface and text treatment instead
of only reducing the opacity of a filled brand button. Provide a reason for a
disabled action. A button styled as a card, tab, link or other multi-line surface
must explicitly override inherited fixed height and white-space constraints.

Use one competing primary action per decision area. Repeated independent decisions
may each have a primary action when the actions do not compete with each other.

### 2.2 Inputs and size variants

Form inputs use the shared 38px control height; search controls use the 32px
variant. Apply the shared border, background, radius and focus treatment.

Size variants belong in CSS classes. A compact select must retain space for its
arrow; replacing its entire padding inline can make text overlap that arrow.
Use visible labels or accessible names for every input.

### 2.3 Lists, tabs and selected states

Selected rows use the selected surface and brand-colored icon. Avoid adding
unrelated shadows or heavier text merely to indicate selection. Typical navigation
and folder rows use the established 36px and 34px heights.

Counts and keyboard hints use their shared chip/badge styles. Keep category
filters and tags visually consistent across panels.

### 2.4 Cards and previews

Use the shared card surface, border, radius, padding and shadow. Only interactive
cards receive an interactive hover treatment. Informational cards must not imply
a click action.

Titles, descriptions and preview details must wrap within the available width.
Flexible text columns need `min-width: 0`; grid columns containing long text
should permit shrinking with `minmax(0, 1fr)`. Keep icons, badges and close controls
from consuming or expanding the text column unexpectedly.

Use component-specific preview classes. A generic class such as `.preview` can
inherit unrelated global styles when a preview appears on hover. Pointer hover
and keyboard focus should expose equivalent preview content without selecting
a workflow until the user activates it.

### 2.5 Menus, popovers and dialogs

Use the shared surface, border, radius, padding and popover shadow. Give dangerous
menu items the semantic danger treatment. Keep focus indication visible.

Constrain overlays to the viewport. Long descriptions and unbroken identifiers
must wrap. A tall popover or dialog must scroll internally, while its close and
primary controls remain reachable. Recheck positioning near every viewport edge.

Small dialogs use `min(440px, 92vw)`. Larger panel dialogs share their shell and
set only a named width variable for the content. Respect the shared viewport
height limit instead of copying slightly different shells into each caller.

### 2.6 Toasts, icons and native controls

Toasts use the shared inverse surface/text treatment. Errors may use a danger
accent rather than replacing the entire toast with a red block.

Use the application's `Icon` component, which maps legacy `bx-*` identifiers to
Lucide icons. Do not add a second icon font. Colored emoji do not replace control
icons, and a symbol glyph must not be the entire label of an icon button. Give
icon buttons accessible names and titles.

Checkboxes, radio controls and placeholders use the existing shared styles so
their states remain visible in both themes.

### 2.7 Motion and the composer

Use short transitions for color, border, background and shadow. Use transforms
for movement rather than animating layout dimensions. Respect
`prefers-reduced-motion: reduce` for every added animation or transition.

The bottom composer uses its existing translucent surface, width and control
order. Preserve its positioning and readable fade over the document. A running
action must show a visible stop control or a meaningful busy label.

## 3. Requirements for interface changes

1. Source visual values from design tokens, including inline JSX styles.
2. Keep UI typography separate from reading typography.
3. Use existing control variants; explicitly release fixed sizing when repurposing buttons.
4. Give each decision area a clear primary action.
5. Mark dangerous actions and preserve available recovery paths.
6. Implement light and dark states together.
7. Label inputs visibly or through an accessible name.
8. Name icon buttons and explain disabled actions.
9. Make clickable surfaces keyboard-operable through native controls or the shared helper.
10. Preserve the separate activity category palette.
11. Add transitions only when reduced-motion settings can disable them.
12. Use tabular numerals for changing interface values.
13. Use the icon component rather than colored emoji as controls.
14. Reuse styled native form controls.
15. Apply click-like hover effects only to actual interactive elements.
16. Add custom-property fallbacks only where the fallback can meaningfully be used.
17. Keep hover, focus, preview and selection behavior distinct and accessible.

Long operations must visibly show progress or a running state. Register a busy
label or document the control's own feedback in the busy-state gate. Disabling
an action alone does not explain that work is in progress.

## 4. Review scope

Check note navigation, editor and revisions, the knowledge base, settings,
imports, skills and writing workflows. Exercise empty, loading, disabled, success,
error and cancellation states. For writing templates, inspect every category and
long title/description through both hover and keyboard focus.

## 5. Verification

Run `npm test` and `npm run build` from `frontend/`, and the appropriate backend
and desktop checks. Frontend gates cover accessibility, tokens, icons, CSS
classes, busy feedback and other shared contracts. Scanner gates must verify
that they actually saw the intended source files.

Automated checks do not establish visual fit. Inspect light and dark themes at
normal desktop size and at least 1000×700. Include long titles, long identifiers,
expanded descriptions, menus near viewport edges and enlarged text. Use actual
DOM measurements when a screenshot cannot explain clipping or overlap.

After any color change, recalculate text and control contrast against their
actual backgrounds. After typography, spacing or radius changes, repeat narrow
window checks. Report any unavailable visual verification explicitly.
