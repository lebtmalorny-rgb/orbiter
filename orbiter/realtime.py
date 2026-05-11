from __future__ import annotations

import json
import math
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from skyfield.api import EarthSatellite, load, wgs84

from .dynamics import R_EARTH, geodetic_surface_point

CELESTRAK_GP_URL = "https://celestrak.org/NORAD/elements/gp.php"
DEFAULT_CELESTRAK_GROUP = "STATIONS"
DEFAULT_CACHE_TTL = timedelta(hours=2)
DEFAULT_MAX_EPOCH_AGE_DAYS = 14.0
DEFAULT_TRAJECTORY_DURATION_MIN = 180.0
DEFAULT_TRAJECTORY_STEP_SECONDS = 20.0
MAX_TRAJECTORY_SAMPLES = 20_000
DEFAULT_NETWORK_TIMEOUT_SECONDS = 20.0
DEFAULT_USER_AGENT = "orbiter/0.1 local-visualizer; cache=2h"
CELESTRAK_OMM_DEFAULTS = {
    "CENTER_NAME": "EARTH",
    "REF_FRAME": "TEME",
    "TIME_SYSTEM": "UTC",
    "MEAN_ELEMENT_THEORY": "SGP4",
}
REQUIRED_OMM_FIELDS = (
    "EPOCH",
    "MEAN_MOTION",
    "ECCENTRICITY",
    "INCLINATION",
    "RA_OF_ASC_NODE",
    "ARG_OF_PERICENTER",
    "MEAN_ANOMALY",
    "NORAD_CAT_ID",
)

SGP4_REFERENCE_FRAME = (
    "Input GP/OMM mean elements use the CelesTrak/Space-Track SGP4 convention "
    "(TEME, UTC, Earth-centered); Skyfield propagates them with SGP4 and exposes "
    "GCRS position plus WGS84-derived geodetic coordinates for visualization."
)
SGP4_TIME_SCALE = "UTC wall-clock time."
SGP4_UNITS = (
    "GCRS position and visual position: km; velocity: km/s; geodetic latitude/longitude: degrees."
)
SGP4_FORCE_MODEL = "SGP4 general perturbations from GP/OMM mean elements."

UrlOpen = Callable[[Request], object]


@dataclass(frozen=True)
class OmmElementSet:
    """A CelesTrak/Space-Track OMM element set for SGP4 propagation."""

    name: str
    norad_cat_id: str
    epoch_utc: datetime
    fields: dict[str, object]
    source: str
    fetched_at_utc: datetime | None = None


@dataclass(frozen=True)
class RealtimeSatelliteState:
    """One UTC-synchronized SGP4 state for rendering and metadata display."""

    name: str
    norad_cat_id: str
    sample_utc: datetime
    epoch_utc: datetime
    epoch_age_days: float
    epoch_is_stale: bool
    gcrs_position_km: tuple[float, float, float]
    gcrs_velocity_km_s: tuple[float, float, float]
    visual_position_km: tuple[float, float, float]
    latitude_deg: float
    longitude_deg: float
    altitude_km: float
    frame: str = SGP4_REFERENCE_FRAME
    time_scale: str = SGP4_TIME_SCALE
    units: str = SGP4_UNITS
    force_model: str = SGP4_FORCE_MODEL


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def ensure_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def parse_utc(value: object) -> datetime:
    text = str(value).strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    parsed = datetime.fromisoformat(text)
    return ensure_utc(parsed)


def celestrak_gp_url(
    query: str = "GROUP",
    value: str = DEFAULT_CELESTRAK_GROUP,
    data_format: str = "JSON",
) -> str:
    query_key = query.upper()
    params = {
        query_key: value.upper() if query_key == "GROUP" else value,
        "FORMAT": data_format.upper(),
    }
    return f"{CELESTRAK_GP_URL}?{urlencode(params)}"


def default_cache_path(
    query: str = "GROUP",
    value: str = DEFAULT_CELESTRAK_GROUP,
    data_format: str = "JSON",
    cache_dir: Path | str = ".orbiter_cache",
) -> Path:
    safe_value = "".join(char if char.isalnum() else "_" for char in value.upper()).strip("_")
    safe_format = data_format.lower().replace("-", "_")
    return Path(cache_dir) / f"celestrak_{query.lower()}_{safe_value}.{safe_format}"


