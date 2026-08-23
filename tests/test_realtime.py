from __future__ import annotations

import json
from datetime import timedelta, timezone
from urllib.error import URLError
from urllib.request import Request

import numpy as np
import pytest

from orbiter.dynamics import R_EARTH
from orbiter.realtime import (
    SGP4_FORCE_MODEL,
    celestrak_gp_url,
    load_celestrak_omm_json,
    parse_omm_json,
    parse_utc,
    propagate_omm_element,
    sample_realtime_trajectory,
    select_omm_element,
    trajectory_to_json,
)

SAMPLE_OMM = [
    {
        "OBJECT_NAME": "ISS (ZARYA)",
        "OBJECT_ID": "1998-067A",
        "EPOCH": "2024-05-06T19:53:04.999776",
        "MEAN_MOTION": "15.50957674",
        "ECCENTRICITY": ".000358",
        "INCLINATION": "51.6393",
        "RA_OF_ASC_NODE": "160.4574",
        "ARG_OF_PERICENTER": "140.6673",
        "MEAN_ANOMALY": "205.7250",
        "EPHEMERIS_TYPE": "0",
        "CLASSIFICATION_TYPE": "U",
        "NORAD_CAT_ID": "25544",
        "ELEMENT_SET_NO": "999",
        "REV_AT_EPOCH": "45212",
        "BSTAR": ".2731E-3",
        "MEAN_MOTION_DOT": ".15698E-3",
        "MEAN_MOTION_DDOT": "0",
    },
    {
        "OBJECT_NAME": "TEST SAT",
        "OBJECT_ID": "2024-001A",
        "EPOCH": "2024-05-06T19:53:04.999776",
        "MEAN_MOTION": "14.10000000",
        "ECCENTRICITY": ".001",
        "INCLINATION": "60.0",
        "RA_OF_ASC_NODE": "10.0",
        "ARG_OF_PERICENTER": "20.0",
        "MEAN_ANOMALY": "30.0",
        "EPHEMERIS_TYPE": "0",
        "CLASSIFICATION_TYPE": "U",
        "NORAD_CAT_ID": "99999",
        "ELEMENT_SET_NO": "999",
        "REV_AT_EPOCH": "1",
        "BSTAR": "0",
        "MEAN_MOTION_DOT": "0",
        "MEAN_MOTION_DDOT": "0",
    },
]


class FakeResponse:
    status = 200

    def __init__(self, payload: str) -> None:
        self.payload = payload.encode("utf-8")
        self.closed = False

    def read(self) -> bytes:
        return self.payload

    def close(self) -> None:
        self.closed = True


def test_celestrak_url_requests_group_json() -> None:
    url = celestrak_gp_url("GROUP", "stations", "json")

    assert url == "https://celestrak.org/NORAD/elements/gp.php?GROUP=STATIONS&FORMAT=JSON"


def test_celestrak_url_requests_catnr_json() -> None:
    url = celestrak_gp_url("CATNR", "59371", "json")

    assert url == "https://celestrak.org/NORAD/elements/gp.php?CATNR=59371&FORMAT=JSON"


def request_url(request: Request) -> str:
    return request.full_url


def test_load_celestrak_omm_json_uses_cache_without_network(tmp_path) -> None:
    payload = json.dumps(SAMPLE_OMM)
    cache_path = tmp_path / "stations.json"
    calls = []

    def opener(request: Request) -> FakeResponse:
        calls.append(request_url(request))
        return FakeResponse(payload)

    first = load_celestrak_omm_json(
        cache_path=cache_path,
        now_utc=parse_utc("2024-05-06T20:00:00+00:00"),
        opener=opener,
    )
    second = load_celestrak_omm_json(
        cache_path=cache_path,
        cache_ttl=timedelta(days=1),
        now_utc=parse_utc("2024-05-06T20:05:00+00:00"),
        opener=lambda _url: pytest.fail("cache should avoid a network request"),
    )

    assert len(calls) == 1
    assert calls[0].endswith("GROUP=STATIONS&FORMAT=JSON")
    assert first[0].name == "ISS (ZARYA)"
    assert second[0].norad_cat_id == "25544"


def test_load_celestrak_omm_json_falls_back_to_stale_cache_on_network_error(tmp_path) -> None:
    cache_path = tmp_path / "stations.json"
    cache_path.write_text(json.dumps(SAMPLE_OMM), encoding="utf-8")

    def offline_opener(_request: Request) -> FakeResponse:
        raise URLError("offline")

    elements = load_celestrak_omm_json(
        cache_path=cache_path,
        cache_ttl=timedelta(seconds=0),
        now_utc=parse_utc("2024-05-06T22:00:00+00:00"),
        opener=offline_opener,
    )

    assert elements[0].name == "ISS (ZARYA)"
    assert elements[0].source == str(cache_path)


