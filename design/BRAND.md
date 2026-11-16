# Context OS visual system — design direction

Status: **candidate for review**, not final approval. The interactive [prototype](prototype.html) demonstrates Search, Library, Memory detail, and extension save feedback. The direction is original to Context OS and uses the user's references as quality benchmarks rather than component templates.

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
| Ink quiet | `#9BA2AA` | Meta labels |
| Border | `#E6E9E7` | Dividers and control outlines |
| Accent | `#526187` | Primary action, selected state |
| Accent soft | `#EEF0F6` | Selected rows and badges |
| Success | `#47715E` | Save confirmation |
| Danger | `#A2525D` | Destructive actions |

Use DM Sans for headings and Inter for interface text, with system sans-serif fallbacks. Heading sizes: 40–56 px for a page statement, 24–32 px for a page title, 18–20 px for section titles. Interface text is 12–14 px with sufficient line height for reading. The spacing scale is 4, 8, 12, 16, 24, 32, 48, 64 px. Primary surfaces use 12–14 px radii; inputs and buttons 8–10 px. Borders are 1 px. Shadows are soft and used only to distinguish raised surfaces or transient panels.

Motion uses 140–220 ms transitions for hover, selection, dialog entrance, and confirmation. It supports reduced-motion preference. Focus rings are always visible. The default theme is light; dark mode can follow after the light system is approved.

## Interaction patterns

- The sidebar holds primary navigation; search remains accessible globally with Ctrl/Cmd+K.
- Search results show title, source, date, type, and the reason for the match. A side preview retains the results behind it.
- The original source is never hidden behind an AI summary. Generated content is clearly labeled.
- The extension button saves immediately. Its confirmation panel reports what was saved and offers note, project, and visible-screenshot actions.
- Empty states explain the next useful action. Errors state what failed and how to retry. Loading states preserve layout to avoid jumps.
- Responsive layouts collapse navigation and convert multi-column detail views to one column without hiding the source.

## Review criteria

Review the prototype at desktop and narrow widths. Confirm the hierarchy, readability, density, interaction feedback, and whether the identity feels distinct enough. After review, update these tokens and apply them consistently to the running app and extension. Do not mark the design system approved until that review is complete.
