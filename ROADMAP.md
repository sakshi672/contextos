# Context OS: complete web product roadmap

## Product boundary

Build a complete, public-ready web product through the brief's **Intelligent Memory** stage. The product has two connected clients:

- **Web app:** account, library, search, projects, collections, tags, relationships, graph, timeline, import/export, settings, and source-grounded AI features.
- **Browser extension:** an explicit Save current tab action, with optional visible screenshot and user note. The extension sends captures to the same account and memory store as the web app.

The first release covers browser tabs, manually entered URLs and notes, and uploaded PDFs, documents, and images. Capture from other desktop applications needs a desktop companion and is outside this web release. Continuous recording, email access, mobile apps, collaboration, APIs, and MCP integrations remain later platform work.

## The capture promise

Clicking the extension button saves the current tab immediately. A small confirmation panel then lets the user add a project or note, or choose **Save visible screenshot** as an additional action. A successful save appears in the web library immediately. The extension reports when page text cannot be extracted and still allows a URL, note, and screenshot capture where supported. A screenshot represents the visible tab area, not an entire long page or the whole desktop. Capture is explicit and user initiated.

The capture pipeline stores the original URL, title, time, source type, user note, extracted text, optional image/file, extraction status, and provenance of each field. Original content and derived content are kept separately. The app must avoid collecting form entries, passwords, and hidden page data as part of routine text extraction. Users can inspect and edit a saved capture, then delete it later.

## Visual identity and UI direction

Visual quality is a core product requirement. Context OS should feel like a premium, modern productivity tool with the composure of a desktop application. Linear, Notion, Arc, Raycast, Readwise, and Obsidian are references for level of polish and interaction quality; the final interface must have its own visual identity and must not copy their layouts, branding, or distinctive components.

Use a **light theme by default**. The proposed identity is quiet and editorial: warm near-white surfaces, deep ink text, neutral grays, and one restrained accent color to signal selection and action. Choose the final palette and typography through design prototypes, then record them as reusable design tokens. A dark theme can use the same hierarchy and components, but the light theme is the primary design target.

Keep the interface minimalist and elegant: clean typography, generous but purposeful spacing, subtle borders, soft shadows, and one consistent system of rounded corners. Use smooth, short transitions and micro-interactions to clarify feedback and state changes. Avoid excessive gradients, color, ornament, and animation. Search and the original source should be more prominent than the graph or AI assistant.

Use a consistent component system across the web app and extension. Support keyboard navigation, readable contrast, reduced-motion preferences, responsive layouts, and visible loading, empty, success, and error states. Density should suit research work: information remains easy to scan without making every screen sparse.

### Key screens

The desktop web app uses a persistent left navigation for **Search**, **Library**, **Projects**, **Timeline**, and **Connections**, plus a prominent **Save** action. The main area changes with the task. On smaller screens, navigation becomes compact and core capture/search actions remain accessible.

| Surface | Primary layout and behavior |
| --- | --- |
| Search | Large search field, useful filters, ranked result list, clear match reasons, and a source preview. Search is also accessible from every screen. |
| Library | Scannable cards or rows with title, source, type, saved date, project, and extraction status; sort and filter controls. |
| Memory detail | Original source or file preview beside the user's notes, metadata, highlights, relationships, and related items. Original text and AI-generated content are visually labeled. |
| Project | Project overview with associated memories, project search, notes, timeline, connections, and a source-grounded assistant. |
| Timeline | Chronological view of explicitly saved memories with project and type filters. |
| Connections | Simple, readable graph with a list alternative; selecting a link shows its type, origin, and evidence. |
| Assistant | Conversational answers with citations that open the exact memory and passage/page where possible; uncertainty and missing evidence are shown plainly. |
| Extension | Small confirmation panel after one-click save, showing what was captured, save status, optional note/project, visible screenshot action, and a link to the memory. |

Before building the full interface, create and review a high-fidelity visual prototype of Search, Library, Memory detail, and the extension panel in the default light theme. It should include populated and empty states, responsive behavior, hover/focus states, and the one-click save feedback. Approve the visual system and interaction patterns before applying them to the remaining screens. At public release, review every screen for visual consistency and polish alongside functional and accessibility checks.

## Build stages

| Stage | Deliverable | Completion check |
| --- | --- | --- |
| 0. Architecture and specifications | Choose one backend stack, hosted account and file storage design, database, extraction pipeline, extension permissions, AI provider boundary, and initial supported file types. Define the memory schema and capture contract. Prototype and approve the light-theme visual system for core screens. | Architecture and acceptance criteria are documented; the repo can run locally; core screen prototypes establish the design direction. |
| 1. Core memory platform | Accounts and data isolation; memory create, read, edit, and delete; original file storage; library and detail view; extraction jobs and statuses; data export. | A user can save and retrieve their own persistent records; deletion removes associated stored and indexed data. |
| 2. One-click browser capture | Browser extension with explicit Save current tab, optional visible screenshot, note/project editing, authentication, duplicate handling, and extraction failure feedback. | A supported tab can be saved in one action and found in the web app; unsupported pages fail clearly. |
| 3. Cross-source capture | Manual URL capture, PDF and selected document uploads, images/screenshots, notes and snippets; text extraction and image OCR where supported. | Every supported source can be saved, inspected, and searched; scanned or unsupported content has a clear status. |
| 4. Retrieval and organisation | Full-text search, source/date/type/project filters, ranking and match explanations; tags, collections, multi-project association. | Known phrases retrieve the expected item; users can search across and within projects without duplicate records. |
| 5. Context exploration | Manual relationships, simple graph, saved-item timeline, annotation/highlight support, and project views. | Users can create, inspect, edit, and remove links; graph and timeline open original memories. |
| 6. Intelligent Memory | Hybrid keyword and semantic retrieval; vague-query evaluation; related-memory and relationship suggestions with review; project assistant, summaries, and comparison with passage or page citations. | AI features can be disabled; claims link to sources; unanswered questions and uncertain inferences are marked; usage is limited and visible. |
| 7. Public release readiness | Visual consistency review, accessibility, security review, rate limits, backup/restore, performance, browser compatibility, observability without raw private content, documentation, deployment, and end-to-end tests. | Release checklist passes on a deployed staging environment before public launch. |

These are internal delivery stages. Public access begins after stage 7 passes; the stages are not separate public releases.

## Retrieval quality gates

Create a repeatable set of saved items and intended-item queries during development. Include exact phrases, partial titles, source/date clues, and meaning-based descriptions. Record whether the intended source appears in the first results, time to find it, and failures. Compare semantic retrieval with the keyword baseline before shipping it. Keep the original item and the reason each result matched visible to the user.

## Decisions to settle in stage 0

1. Initial browser support (recommend Chrome/Chromium first).
2. Supported document formats and upload limits for launch.
3. Hosted storage region, retention, and backup policy.
4. Default AI state, model provider, consent text, and monthly usage limits.
5. Final interaction details for the confirmation panel after the one-click save.

The canonical product brief supplies the overall vision. This roadmap records the agreed launch boundary and the implementation order.