def open_celestrak_request(request: Request) -> object:
    return urlopen(request, timeout=DEFAULT_NETWORK_TIMEOUT_SECONDS)


def celestrak_request(url: str) -> Request:
    return Request(url, headers={"User-Agent": DEFAULT_USER_AGENT})


def load_celestrak_omm_json(
    query: str = "GROUP",
    value: str = DEFAULT_CELESTRAK_GROUP,
    *,
    cache_path: Path | str | None = None,
    cache_ttl: timedelta = DEFAULT_CACHE_TTL,
    now_utc: datetime | None = None,
    opener: UrlOpen = open_celestrak_request,
) -> list[OmmElementSet]:
    now = ensure_utc(now_utc or utc_now())
    path = Path(cache_path) if cache_path is not None else default_cache_path(query, value)
    cached_payload = None

    if path.exists():
        cached_payload = path.read_text(encoding="utf-8")
        modified = datetime.fromtimestamp(path.stat().st_mtime, timezone.utc)
        if now - modified <= cache_ttl:
            return parse_omm_json(cached_payload, source=str(path))

    url = celestrak_gp_url(query, value, "JSON")
    try:
        response = opener(celestrak_request(url))
        try:
            status = getattr(response, "status", 200)
            if status != 200:
                raise RuntimeError(f"CelesTrak returned HTTP {status} for {url}.")
            payload = response.read().decode("utf-8")
            if not payload.strip():
                raise RuntimeError(f"CelesTrak returned an empty GP payload for {url}.")
        finally:
            close = getattr(response, "close", None)
            if close:
                close()
    except (HTTPError, URLError, TimeoutError, RuntimeError):
        if cached_payload is not None:
            return parse_omm_json(cached_payload, source=str(path))
        raise

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(payload, encoding="utf-8")
    return parse_omm_json(payload, source=url, fetched_at_utc=now)


def parse_omm_json(
    text: str,
    *,
    source: str = "",
    fetched_at_utc: datetime | None = None,
) -> list[OmmElementSet]:
    data = json.loads(text)
    if not isinstance(data, list):
        raise ValueError("CelesTrak OMM JSON payload must be a list of element sets.")

    elements = []
    for fields in data:
        if not isinstance(fields, dict):
            raise ValueError("Each OMM element set must be a JSON object.")
        normalized_fields = {**CELESTRAK_OMM_DEFAULTS, **fields}
        missing_fields = [
            field for field in REQUIRED_OMM_FIELDS if normalized_fields.get(field) in (None, "")
        ]
        if missing_fields:
            raise ValueError(f"OMM element set is missing required fields: {missing_fields}.")
        name = str(
            normalized_fields.get("OBJECT_NAME") or normalized_fields.get("TLE_LINE0") or ""
        ).strip()
        norad_cat_id = str(normalized_fields.get("NORAD_CAT_ID") or "").strip()
        epoch = parse_utc(normalized_fields["EPOCH"])
        elements.append(
            OmmElementSet(
                name=name,
                norad_cat_id=norad_cat_id,
                epoch_utc=epoch,
                fields=dict(normalized_fields),
                source=source,
                fetched_at_utc=fetched_at_utc,
            )
        )
    return elements


def select_omm_element(elements: list[OmmElementSet], query: str) -> OmmElementSet | None:
    needle = query.strip().casefold()
    if not needle:
        return elements[0] if elements else None

    for element in elements:
        if element.norad_cat_id.casefold() == needle:
            return element

    for element in elements:
        if needle in element.name.casefold():
            return element

    return None


def propagate_omm_element(
    element: OmmElementSet,
    when_utc: datetime | None = None,
    *,
    max_epoch_age_days: float | None = DEFAULT_MAX_EPOCH_AGE_DAYS,
) -> RealtimeSatelliteState:
    when = ensure_utc(when_utc or utc_now())
    ts = load.timescale()
    satellite = EarthSatellite.from_omm(ts, element.fields)
    return _propagate_satellite(element, satellite, ts, when, max_epoch_age_days)


