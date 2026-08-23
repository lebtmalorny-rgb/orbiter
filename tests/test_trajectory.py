from __future__ import annotations

import re
from copy import deepcopy

import pytest

from orbiter.trajectory import (
    TRAJECTORY_SCHEMA_VERSION,
    TrajectoryContractError,
    build_trajectory_contract,
    validate_trajectory_contract,
)


def valid_contract_kwargs() -> dict[str, object]:
    return {
        "trajectory_id": "norad:25544",
        "name": "ISS (ZARYA)",
        "kind": "sgp4",
        "source": "sample-cache.json",
        "time": {
            "scale": "UTC",
            "sample_field": "time_utc",
            "start_utc": "2026-08-21T12:00:00+00:00",
            "end_utc": "2026-08-21T12:01:00+00:00",
        },
        "model": {
            "force_model": "SGP4 general perturbations from GP/OMM mean elements.",
            "element_epoch_utc": "2026-08-21T06:00:00+00:00",
        },
        "coordinate_sets": {
            "orbit": {
                "frame": "GCRS",
                "position_unit": "km",
                "velocity_unit": "km/s",
            },
            "ground_track": {
                "frame": "WGS84 geodetic projected onto the static spherical Earth",
                "angle_unit": "degrees",
                "altitude_unit": "km",
                "visual_position_unit": "km",
            },
        },
        "samples": [
            {
                "time_utc": "2026-08-21T12:00:00+00:00",
                "orbit": {
                    "position_km": [6800.0, 0.0, 0.0],
                    "velocity_km_s": [0.0, 7.6, 0.1],
                },
                "ground_track": {
                    "latitude_deg": 0.0,
                    "longitude_deg": 10.0,
                    "altitude_km": 420.0,
                    "visual_position_km": [6686.8, 1179.2, 0.0],
                },
                "quality": {"epoch_age_days": 0.25, "epoch_is_stale": False},
            },
            {
                "time_utc": "2026-08-21T12:01:00+00:00",
                "orbit": {
                    "position_km": [6785.0, 455.0, 6.0],
                    "velocity_km_s": [-0.5, 7.58, 0.1],
                },
                "ground_track": {
                    "latitude_deg": 2.0,
                    "longitude_deg": 13.0,
                    "altitude_km": 421.0,
                    "visual_position_km": [6615.0, 1527.0, 237.0],
                },
                "quality": {"epoch_age_days": 0.251, "epoch_is_stale": False},
            },
        ],
    }


def build_valid_contract() -> dict[str, object]:
    return build_trajectory_contract(**valid_contract_kwargs())


def test_build_trajectory_contract_adds_version_without_mutating_inputs() -> None:
    kwargs = valid_contract_kwargs()
    original = deepcopy(kwargs)

    contract = build_trajectory_contract(**kwargs)

    assert contract["schema_version"] == TRAJECTORY_SCHEMA_VERSION == 1
    assert contract["id"] == "norad:25544"
    assert contract["coordinate_sets"]["orbit"]["frame"] == "GCRS"
    assert kwargs == original
    assert contract["samples"] is not kwargs["samples"]


def test_validate_trajectory_contract_accepts_model_elapsed_time() -> None:
    kwargs = valid_contract_kwargs()
    kwargs["kind"] = "numerical"
    kwargs["time"] = {"scale": "MODEL_ELAPSED", "sample_field": "t_seconds"}
    kwargs["model"] = {"force_model": "two-body Earth point mass"}
    kwargs["coordinate_sets"] = {"orbit": kwargs["coordinate_sets"]["orbit"]}
    kwargs["samples"] = [
        {"t_seconds": 0.0, "orbit": kwargs["samples"][0]["orbit"]},
        {"t_seconds": 10.0, "orbit": kwargs["samples"][1]["orbit"]},
    ]

    contract = build_trajectory_contract(**kwargs)

    assert contract["time"] == {
        "scale": "MODEL_ELAPSED",
        "sample_field": "t_seconds",
    }


def set_path(container: object, path: tuple[object, ...], value: object) -> None:
    target = container
    for part in path[:-1]:
        target = target[part]
    target[path[-1]] = value


@pytest.mark.parametrize(
    ("path", "value", "error_path"),
    [
        (("kind",), "unknown", "kind"),
        (("source",), "", "source"),
        (
            ("coordinate_sets", "orbit", "frame"),
            "",
            "coordinate_sets.orbit.frame",
        ),
        (
            ("samples", 0, "orbit", "position_km"),
            [1.0, 2.0],
            "samples[0].orbit.position_km",
        ),
        (
            ("samples", 0, "orbit", "velocity_km_s", 1),
            float("inf"),
            "samples[0].orbit.velocity_km_s",
        ),
        (
            ("samples", 0, "ground_track", "latitude_deg"),
            91.0,
            "samples[0].ground_track.latitude_deg",
        ),
        (
            ("samples", 0, "ground_track", "longitude_deg"),
            181.0,
            "samples[0].ground_track.longitude_deg",
        ),
    ],
)
def test_contract_reports_invalid_field_path(
    path: tuple[object, ...], value: object, error_path: str
) -> None:
    kwargs = valid_contract_kwargs()
    set_path(kwargs, path, value)

    with pytest.raises(TrajectoryContractError, match=re.escape(error_path)):
        build_trajectory_contract(**kwargs)


def test_contract_requires_strictly_increasing_utc_samples() -> None:
    kwargs = valid_contract_kwargs()
    kwargs["samples"][1]["time_utc"] = kwargs["samples"][0]["time_utc"]

    with pytest.raises(TrajectoryContractError, match=r"samples\[1\]\.time_utc"):
        build_trajectory_contract(**kwargs)


def test_contract_rejects_naive_utc_timestamp() -> None:
    kwargs = valid_contract_kwargs()
    kwargs["samples"][0]["time_utc"] = "2026-08-21T12:00:00"

    with pytest.raises(TrajectoryContractError, match=r"samples\[0\]\.time_utc"):
        build_trajectory_contract(**kwargs)


def test_contract_rejects_time_scale_and_sample_field_mismatch() -> None:
    kwargs = valid_contract_kwargs()
    kwargs["time"]["sample_field"] = "t_seconds"

    with pytest.raises(TrajectoryContractError, match="time.sample_field"):
        build_trajectory_contract(**kwargs)


def test_sgp4_contract_requires_element_epoch() -> None:
    kwargs = valid_contract_kwargs()
    del kwargs["model"]["element_epoch_utc"]

    with pytest.raises(TrajectoryContractError, match="model.element_epoch_utc"):
        build_trajectory_contract(**kwargs)


def test_sgp4_contract_requires_ground_track() -> None:
    kwargs = valid_contract_kwargs()
    del kwargs["coordinate_sets"]["ground_track"]

    with pytest.raises(
        TrajectoryContractError, match="coordinate_sets.ground_track"
    ):
        build_trajectory_contract(**kwargs)


def test_validate_rejects_changed_schema_version() -> None:
    contract = build_valid_contract()
    contract["schema_version"] = 2

    with pytest.raises(TrajectoryContractError, match="schema_version"):
        validate_trajectory_contract(contract)
