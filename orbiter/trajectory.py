from __future__ import annotations

import json
from copy import deepcopy
from datetime import datetime
from math import isfinite

TRAJECTORY_SCHEMA_VERSION = 1
SUPPORTED_TRAJECTORY_KINDS = frozenset({"sgp4", "numerical", "ephemeris"})
TIME_FIELDS = {"UTC": "time_utc", "MODEL_ELAPSED": "t_seconds"}


class TrajectoryContractError(ValueError):
    """Raised when a trajectory contract violates schema version 1."""


def _error(path: str, message: str) -> TrajectoryContractError:
    return TrajectoryContractError(f"{path}: {message}")


def _mapping(value: object, path: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise _error(path, "must be an object")
    return value


def _list(value: object, path: str) -> list[object]:
    if not isinstance(value, list):
        raise _error(path, "must be a list")
    return value


def _string(value: object, path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise _error(path, "must be a non-empty string")
    return value


def _finite_number(value: object, path: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise _error(path, "must be a finite number")
    result = float(value)
    if not isfinite(result):
        raise _error(path, "must be a finite number")
    return result


def _vector3(value: object, path: str) -> None:
    vector = _list(value, path)
    if len(vector) != 3:
        raise _error(path, "must contain exactly three finite numbers")
    for index, component in enumerate(vector):
        _finite_number(component, f"{path}[{index}]")


def _aware_datetime(value: object, path: str) -> datetime:
    timestamp = _string(value, path)
    normalized = f"{timestamp[:-1]}+00:00" if timestamp.endswith("Z") else timestamp
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise _error(path, "must be an ISO 8601 timestamp with a UTC offset") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise _error(path, "must include a UTC offset")
    return parsed


def _validated_time_field(contract: dict[str, object]) -> tuple[str, str]:
    time = _mapping(contract.get("time"), "time")
    scale = _string(time.get("scale"), "time.scale")
    if scale not in TIME_FIELDS:
        raise _error("time.scale", f"must be one of {sorted(TIME_FIELDS)}")
    sample_field = _string(time.get("sample_field"), "time.sample_field")
    expected_field = TIME_FIELDS[scale]
    if sample_field != expected_field:
        raise _error("time.sample_field", f"must be {expected_field!r} for {scale}")
    return scale, sample_field


def _validate_time(contract: dict[str, object]) -> None:
    scale, sample_field = _validated_time_field(contract)
    if scale != "UTC":
        return

    time = _mapping(contract.get("time"), "time")
    start = _aware_datetime(time.get("start_utc"), "time.start_utc")
    end = _aware_datetime(time.get("end_utc"), "time.end_utc")
    samples = _list(contract.get("samples"), "samples")
    if not samples:
        raise _error("samples", "must contain at least one sample")
    first = _mapping(samples[0], "samples[0]")
    last_index = len(samples) - 1
    last = _mapping(samples[last_index], f"samples[{last_index}]")
    first_time = _aware_datetime(first.get(sample_field), f"samples[0].{sample_field}")
    last_time = _aware_datetime(
        last.get(sample_field), f"samples[{last_index}].{sample_field}"
    )
    if start != first_time:
        raise _error("time.start_utc", "must equal the first sample timestamp")
    if end != last_time:
        raise _error("time.end_utc", "must equal the last sample timestamp")


def _validate_coordinate_sets(contract: dict[str, object]) -> None:
    coordinate_sets = _mapping(contract.get("coordinate_sets"), "coordinate_sets")
    orbit = _mapping(coordinate_sets.get("orbit"), "coordinate_sets.orbit")
    _string(orbit.get("frame"), "coordinate_sets.orbit.frame")
    _string(orbit.get("position_unit"), "coordinate_sets.orbit.position_unit")
    _string(orbit.get("velocity_unit"), "coordinate_sets.orbit.velocity_unit")

    if "ground_track" not in coordinate_sets:
        if contract.get("kind") == "sgp4":
            raise _error("coordinate_sets.ground_track", "is required for SGP4")
        return

    ground_track = _mapping(
        coordinate_sets["ground_track"], "coordinate_sets.ground_track"
    )
    _string(ground_track.get("frame"), "coordinate_sets.ground_track.frame")
    _string(ground_track.get("angle_unit"), "coordinate_sets.ground_track.angle_unit")
    _string(
        ground_track.get("altitude_unit"),
        "coordinate_sets.ground_track.altitude_unit",
    )
    _string(
        ground_track.get("visual_position_unit"),
        "coordinate_sets.ground_track.visual_position_unit",
    )


def _validate_ground_track(sample: dict[str, object], path: str) -> None:
    ground_track = _mapping(sample.get("ground_track"), f"{path}.ground_track")
    latitude_path = f"{path}.ground_track.latitude_deg"
    latitude = _finite_number(ground_track.get("latitude_deg"), latitude_path)
    if not -90.0 <= latitude <= 90.0:
        raise _error(latitude_path, "must be between -90 and 90 degrees")
    longitude_path = f"{path}.ground_track.longitude_deg"
    longitude = _finite_number(ground_track.get("longitude_deg"), longitude_path)
    if not -180.0 <= longitude <= 180.0:
        raise _error(longitude_path, "must be between -180 and 180 degrees")
    _finite_number(
        ground_track.get("altitude_km"), f"{path}.ground_track.altitude_km"
    )
    _vector3(
        ground_track.get("visual_position_km"),
        f"{path}.ground_track.visual_position_km",
    )


def _validate_samples(contract: dict[str, object]) -> None:
    scale, sample_field = _validated_time_field(contract)
    samples = _list(contract.get("samples"), "samples")
    if not samples:
        raise _error("samples", "must contain at least one sample")
    coordinate_sets = _mapping(contract.get("coordinate_sets"), "coordinate_sets")
    has_ground_track = "ground_track" in coordinate_sets
    previous_time: datetime | float | None = None

    for index, sample_value in enumerate(samples):
        path = f"samples[{index}]"
        sample = _mapping(sample_value, path)
        if scale == "UTC":
            sample_time: datetime | float = _aware_datetime(
                sample.get(sample_field), f"{path}.{sample_field}"
            )
        else:
            sample_time = _finite_number(
                sample.get(sample_field), f"{path}.{sample_field}"
            )
        if previous_time is not None and sample_time <= previous_time:
            raise _error(f"{path}.{sample_field}", "must be strictly increasing")
        previous_time = sample_time

        orbit = _mapping(sample.get("orbit"), f"{path}.orbit")
        _vector3(orbit.get("position_km"), f"{path}.orbit.position_km")
        _vector3(orbit.get("velocity_km_s"), f"{path}.orbit.velocity_km_s")
        if has_ground_track:
            _validate_ground_track(sample, path)


def build_trajectory_contract(
    *,
    trajectory_id: str,
    name: str,
    kind: str,
    source: str,
    time: dict[str, object],
    model: dict[str, object],
    coordinate_sets: dict[str, dict[str, object]],
    samples: list[dict[str, object]],
) -> dict[str, object]:
    contract = {
        "schema_version": TRAJECTORY_SCHEMA_VERSION,
        "id": trajectory_id,
        "name": name,
        "kind": kind,
        "source": source,
        "time": deepcopy(time),
        "model": deepcopy(model),
        "coordinate_sets": deepcopy(coordinate_sets),
        "samples": deepcopy(samples),
    }
    validate_trajectory_contract(contract)
    return contract


def validate_trajectory_contract(contract: dict[str, object]) -> None:
    contract = _mapping(contract, "contract")
    schema_version = contract.get("schema_version")
    if isinstance(schema_version, bool) or schema_version != TRAJECTORY_SCHEMA_VERSION:
        raise _error("schema_version", f"must equal {TRAJECTORY_SCHEMA_VERSION}")
    _string(contract.get("id"), "id")
    _string(contract.get("name"), "name")
    kind = _string(contract.get("kind"), "kind")
    if kind not in SUPPORTED_TRAJECTORY_KINDS:
        raise _error("kind", f"must be one of {sorted(SUPPORTED_TRAJECTORY_KINDS)}")
    _string(contract.get("source"), "source")

    model = _mapping(contract.get("model"), "model")
    _string(model.get("force_model"), "model.force_model")
    if kind == "sgp4":
        _aware_datetime(model.get("element_epoch_utc"), "model.element_epoch_utc")

    _validate_coordinate_sets(contract)
    _validate_samples(contract)
    _validate_time(contract)

    try:
        json.dumps(contract, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise TrajectoryContractError(
            "contract: value is not JSON-compatible"
        ) from exc