def _propagate_satellite(
    element: OmmElementSet,
    satellite: EarthSatellite,
    timescale: object,
    when: datetime,
    max_epoch_age_days: float | None,
) -> RealtimeSatelliteState:
    t = timescale.from_datetime(when)
    geocentric = satellite.at(t)

    message = getattr(geocentric, "message", None)
    if message:
        raise RuntimeError(f"SGP4 propagation failed for {element.name}: {message}")

    epoch_age_days = float(t - satellite.epoch)
    epoch_is_stale = (
        max_epoch_age_days is not None and abs(epoch_age_days) > max_epoch_age_days
    )

    gcrs_position = tuple(float(value) for value in geocentric.position.km)
    gcrs_velocity = tuple(float(value) for value in geocentric.velocity.km_per_s)
    latitude, longitude = wgs84.latlon_of(geocentric)
    altitude_km = float(wgs84.height_of(geocentric).km)
    longitude_deg = ((float(longitude.degrees) + 180.0) % 360.0) - 180.0
    visual_position = geodetic_surface_point(
        latitude.degrees,
        longitude_deg,
        R_EARTH + altitude_km,
    )

    return RealtimeSatelliteState(
        name=element.name,
        norad_cat_id=element.norad_cat_id,
        sample_utc=when,
        epoch_utc=satellite.epoch.utc_datetime().astimezone(timezone.utc),
        epoch_age_days=epoch_age_days,
        epoch_is_stale=epoch_is_stale,
        gcrs_position_km=gcrs_position,
        gcrs_velocity_km_s=gcrs_velocity,
        visual_position_km=tuple(float(value) for value in visual_position),
        latitude_deg=float(latitude.degrees),
        longitude_deg=longitude_deg,
        altitude_km=altitude_km,
    )


def sample_realtime_trajectory(
    element: OmmElementSet,
    *,
    center_utc: datetime | None = None,
    duration_min: float = DEFAULT_TRAJECTORY_DURATION_MIN,
    step_seconds: float = DEFAULT_TRAJECTORY_STEP_SECONDS,
    max_epoch_age_days: float | None = DEFAULT_MAX_EPOCH_AGE_DAYS,
) -> list[RealtimeSatelliteState]:
    if duration_min <= 0:
        raise ValueError("Realtime trajectory duration must be positive minutes.")
    if step_seconds <= 0:
        raise ValueError("Realtime trajectory step must be positive seconds.")

    steps = math.ceil(duration_min * 60.0 / step_seconds)
    if steps + 1 > MAX_TRAJECTORY_SAMPLES:
        raise ValueError(
            f"Realtime trajectory has too many samples: {steps + 1}. "
            "Increase step_seconds or reduce duration_min."
        )

    center = ensure_utc(center_utc or utc_now())
    start = center - timedelta(minutes=duration_min / 2.0)
    ts = load.timescale()
    satellite = EarthSatellite.from_omm(ts, element.fields)
    return [
        _propagate_satellite(
            element,
            satellite,
            ts,
            start + timedelta(seconds=index * step_seconds),
            max_epoch_age_days,
        )
        for index in range(steps + 1)
    ]


def state_to_json(state: RealtimeSatelliteState) -> dict[str, object]:
    return {
        "name": state.name,
        "norad_cat_id": state.norad_cat_id,
        "sample_utc": state.sample_utc.isoformat(),
        "epoch_utc": state.epoch_utc.isoformat(),
        "epoch_age_days": state.epoch_age_days,
        "epoch_is_stale": state.epoch_is_stale,
        "gcrs_position_km": state.gcrs_position_km,
        "gcrs_velocity_km_s": state.gcrs_velocity_km_s,
        "visual_position_km": state.visual_position_km,
        "latitude_deg": state.latitude_deg,
        "longitude_deg": state.longitude_deg,
        "altitude_km": state.altitude_km,
        "frame": state.frame,
        "time_scale": state.time_scale,
        "units": state.units,
        "force_model": state.force_model,
    }


def _optional_float(fields: dict[str, object], key: str) -> float | None:
    value = fields.get(key)
    if value in (None, ""):
        return None
    return float(value)


