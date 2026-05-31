from core.steel.beam import calculate_steel_beam
from app import app
from fastapi.testclient import TestClient
import pytest
from models.steel import (
    AutomaticFloorLoad,
    AutomaticLoadTakedown,
    AutomaticWallLoad,
    LineLoad,
    PointLoad,
    SteelBeamDesignOptions,
    SteelBeamGeometry,
    SteelBeamLoads,
    SteelBeamRequest,
)


client = TestClient(app)


def test_direct_steel_beam_result_has_core_effects():
    request = SteelBeamRequest(
        profile_name="IPE 160",
        geometry=SteelBeamGeometry(span_m=5.0, axis="major", deflection_limit_ratio=500),
        loads=SteelBeamLoads(mode="direct", direct_w_kN_m=5.0),
        design=SteelBeamDesignOptions(recommendation_limit=3),
    )

    result = calculate_steel_beam(request)

    assert result["success"] is True
    assert result["results"]["MEd"] > 0
    assert result["results"]["VEd"] > 0
    assert result["results"]["effects"]["MEd_kNm"] > 0
    assert result["results"]["effects"]["VEd_kN"] > 0
    assert result["results"]["resistance"]["MRd_kNm"] > 0
    assert len(result["results"]["recommendations"]) <= 3


def test_direct_steel_beam_result_includes_backend_plot_data():
    request = SteelBeamRequest(
        profile_name="IPE 160",
        geometry=SteelBeamGeometry(span_m=5.0, axis="major", deflection_limit_ratio=500),
        loads=SteelBeamLoads(
            mode="direct",
            direct_w_kN_m=5.0,
            point_loads=[PointLoad(P_kN=10.0, a_m=2.0, type="live")],
        ),
        design=SteelBeamDesignOptions(recommendation_limit=3),
    )

    result = calculate_steel_beam(request)
    plots = result["results"]["plots"]
    x = plots["x"]

    assert result["success"] is True
    assert isinstance(plots, dict)
    assert len(x) > 300
    assert len(plots["shear"]) == len(x)
    assert len(plots["moment"]) == len(x)
    assert len(plots["deflection"]) == len(x)
    assert plots["meta"]["x_unit"] == "m"
    assert plots["meta"]["shear_unit"] == "kN"
    assert plots["markers"]["max_shear"]["abs_value"] == pytest.approx(result["results"]["VEd"])
    assert plots["markers"]["max_moment"]["abs_value"] == pytest.approx(result["results"]["MEd"])
    assert plots["markers"]["max_deflection"]["abs_value"] == pytest.approx(result["results"]["delta"])


def test_combination_mode_uses_line_load_actions():
    request = SteelBeamRequest(
        profile_name="IPE 200",
        geometry=SteelBeamGeometry(span_m=4.0),
        loads=SteelBeamLoads(
            mode="comb",
            line_loads=[
                LineLoad(w_kN_m=2.0, type="G"),
                LineLoad(w_kN_m=3.0, type="live"),
            ],
            include_self_weight=True,
        ),
    )

    result = calculate_steel_beam(request)

    assert result["results"]["loads"]["w_ULS_kN_m"] > result["results"]["loads"]["w_SLS_kN_m"]
    assert result["results"]["reactions"]["dead"]["RA_kN"] > 0
    assert "ULS lead live" in result["results"]["governing_combination"]


def test_automatic_floor_and_wall_loads_are_calculated_backend_side():
    request = SteelBeamRequest(
        profile_name="IPE 240",
        geometry=SteelBeamGeometry(span_m=4.0),
        loads=SteelBeamLoads(
            mode="comb",
            line_loads=[],
            automatic=AutomaticLoadTakedown(
                enabled=True,
                include_wall=True,
                floor_rows=[
                    AutomaticFloorLoad(
                        slab_type="wood",
                        span_m=4.0,
                        accessible="accessible",
                        additional_dead_kN_m2=0.5,
                    )
                ],
                wall_rows=[
                    AutomaticWallLoad(
                        thickness_cm=14.0,
                        density_kN_m3=18.0,
                        height_m=3.0,
                        percent=100.0,
                    )
                ],
            ),
        ),
    )

    result = calculate_steel_beam(request)
    takedown = result["results"]["loads"]["automatic_takedown"]

    assert takedown["enabled"] is True
    assert takedown["floor_dead_kN_m"] == 3.0
    assert takedown["floor_live_kN_m"] == 4.0
    assert round(takedown["wall_kN_m"], 3) == 7.56
    assert result["results"]["auto_load_breakdown"]["auto_dead_load_kN_m"] == takedown["dead_kN_m"]
    assert result["results"]["auto_load_breakdown"]["auto_live_load_kN_m"] == takedown["live_kN_m"]
    assert result["results"]["floor_contribution_kN_m"] == 3.0
    assert round(result["results"]["wall_contribution_kN_m"], 3) == 7.56


