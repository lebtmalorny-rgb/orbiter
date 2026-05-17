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
