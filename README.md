# Orbiter

Interactive local satellite orbit visualizer.

The project goal is a locally launched app for exploring satellite motion around Earth
with convenient 3D navigation. It currently propagates one configured satellite, and the
code should stay ready for future named satellites, imported trajectories, and an explicit
real-time mode synchronized to wall-clock time.

## Run

```powershell
venv\Scripts\python.exe third.py
```

The browser app is `orbiter_web.html`; `third.py` serves it locally so ES modules and
assets load correctly.

The server binds to `127.0.0.1` and chooses a free port in the local range starting at
`8765`.

For automated checks or manual browser opening:

```powershell
venv\Scripts\python.exe third.py --no-browser --port 8770
```

## Model

- Frame: geocentric inertial Cartesian frame, axes `X/Y/Z`.
- Time scale: relative simulation time from `t = 0`; UTC, TT, and TDB are not used.
- Units: position in km, velocity in km/s, time step in seconds, duration in minutes,
  orbital angles in degrees.
- Force model: selectable two-body point-mass Earth or two-body + Earth J2. There is
  no atmosphere, thrust, third bodies, Earth rotation, TLE, or SGP4.
- Earth home view: above Moscow, latitude `55.7558 deg N`, longitude `37.6173 deg E`.
  In the current model this is a static spherical Earth visual reference, not an
  Earth-rotation or UTC-ground-track solution.

The Python reference implementation lives in `orbiter/dynamics.py`. The browser
visualizer mirrors the same equations in JavaScript for client-side interaction.

## Roadmap Notes

- Multiple satellites: add named state/trajectory records instead of hard-coding one
  active satellite.
- Imported trajectories: keep frame, time scale, units, and force model metadata beside
  every trajectory.
- Real-time display: add a separate wall-clock synchronized mode only after introducing
  UTC-aware propagation, TLE epoch validation, and SGP4/Skyfield for TLE objects.

## Checks

```powershell
venv\Scripts\python.exe -m ruff check .
venv\Scripts\python.exe -m pytest
```