def test_support_width_recommendations_use_three_part_backend_contract():
    request = SteelBeamRequest(
        profile_name="IPE 240",
        geometry=SteelBeamGeometry(span_m=4.0),
        loads=SteelBeamLoads(mode="direct", direct_w_kN_m=5.0),
        design=SteelBeamDesignOptions(support_width_cm=14.0, recommendation_limit=5),
    )

    result = calculate_steel_beam(request)
    recommendations = result["results"]["recommendations"]
    support_width_recommendations = result["results"]["support_width_recommendations"]

    assert result["success"] is True
    assert isinstance(recommendations, list)
    assert isinstance(support_width_recommendations, list)
    assert recommendations
    assert support_width_recommendations
    assert recommendations[0]["support_width_fit"]["remaining_gap_mm"] >= 0.0
    assert recommendations[0]["support_width_fit"]["remaining_gap_mm"] <= 30.0
    assert result["results"]["support_width_recommendation_status"]["state"] == "ok"


def test_independent_left_right_support_widths():
    request = SteelBeamRequest(
        profile_name="IPE 240",
        geometry=SteelBeamGeometry(span_m=4.0),
        loads=SteelBeamLoads(mode="direct", direct_w_kN_m=5.0),
        design=SteelBeamDesignOptions(
            left_support_width_cm=14.0,
            right_support_width_cm=19.0,
            recommendation_limit=5,
        ),
    )

    # Minimum support width governs the bearing-sensitive recommendation engine.
    assert request.design.effective_support_width_cm == 14.0

    result = calculate_steel_beam(request)
    results = result["results"]
    left = results["support_bearing_left"]
    right = results["support_bearing_right"]

    # Each side reports its own width, and the slof lengths differ because the widths differ.
    assert left["width_cm"] == 14.0
    assert right["width_cm"] == 19.0
    assert left["length_cm"] != right["length_cm"]
    # Reinforcement is width-independent and identical on both sides (unchanged workflow).
    assert left["reinforcement_mid_cm2"] == right["reinforcement_mid_cm2"]
    assert left["reinforcement_head_cm2"] == right["reinforcement_head_cm2"]


def test_legacy_single_support_width_still_supported():
    # Backward compatibility: legacy support_width_cm populates both sides.
    request = SteelBeamRequest(
        profile_name="IPE 240",
        geometry=SteelBeamGeometry(span_m=4.0),
        loads=SteelBeamLoads(mode="direct", direct_w_kN_m=5.0),
        design=SteelBeamDesignOptions(support_width_cm=14.0, recommendation_limit=5),
    )

    assert request.design.left_width_cm == 14.0
    assert request.design.right_width_cm == 14.0
    assert request.design.effective_support_width_cm == 14.0

    result = calculate_steel_beam(request)
    results = result["results"]
    assert results["support_bearing_left"]["width_cm"] == 14.0
    assert results["support_bearing_right"]["width_cm"] == 14.0


def test_api_validation_errors_are_friendly_and_standardized():
    response = client.post(
        "/calculate/steel-beam",
        json={
            "profile_name": "IPE 160",
            "geometry": {"span_m": 5.0},
            "material": {"fy_MPa": -1.0, "E_GPa": 210.0, "gamma_M0": 1.0},
            "loads": {"mode": "direct", "direct_w_kN_m": 5.0},
            "design": {"recommendation_limit": 3},
        },
    )

    body = response.json()

    assert response.status_code == 422
    assert body == {
        "success": False,
        "results": {},
        "warnings": [],
        "errors": ["Steel yield strength must be greater than 0 MPa."],
    }


def test_unknown_profile_returns_friendly_engineering_error():
    response = client.post(
        "/calculate/steel-beam",
        json={
            "profile_name": "NOT A PROFILE",
            "geometry": {"span_m": 5.0},
            "loads": {"mode": "direct", "direct_w_kN_m": 5.0},
            "design": {"recommendation_limit": 3},
        },
    )

    body = response.json()

    assert response.status_code == 422
    assert body["success"] is False
    assert body["results"] == {}
    assert body["errors"] == ["Selected steel section is not available in the backend profile library."]


def test_steel_beam_report_endpoint_returns_downloadable_pdf():
    response = client.post(
        "/reports/steel-beam",
        json={
            "profile_name": "IPE 240",
            "geometry": {"span_m": 4.0},
            "loads": {"mode": "direct", "direct_w_kN_m": 5.0},
            "design": {"support_width_cm": 14.0, "recommendation_limit": 5},
        },
    )

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert "steel_beam_report_" in response.headers["content-disposition"]
    assert response.content.startswith(b"%PDF")
    assert len(response.content) > 1000
