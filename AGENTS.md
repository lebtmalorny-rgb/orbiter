# Project rules for satellite dynamics Python code

- Use Serena before large edits: activate current project, inspect symbols, then edit.
- Use Context7 for current documentation of astropy, skyfield, sgp4, scipy, tudatpy, spiceypy, orekit, and plotting libraries.
- Always state the frame, time scale, units, and force model.
- Never mix km/m, degrees/radians, or UTC/TT/TDB silently.
- For TLE propagation, use SGP4/Skyfield and check the TLE epoch.
- For numerical propagation, start with a two-body test and validate energy/angular momentum conservation.
- Add pytest tests for propagators, coordinate transforms, and unit conversions.
- Run ruff and pytest before finishing.