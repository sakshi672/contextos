# Phase 0 visual review

Status: internal review complete. User selected the light background as the working direction on 16 November 2026; detailed visual refinement remains open during implementation.

Open [the interactive prototype](prototype.html) directly in Chrome or Edge. Use the controls across the top to switch Search, Library, Memory detail, and Extension save; switch Populated, Empty, Loading, and Error; then compare Light theme with Graphite theme. The file is a visual study with sample content, not the running product.

## Internal checks

| Area | Checked | Result |
| --- | --- | --- |
| Populated views | Desktop Search, Library, Memory detail, and extension capture confirmation | Clear source hierarchy and distinct save feedback. |
| Empty, loading, error | Search states; the same state renderer serves the other views | Main heading and search/filter controls stay in place. Empty has a next action; error has retry copy. |
| Hover and focus | Navigation, controls, cards, result selection, and focused search field | Hover is restrained; focused search shows a visible ring. |
| Small screen | Search and extension at a 500 px browser viewport | Single-column layout; controls remain available in a horizontally scrollable preview bar. A true 390 px device viewport still needs browser-device QA during implementation. |
| Graphite comparison | Desktop Search, extension, and narrow Search | Deep neutral surfaces retain hierarchy; metadata and result explanations were brightened for readability. |

The recommendation is a warm-white default with graphite as an optional theme. This keeps lengthy source content comfortable to read and gives the product a technical aesthetic through precise type, dark controls, structured metadata, and a cool accent. Avoid pure black: the graphite palette separates the app canvas, panels, selection, and overlays more clearly.

## Working decision

Proceed with the light theme as the default and the [brand tokens and interaction patterns](BRAND.md) as the implementation baseline. Keep the graphite prototype available for later comparison. Revisit density, typography, and technical character as real screens are built; this choice does not require shipping a dark-mode setting.