def omm_element_parameters(element: OmmElementSet) -> dict[str, object]:
    """Compact OMM/NORAD table values that identify the propagated element set."""

    fields = element.fields
    mean_motion = _optional_float(fields, "MEAN_MOTION")
    return {
        "object_name": element.name,
        "object_id": str(fields.get("OBJECT_ID") or ""),
        "norad_cat_id": element.norad_cat_id,
        "epoch_utc": element.epoch_utc.isoformat(),
        "classification_type": str(fields.get("CLASSIFICATION_TYPE") or ""),
        "center_name": str(fields.get("CENTER_NAME") or ""),
        "ref_frame": str(fields.get("REF_FRAME") or ""),
        "time_system": str(fields.get("TIME_SYSTEM") or ""),
        "mean_element_theory": str(fields.get("MEAN_ELEMENT_THEORY") or ""),
        "ephemeris_type": str(fields.get("EPHEMERIS_TYPE") or ""),
        "element_set_no": str(fields.get("ELEMENT_SET_NO") or ""),
        "rev_at_epoch": str(fields.get("REV_AT_EPOCH") or ""),
        "mean_motion_rev_per_day": mean_motion,
        "period_min": (1440.0 / mean_motion) if mean_motion else None,
        "eccentricity": _optional_float(fields, "ECCENTRICITY"),
        "inclination_deg": _optional_float(fields, "INCLINATION"),
        "raan_deg": _optional_float(fields, "RA_OF_ASC_NODE"),
        "arg_perigee_deg": _optional_float(fields, "ARG_OF_PERICENTER"),
        "mean_anomaly_deg": _optional_float(fields, "MEAN_ANOMALY"),
        "bstar": _optional_float(fields, "BSTAR"),
        "mean_motion_dot_rev_per_day2": _optional_float(fields, "MEAN_MOTION_DOT"),
        "mean_motion_ddot_rev_per_day3": _optional_float(fields, "MEAN_MOTION_DDOT"),
        "units": {
            "mean_motion": "revolutions/day",
            "period": "minutes",
            "angles": "degrees",
            "bstar": "1 / Earth radii",
        },
    }


def trajectory_model_profile(element: OmmElementSet) -> dict[str, object]:
    fields = element.fields
    return {
        "standard": "CCSDS OMM-compatible GP data for SGP4 propagation.",
        "source_format": "CelesTrak GP JSON with OMM field names.",
        "input_center": str(fields.get("CENTER_NAME") or "EARTH"),
        "input_frame": str(fields.get("REF_FRAME") or "TEME"),
        "input_time_system": str(fields.get("TIME_SYSTEM") or "UTC"),
        "mean_element_theory": str(fields.get("MEAN_ELEMENT_THEORY") or "SGP4"),
        "propagator": "Skyfield EarthSatellite.from_omm / SGP4.",
        "output_frame": (
            "GCRS position and velocity; WGS84-derived latitude, longitude, and height; "
            "static spherical Earth visual reference."
        ),
        "units": SGP4_UNITS,
        "epoch_policy": (
            f"Element epoch is flagged stale when |sample UTC - epoch| exceeds "
            f"{DEFAULT_MAX_EPOCH_AGE_DAYS:g} days."
        ),
    }


def trajectory_to_json(
    element: OmmElementSet,
    samples: list[RealtimeSatelliteState],
) -> dict[str, object]:
    return {
        "source": element.source,
        "fetched_at_utc": element.fetched_at_utc.isoformat() if element.fetched_at_utc else None,
        "satellite": {
            "name": element.name,
            "norad_cat_id": element.norad_cat_id,
            "epoch_utc": element.epoch_utc.isoformat(),
        },
        "model_profile": trajectory_model_profile(element),
        "element_parameters": omm_element_parameters(element),
        "metadata": {
            "frame": SGP4_REFERENCE_FRAME,
            "time_scale": SGP4_TIME_SCALE,
            "units": SGP4_UNITS,
            "force_model": SGP4_FORCE_MODEL,
        },
        "samples": [state_to_json(sample) for sample in samples],
    }


def catalog_summary(elements: list[OmmElementSet]) -> list[dict[str, object]]:
    return [
        {
            "name": element.name,
            "norad_cat_id": element.norad_cat_id,
            "epoch_utc": element.epoch_utc.isoformat(),
            "source": element.source,
        }
        for element in elements
    ]


def api_error_payload(error: Exception) -> dict[str, object]:
    return {"error": type(error).__name__, "message": str(error)}
