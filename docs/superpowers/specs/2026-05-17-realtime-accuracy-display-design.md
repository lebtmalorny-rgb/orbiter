# Real-Time Accuracy And Orbit Display Design

Date: 2026-05-17

## Goal

Improve the current real-time satellite experience with a small corrective pass,
without a broad architecture rewrite. The app should make SGP4/UTC motion look
smoother, make orbit/trail rendering easier to read, and clearly explain why the
manual RK4 default orbit does not match a real-time CelesTrak/SGP4 satellite.

## Current Root Cause

The mismatch between the default/manual orbit and real-time orbit is expected.
They are not two versions of the same calculation:

- Manual/default mode uses approximate local presets and browser RK4.
- Real-time mode uses CelesTrak GP/OMM mean elements and Skyfield SGP4.
- Manual mode uses elapsed simulation time; real-time mode uses wall-clock UTC.
- Manual mode is drawn in the app's static geocentric visual frame; real-time
  mode currently draws `visual_position_km`, projected from WGS84
  latitude/longitude/height onto the app's static spherical Earth.

This design improves clarity and rendering quality without pretending that the
manual RK4 presets can reproduce SGP4 by changing `MU`, `J2`, or radius
constants.

## Scope

In scope:

- Keep `third.py`, `orbiter/realtime.py`, and `orbiter_web.html` as the main
  runtime structure.
- Keep Skyfield SGP4 as the source of truth for real-time mode.
- Smooth real-time animation by interpolating between UTC samples instead of
  snapping to the nearest sample.
- Improve orbit/trail rendering so the current motion direction and recent
  track are visually clearer.
- Update UI/README text so users understand the frame, time scale, units, and
  force model boundary.
- Add focused tests where Python API behavior or documented boundaries change.

Out of scope for this pass:

- Moving satellite descriptions and orbit presets into a new Python module.
- Replacing the static spherical Earth with full WGS84/ITRF rendering.
- Adding Astropy/Cesium/satellite.js or browser worker propagation.
- Making manual RK4 match SGP4 from mean elements.
- Downloading CelesTrak data more frequently than the existing cache policy.

## Architecture

Real-time propagation stays server-side:

1. Browser asks `third.py` for `/api/realtime/trajectory`.
2. `orbiter.realtime` loads CelesTrak GP/OMM JSON with the existing 2-hour cache.
3. Skyfield `EarthSatellite.from_omm` propagates samples using SGP4.
4. The API returns sample UTC, GCRS position/velocity, WGS84-derived
   latitude/longitude/height, `visual_position_km`, model metadata, and OMM
   element metadata.
5. Browser renders the returned trajectory and animates the current satellite
   position against wall-clock UTC.

The browser should treat real-time samples as a time series. It should compute a
continuous visual state for the current UTC by interpolating position and
velocity between neighboring samples. If the current UTC is outside the returned
window, it should clamp to the first or last sample and keep the existing stale
epoch warnings.

## UI And Rendering

Real-time animation:

- Replace nearest-sample frame selection with a real-time interpolation cursor.
- Keep `frameIndex` as the nearest sample index for panels that display OMM or
  sample metadata.
- Use interpolated position for the satellite mesh and radius vector.
- Use interpolated velocity magnitude for the HUD when available.

Orbit display:

- Keep the existing full orbit line.
- Keep the trail line but base its range on the real-time UTC cursor, not only
  on sample index snapping.
- Make the current/recent trail visually stronger than the full orbit line.
- Preserve the existing "always visible" depth mode.

Explanatory text:

- When real-time mode loads, the preset info and summary should state that the
  trajectory is SGP4/UTC from GP/OMM and is not comparable to the educational
  RK4 preset unless both are seeded from the same state and model assumptions.
- README should retain the boundary: local `R_EARTH`, `MU`, `J2`, and
  `J2_REFERENCE_RADIUS` describe the educational/static-sphere model and do not
  control Skyfield/SGP4.

## Error Handling

- If interpolation cannot find valid neighboring samples, fall back to the
  nearest valid sample instead of stopping animation.
- If samples are malformed, keep the current load error path.
- If current wall-clock UTC is outside the sampled window, clamp to the nearest
  endpoint and keep the trajectory visible.
- Do not change the CelesTrak network retry or persistent backoff behavior in
  this pass.

## Testing

Verification should include:

- `venv\Scripts\python.exe -m ruff check .`
- `venv\Scripts\python.exe -m pytest`
- Browser verification after starting `venv\Scripts\python.exe third.py
  --no-browser --port <free-port>`:
  - page loads without console errors;
  - Earth/WebGL scene is nonblank;
  - real-time trajectory renders;
  - real-time satellite motion is smooth between samples;
  - desktop and mobile layouts do not overlap.

If only browser JavaScript changes are made, pytest still runs to confirm the
Python reference and SGP4 API stayed stable.

## Acceptance Criteria

- Real-time satellite motion no longer jumps sample-to-sample during normal
  playback.
- The full orbit, recent trail, satellite marker, HUD, and NORAD panel remain
  consistent while real-time mode is playing.
- The app clearly distinguishes educational RK4/manual mode from real-time
  SGP4/UTC mode.
- Existing cache behavior, explicit `FORMAT=JSON`, and stale cache fallback are
  preserved.
- Ruff and pytest pass.
