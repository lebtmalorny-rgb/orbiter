# Project rules for satellite dynamics Python code

- Product goal: build a local satellite-motion visualization app with clear 3D navigation
  and local assets. Built-in/manual trajectories must run without network access; the
  SGP4 real-time mode may use CelesTrak network access for fresh GP/OMM elements and
  must cache downloaded data in `.orbiter_cache/`.
- The main local app entry point is `venv\Scripts\python.exe third.py`, which serves
  `orbiter_web.html` over localhost so ES modules and assets load correctly.
- Keep the first viewport focused on the actual Earth/satellite visualization, not a landing page.
- The Earth home view must be above Moscow: use latitude `55.7558 deg N`,
  longitude `37.6173 deg E`, and document that the current Earth is a static spherical
  visual reference in the geocentric inertial frame.
- Design new trajectory/satellite features around data models that can grow from one
  propagated object to multiple named satellites and externally supplied trajectories.
- Keep real-time synchronization as an explicit mode: distinguish simulation elapsed
  time from wall-clock UTC and never imply real-time TLE/GP/OMM accuracy without SGP4
  propagation and a checked element epoch.

## MCP/tool usage

- Use `tool_search` first when a deferred MCP may be needed; the current workspace can
  expose Serena, Context7, Playwright, Chrome DevTools, mcp-omnisearch, code-index,
  OpenAI developer docs, sequential-thinking, and shadcn tools.
- Use Serena as the primary code-navigation/editing MCP before non-trivial code edits:
  activate `orbiter`, inspect symbols or references, then edit with the narrowest
  practical change.
- Use code-index only as a secondary code lookup/index refresh tool when Serena or `rg`
  is insufficient or stale.
- Use Brainstorm for engineering problem solving and for choosing an optimal solution
  when there is a meaningful trade-off, such as propagation architecture, numerical
  method selection, real-time synchronization design, performance optimization, data
  model boundaries, or browser rendering strategy. Prefer `brainstorm_quick` for fast
  second opinions and `brainstorm` multi-round debate for high-impact architecture
  decisions; use `brainstorm_review` for substantial diffs before merging.
- Do not use Brainstorm for tiny mechanical edits, formatting-only changes, or tasks
  where the correct local pattern is already obvious from the codebase.
- Use Context7 for current library/API documentation. In this project that includes
  Three.js/OrbitControls, NumPy, pytest, ruff, and any future astrodynamics stack such
  as astropy, skyfield, sgp4, scipy, tudatpy, spiceypy, and orekit.
- Use Playwright for browser-level verification of `orbiter_web.html`: desktop/mobile
  viewport checks, screenshots, accessibility snapshots, console errors, and network
  requests after starting the local server.
- Use Chrome DevTools MCP when deeper browser debugging is needed: console details,
  network traces, Lighthouse/accessibility checks, performance traces, or element/page
  screenshots.
- Use mcp-omnisearch only for external/current facts, standards, satellite/TLE sources,
  or primary-source research that is not already in local files or Context7 docs.
- Use OpenAI developer docs MCP only if the app gains OpenAI API features; prefer the
  official OpenAI spec/docs over general web search.
- Use sequential-thinking for multi-step architecture decisions or ambiguous
  propagation/visualization design work; keep routine edits direct.
- Use shadcn only if the UI is migrated to a component stack that actually uses it; the
  current app is plain HTML/CSS/Three.js.
- Do not commit MCP/tool artifacts: `.serena/`, `.playwright-mcp/`, screenshots, traces,
  local caches, logs, `__pycache__/`, or IDE state. Keep these ignored or write them to
  a temp location.

## Dynamics and verification

- Always state the frame, time scale, units, and force model.
- Never mix km/m, degrees/radians, or UTC/TT/TDB silently.
- For TLE/GP/OMM propagation, use SGP4/Skyfield and check the element epoch.
- For numerical propagation, start with a two-body test and validate energy/angular momentum conservation.
- Add pytest tests for propagators, coordinate transforms, and unit conversions.
- Run ruff and pytest before finishing.
