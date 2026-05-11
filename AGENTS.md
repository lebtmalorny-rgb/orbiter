# Project rules for satellite dynamics Python code

- Product goal: build a local satellite-motion visualization app with clear 3D navigation,
  local assets, and no required network access at runtime.
- The main local app entry point is `venv\Scripts\python.exe third.py`, which serves
  `orbiter_web.html` over localhost so ES modules and assets load correctly.
- Keep the first viewport focused on the actual Earth/satellite visualization, not a landing page.
- The Earth home view must be above Moscow: use latitude `55.7558 deg N`,
  longitude `37.6173 deg E`, and document that the current Earth is a static spherical
  visual reference in the geocentric inertial frame.
- Design new trajectory/satellite features around data models that can grow from one
  propagated object to multiple named satellites and externally supplied trajectories.
- Prepare future real-time synchronization as an explicit mode: distinguish simulation
  elapsed time from wall-clock UTC and never imply real-time TLE accuracy without SGP4
  propagation and a checked TLE epoch.
- Use Serena before large edits: activate current project, inspect symbols, then edit.
- Use Context7 for current documentation of astropy, skyfield, sgp4, scipy, tudatpy, spiceypy, orekit, and plotting libraries.
- Always state the frame, time scale, units, and force model.
- Never mix km/m, degrees/radians, or UTC/TT/TDB silently.
- For TLE propagation, use SGP4/Skyfield and check the TLE epoch.
- For numerical propagation, start with a two-body test and validate energy/angular momentum conservation.
- Add pytest tests for propagators, coordinate transforms, and unit conversions.
- Run ruff and pytest before finishing.
