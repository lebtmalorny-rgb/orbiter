# Realtime Orbit Panel UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Улучшить читаемость real-time сцены: один видимый виток, корректная глубина линий и скрываемая NORAD/OMM-панель.

**Architecture:** Серверные SGP4-данные не меняются. `orbiter_web.html` получает UI-переключатель и отдельную функцию расчета draw range для real-time линии, а тесты статически проверяют наличие ключевых регрессий.

**Tech Stack:** Plain HTML/CSS/JavaScript, Three.js `LineBasicMaterial`, Python pytest для статических UI-проверок, Playwright MCP для браузерной верификации.

---

### Task 1: UI Regression Tests

**Files:**
- Create: `tests/test_orbiter_web_ui.py`
- Read: `orbiter_web.html`

- [ ] **Step 1: Write failing tests**

```python
from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HTML = (ROOT / "orbiter_web.html").read_text(encoding="utf-8")


def test_realtime_orbit_draw_range_limits_visible_orbit_to_current_period() -> None:
    assert "function realtimeOrbitDrawRange()" in HTML
    assert "period_min" in HTML
    assert "orbitLine.geometry.setDrawRange(orbitRange.start, orbitRange.count)" in HTML
    assert "orbitLineVisible.geometry.setDrawRange(orbitRange.start, orbitRange.count)" in HTML


def test_orbit_lines_do_not_render_above_earth_by_default() -> None:
    assert '<input id="alwaysVisible" type="checkbox">' in HTML
    assert "orbitLine.material.depthTest = !alwaysVisible;" in HTML
    assert "orbitLine.material.opacity = alwaysVisible ? 0.12 : 0.22;" in HTML


def test_norad_scene_panel_can_be_hidden_without_hiding_hud() -> None:
    assert 'id="showNoradPanel"' in HTML
    assert "'showNoradPanel'" in HTML
    assert "if (!el.showNoradPanel.checked) {" in HTML
    assert "el.noradPanel.style.display = 'none';" in HTML
```

- [ ] **Step 2: Verify red**

Run: `venv\Scripts\python.exe -m pytest tests/test_orbiter_web_ui.py -q`

Expected: tests fail because `realtimeOrbitDrawRange()` and `showNoradPanel`
do not exist yet, and `alwaysVisible` is still checked by default.

### Task 2: Scene Rendering Fix

**Files:**
- Modify: `orbiter_web.html`

- [ ] **Step 1: Add UI state**

Add constants for real-time visible orbit fallback and a `showNoradPanel`
checkbox in the calculation fieldset.

- [ ] **Step 2: Limit real-time orbit draw range**

Add `realtimeOrbitDrawRange()` and `orbitDrawRange()` helpers. In
`updateTrail()`, apply draw ranges to both orbit lines and the yellow trail.

- [ ] **Step 3: Fix depth defaults**

Remove `checked` from `alwaysVisible`, update `updateDepthMode()` so the base
orbit line also uses depth testing when `Поверх Земли` is off, and leave the
explicit overlay behavior available when the user enables it.

- [ ] **Step 4: Make NORAD/OMM panel hideable**

Wire `showNoradPanel` to `updateNoradPanel()`. When the checkbox is off, hide
only `#noradPanel`; keep `#hud` unchanged.

- [ ] **Step 5: Verify green**

Run:

```powershell
venv\Scripts\python.exe -m pytest tests/test_orbiter_web_ui.py -q
venv\Scripts\python.exe -m ruff check .
venv\Scripts\python.exe -m pytest
```

Expected: all tests pass and ruff has no findings.

### Task 3: Browser Verification

**Files:**
- Read: `orbiter_web.html`

- [ ] Start `third.py` on a free localhost port.
- [ ] Open `/orbiter_web.html` in Playwright.
- [ ] Load SGP4/UTC for ISS.
- [ ] Verify the scene shows a single visible real-time orbit segment by default.
- [ ] Verify `Поверх Земли` can still be enabled.
- [ ] Verify `NORAD/OMM на сцене` hides and shows the panel without hiding HUD.
- [ ] Check console errors and desktop/mobile layout.

