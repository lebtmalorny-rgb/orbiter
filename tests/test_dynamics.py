from __future__ import annotations

import numpy as np

from orbiter.dynamics import (
    J2_MODEL,
    MU,
    ORBIT_PRESETS,
    R_EARTH,
    TWO_BODY_MODEL,
    SimulationConfig,
    acceleration,
    orbital_elements_to_state,
    rotation_x,
    rotation_z,
    simulate_orbit,
)


def test_circular_equatorial_elements_to_state() -> None:
    state = orbital_elements_to_state(
        semi_major_axis=7000.0,
        eccentricity=0.0,
        inclination_deg=0.0,
        raan_deg=0.0,
        arg_perigee_deg=0.0,
        true_anomaly_deg=0.0,
    )

    expected_speed = np.sqrt(MU / 7000.0)
    np.testing.assert_allclose(state[:3], [7000.0, 0.0, 0.0], atol=1e-12)
    np.testing.assert_allclose(state[3:], [0.0, expected_speed, 0.0], atol=1e-12)


def test_rotation_matrices_use_degrees() -> None:
    np.testing.assert_allclose(
        rotation_x(90.0) @ [0.0, 1.0, 0.0],
        [0.0, 0.0, 1.0],
        atol=1e-12,
    )
    np.testing.assert_allclose(
        rotation_z(90.0) @ [1.0, 0.0, 0.0],
        [0.0, 1.0, 0.0],
        atol=1e-12,
    )


def test_duration_minutes_and_step_seconds_define_time_grid() -> None:
    config = SimulationConfig(
        x0=7000.0,
        y0=0.0,
        z0=0.0,
        vx0=0.0,
        vy0=np.sqrt(MU / 7000.0),
        vz0=0.0,
        dt=10.0,
        duration_min=1.0,
    )

    history, times, stopped_by_collision = simulate_orbit(config)

    assert len(history) == 7
    assert times[-1] == 60.0
    assert not stopped_by_collision


def test_two_body_propagation_conserves_energy_and_angular_momentum() -> None:
    config = ORBIT_PRESETS["МКС"].to_config()
    history, _times, stopped_by_collision = simulate_orbit(config)

    radii = np.linalg.norm(history[:, :3], axis=1)
    speeds = np.linalg.norm(history[:, 3:], axis=1)
    energy = speeds**2 / 2.0 - MU / radii
    angular_momentum = np.linalg.norm(np.cross(history[:, :3], history[:, 3:]), axis=1)

    assert not stopped_by_collision
    assert np.min(radii) > R_EARTH
    assert (np.max(energy) - np.min(energy)) / abs(energy[0]) < 1e-11
    assert (np.max(angular_momentum) - np.min(angular_momentum)) / angular_momentum[0] < 1e-11


def test_j2_force_model_changes_acceleration_but_keeps_units() -> None:
    position = np.array([7000.0, 0.0, 1000.0])

    two_body = acceleration(position, TWO_BODY_MODEL)
    j2 = acceleration(position, J2_MODEL)

    assert two_body.shape == (3,)
    assert j2.shape == (3,)
    assert np.linalg.norm(j2 - two_body) > 1e-8
