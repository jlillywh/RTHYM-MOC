"""Unit coverage for ``long_pipeline_surge_utils`` helpers."""

from __future__ import annotations

import pytest

from long_pipeline_surge_utils import (
    DEFAULT_LENGTH_FT,
    SUMMIT_CHAINAGE_FT,
    default_survey,
    expected_grid_distortion_pct,
    survey_z_ft,
)

pytestmark = pytest.mark.dvcm


def test_default_survey_honors_custom_length_and_summit() -> None:
    survey = default_survey(
        length_ft=1000.0,
        summit_chainage_ft=400.0,
        summit_elevation_ft=320.0,
    )
    assert survey == [(0.0, 200.0), (400.0, 320.0), (1000.0, 150.0)]


def test_survey_z_ft_clamps_below_and_above_survey() -> None:
    survey = default_survey()
    assert survey_z_ft(-1.0, survey) == survey[0][1]
    assert survey_z_ft(DEFAULT_LENGTH_FT + 500.0, survey) == survey[-1][1]


def test_survey_z_ft_interpolates_at_summit_chainage() -> None:
    survey = default_survey()
    assert survey_z_ft(SUMMIT_CHAINAGE_FT, survey) == pytest.approx(450.0)


def test_survey_z_ft_fallback_when_no_segment_matches(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    survey = default_survey()

    def empty_zip(*_args, **_kwargs):
        return iter([])

    monkeypatch.setattr("builtins.zip", empty_zip)
    assert survey_z_ft(SUMMIT_CHAINAGE_FT, survey) == survey[-1][1]


def test_expected_grid_distortion_pct_matches_capped_grid() -> None:
    num_segments, distortion_pct = expected_grid_distortion_pct()
    assert num_segments == 2000
    assert distortion_pct > 0.0