def test_parse_and_select_omm_element() -> None:
    elements = parse_omm_json(json.dumps(SAMPLE_OMM), source="sample")

    by_number = select_omm_element(elements, "25544")
    by_name = select_omm_element(elements, "zarya")

    assert by_number is not None
    assert by_number.name == "ISS (ZARYA)"
    assert by_name is by_number
    assert elements[0].epoch_utc.tzinfo is timezone.utc
    assert elements[0].fields["CENTER_NAME"] == "EARTH"
    assert elements[0].fields["REF_FRAME"] == "TEME"
    assert elements[0].fields["TIME_SYSTEM"] == "UTC"
    assert elements[0].fields["MEAN_ELEMENT_THEORY"] == "SGP4"


def test_propagate_omm_element_returns_realtime_metadata() -> None:
    element = parse_omm_json(json.dumps(SAMPLE_OMM))[0]
    when = parse_utc("2024-05-06T19:53:04.999776+00:00")

    state = propagate_omm_element(element, when, max_epoch_age_days=None)

    assert state.name == "ISS (ZARYA)"
    assert state.norad_cat_id == "25544"
    assert state.force_model == SGP4_FORCE_MODEL
    assert "UTC" in state.time_scale
    assert "km/s" in state.units
    assert np.linalg.norm(state.gcrs_position_km) > R_EARTH
    assert np.linalg.norm(state.gcrs_velocity_km_s) > 7.0
    assert -90.0 <= state.latitude_deg <= 90.0
    assert -180.0 <= state.longitude_deg <= 180.0
    np.testing.assert_allclose(
        np.linalg.norm(state.visual_position_km),
        R_EARTH + state.altitude_km,
        rtol=1e-12,
    )


def test_sample_realtime_trajectory_counts_positive_steps() -> None:
    element = parse_omm_json(json.dumps(SAMPLE_OMM))[0]
    center = parse_utc("2024-05-06T20:00:00+00:00")

    samples = sample_realtime_trajectory(
        element,
        center_utc=center,
        duration_min=2.0,
        step_seconds=30.0,
        max_epoch_age_days=None,
    )

    assert len(samples) == 5
    assert samples[0].sample_utc < center < samples[-1].sample_utc


def test_trajectory_json_includes_omm_element_parameters() -> None:
    element = parse_omm_json(json.dumps(SAMPLE_OMM))[0]
    samples = sample_realtime_trajectory(
        element,
        center_utc=parse_utc("2024-05-06T20:00:00+00:00"),
        duration_min=1.0,
        step_seconds=60.0,
        max_epoch_age_days=None,
    )

    payload = trajectory_to_json(element, samples)
    parameters = payload["element_parameters"]
    profile = payload["model_profile"]

    assert parameters["object_id"] == "1998-067A"
    assert parameters["classification_type"] == "U"
    assert parameters["ref_frame"] == "TEME"
    assert parameters["time_system"] == "UTC"
    assert parameters["mean_element_theory"] == "SGP4"
    assert parameters["inclination_deg"] == pytest.approx(51.6393)
    assert parameters["mean_motion_rev_per_day"] == pytest.approx(15.50957674)
    assert parameters["period_min"] == pytest.approx(1440.0 / 15.50957674)
    assert parameters["units"]["angles"] == "degrees"
    assert profile["input_frame"] == "TEME"
    assert profile["input_time_system"] == "UTC"
    assert profile["mean_element_theory"] == "SGP4"


def test_trajectory_json_adds_versioned_coordinate_sets_without_removing_legacy() -> None:
    element = parse_omm_json(json.dumps(SAMPLE_OMM), source="sample-cache.json")[0]
    samples = sample_realtime_trajectory(
        element,
        center_utc=parse_utc("2024-05-06T20:00:00+00:00"),
        duration_min=1.0,
        step_seconds=60.0,
        max_epoch_age_days=None,
    )

    payload = trajectory_to_json(element, samples)
    trajectory = payload["trajectory"]
    first_contract_sample = trajectory["samples"][0]
    first_state = samples[0]

    assert trajectory["schema_version"] == 1
    assert trajectory["id"] == "norad:25544"
    assert trajectory["kind"] == "sgp4"
    assert trajectory["time"]["scale"] == "UTC"
    assert trajectory["coordinate_sets"]["orbit"] == {
        "frame": "GCRS",
        "position_unit": "km",
        "velocity_unit": "km/s",
    }
    assert first_contract_sample["time_utc"] == first_state.sample_utc.isoformat()
    assert first_contract_sample["orbit"]["position_km"] == list(
        first_state.gcrs_position_km
    )
    assert first_contract_sample["orbit"]["velocity_km_s"] == list(
        first_state.gcrs_velocity_km_s
    )
    assert first_contract_sample["ground_track"]["visual_position_km"] == list(
        first_state.visual_position_km
    )
    assert (
        first_contract_sample["ground_track"]["latitude_deg"]
        == first_state.latitude_deg
    )
    assert first_contract_sample["quality"]["epoch_is_stale"] is False

    assert {
        "source",
        "fetched_at_utc",
        "satellite",
        "model_profile",
        "element_parameters",
        "metadata",
        "samples",
    } <= payload.keys()
    assert payload["samples"][0]["gcrs_position_km"] == first_state.gcrs_position_km
    assert payload["samples"][0]["visual_position_km"] == first_state.visual_position_km
