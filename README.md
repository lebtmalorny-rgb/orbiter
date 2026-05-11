# Orbiter

Interactive satellite orbit visualizer.

## Run

```powershell
venv\Scripts\python.exe third.py
```

The browser app is `orbiter_web.html`; `third.py` serves it locally so ES modules and
assets load correctly.

## Model

- Frame: geocentric inertial Cartesian frame, axes `X/Y/Z`.
- Time scale: relative simulation time from `t = 0`; UTC, TT, and TDB are not used.
- Units: position in km, velocity in km/s, time step in seconds, duration in minutes,
  orbital angles in degrees.
- Force model: selectable two-body point-mass Earth or two-body + Earth J2. There is
  no atmosphere, thrust, third bodies, Earth rotation, TLE, or SGP4.

The Python reference implementation lives in `orbiter/dynamics.py`. The browser
visualizer mirrors the same equations in JavaScript for client-side interaction.

## Checks

```powershell
venv\Scripts\python.exe -m ruff check .
venv\Scripts\python.exe -m pytest
```
