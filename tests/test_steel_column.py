from app import app
from core.steel.column import calculate_steel_column
from fastapi.testclient import TestClient
from models.steel import (
    SteelColumnDesignOptions,
    SteelColumnGeometry,
    SteelColumnLoadCase,
    SteelColumnLoads,
    SteelColumnRequest,
)


client = TestClient(app)


def test_direct_steel_column_result_has_core_checks():
    request = SteelColumnRequest(
        profile_name="K120/120/5",
        geometry=SteelColumnGeometry(
            length_m=4.0,
            buckling_length_y_m=4.0,
            buckling_length_z_m=4.0,
            ltb_length_m=4.0,
        ),
        loads=SteelColumnLoads(permanent=SteelColumnLoadCase(N_kN=100.0)),
        design=SteelColumnDesignOptions(recommendation_limit=5),
    )

    result = calculate_steel_column(request)

    assert result["success"] is True
    assert result["results"]["effects"]["NEd_kN"] > 0
    assert result["results"]["resistance"]["NcRd_kN"] > 0
    assert result["results"]["utilization_detail"]["compression"] > 0
    assert result["results"]["buckling"]["chi_y"] > 0
    assert result["results"]["buckling"]["buckling_curve_y"] in {"a", "c"}
    assert result["results"]["buckling"]["lambda_bar_y"] > 0
    assert result["results"]["resistance"]["NbRdy_kN"] > 0
    assert result["results"]["stability_summary"]["governing_axis"] in {"y", "z"}
    assert result["results"]["stability_summary"]["pass_fail"] in {"PASS", "FAIL"}
    assert result["results"]["section"]["classification"]["method"] == "assumed"
    assert isinstance(result["results"]["recommendations"], list)
    assert len(result["results"]["recommendations"]) <= 5


def test_steel_column_api_returns_standard_response():
    response = client.post(
        "/calculate/steel-column",
        json={
            "profile_name": "K120/120/5",
            "geometry": {
                "length_m": 4.0,
                "buckling_length_y_m": 4.0,
                "buckling_length_z_m": 4.0,
                "ltb_length_m": 4.0,
            },
            "loads": {
                "permanent": {"N_kN": 100.0},
                "include_self_weight": True,
            },
            "design": {"recommendation_limit": 5},
        },
    )

    body = response.json()

    assert response.status_code == 200
    assert body["success"] is True
    assert body["errors"] == []
    assert body["results"]["section"]["name"] == "K120/120/5"
    assert body["results"]["effects"]["NEd_kN"] > 0
    assert body["results"]["eurocode"]["standard"] == "EN 1993-1-1"
    assert body["results"]["stability_summary"]["NbRdy_kN"] > 0


def test_steel_column_validation_errors_are_friendly():
    response = client.post(
        "/calculate/steel-column",
        json={
            "profile_name": "K120/120/5",
            "geometry": {
                "length_m": 0.0,
                "buckling_length_y_m": 4.0,
                "buckling_length_z_m": 4.0,
            },
        },
    )

    body = response.json()

    assert response.status_code == 422
    assert body["success"] is False
    assert body["results"] == {}
    assert "Column length must be greater than zero." in body["errors"]


def test_steel_column_report_endpoint_returns_downloadable_pdf():
    response = client.post(
        "/reports/steel-column",
        json={
            "profile_name": "K120/120/5",
            "geometry": {
                "length_m": 4.0,
                "buckling_length_y_m": 4.0,
                "buckling_length_z_m": 4.0,
                "ltb_length_m": 4.0,
            },
            "loads": {
                "permanent": {"N_kN": 100.0},
                "include_self_weight": True,
            },
            "design": {"recommendation_limit": 5},
        },
    )

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert "steel_column_report_" in response.headers["content-disposition"]
    assert response.content.startswith(b"%PDF")
    assert len(response.content) > 1000
