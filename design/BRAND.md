# Context OS visual system — design direction

Status: **light theme approved as the working implementation baseline** on 16 November 2026. The interactive [prototype](prototype.html) demonstrates Search, Library, Memory detail, and extension save feedback in light and graphite themes. The direction is original to Context OS and uses the user's references as quality benchmarks rather than component templates. Visual details may be refined during implementation.

## Idea

**Quiet focus, immediate recall.** The app presents saved knowledge as an organized workspace. It favors editorial clarity over dashboard decoration: precise type, soft paper-like surfaces, compact context labels, and one subtle accent for actions and selection. Search and the original source carry the strongest visual emphasis.

## Mark and voice

The provisional mark is a rounded open-frame symbol: a small shape suggesting a memory held in context. Pair it with a restrained `contextOS` wordmark. The product voice is direct, calm, and specific: “Saved to your library”, “Page text could not be captured”, “Open original source”. Avoid mystical memory metaphors or AI-first language in the interface.

## Tokens

| Token | Light-theme value | Use |
| --- | --- | --- |
| Canvas | `#F7F8F6` | App background |
| Surface | `#FFFFFF` | Cards, panels, menus |
| Surface muted | `#F3F4F2` | Secondary controls |
| Ink | `#252B35` | Main text |
| Ink secondary | `#6F7782` | Supporting text |
| Ink quiet | `#6E7883` | Meta labels with readable contrast |
| Border | `#E6E9E7` | Dividers and control outlines |
| Accent | `#526187` | Primary action, selected state |
| Accent soft | `#EEF0F6` | Selected rows and badges |
| Success | `#47715E` | Save confirmation |
| Danger | `#A2525D` | Destructive actions |

Use DM Sans for headings and Inter for interface text, with system sans-serif fallbacks. Heading sizes: 40–56 px for a page statement, 24–32 px for a page title, 18–20 px for section titles. Interface text is 12–14 px with sufficient line height for reading. The spacing scale is 4, 8, 12, 16, 24, 32, 48, 64 px. Primary surfaces use 12–14 px radii; inputs and buttons 8–10 px. Borders are 1 px. Shadows are soft and used only to distinguish raised surfaces or transient panels.

Motion uses 140–220 ms transitions for hover, selection, dialog entrance, and confirmation. It supports reduced-motion preference. Focus rings are always visible, including around the search field. The default theme is light.

## Graphite theme study

The prototype includes a near-black alternative for comparison. It uses `#11151C` canvas, `#1B212B` panels, `#EDF1F6` primary text, and a cool `#A6B7E7` accent. Surfaces are separated with visible borders and restrained elevation. Graphite is retained as a design study; a dark-mode setting is not part of the approved Phase 0 implementation baseline. It can be considered later without changing the light default.

## Interaction patterns

- The sidebar holds primary navigation; search remains accessible globally with Ctrl/Cmd+K.
- Search results show title, source, date, type, and the reason for the match. A side preview retains the results behind it.
- The original source is never hidden behind an AI summary. Generated content is clearly labeled.
- The extension button saves immediately. Its confirmation panel reports what was saved and offers note, project, and visible-screenshot actions.
- Empty states explain the next useful action. Errors state what failed and how to retry. Loading states preserve layout to avoid jumps.
- Responsive layouts collapse navigation and convert multi-column detail views to one column without hiding the source.

## Review criteria

Open [prototype.html](prototype.html) in a browser. Use the top row to switch screens, data states, and the light/graphite theme. [Review notes](REVIEW.md) record the internal checks and the decision to proceed with light. Apply the light tokens and interaction patterns consistently to the running app and extension, refining them when usability testing shows a need.
