from app import app
from core.timber.beam import calculate_timber_beam
from fastapi.testclient import TestClient
from models.steel import LineLoad, SteelBeamLoads
from models.timber import TimberBeamDesignOptions, TimberBeamGeometry, TimberBeamRequest, TimberMaterial


client = TestClient(app)


def _request(grade, span, section, w_kN_m):
    return TimberBeamRequest(
        section_name=section,
        geometry=TimberBeamGeometry(span_m=span),
        material=TimberMaterial(grade=grade),
        loads=SteelBeamLoads(mode="comb", line_loads=[LineLoad(w_kN_m=w_kN_m, type="live")], include_self_weight=True),
        design=TimberBeamDesignOptions(recommendation_limit=8),
    )


def test_case1_c24_5m():
    result = calculate_timber_beam(_request("C24", 5.0, "75x225", 4.0))
    res = result["results"]
    assert result["success"] is True
    assert res["material"]["grade"] == "C24"
    assert res["material"]["gamma_M"] == 1.3
    assert res["MEd_kNm"] > 0
    assert res["VEd_kN"] > 0
    ud = res["utilization_detail"]
    assert ud["bending"] > 0 and ud["shear"] > 0 and ud["deflection"] > 0
    assert res["status_detail"]["kind"] in {"ok", "warn", "bad"}
    # Recommendation engine returns passing sections, smallest (area) first.
    recs = res["recommendations"]
    assert isinstance(recs, list)
    if len(recs) >= 2:
        assert recs[0]["area_mm2"] <= recs[1]["area_mm2"]


def test_case2_gl28h_7m():
    result = calculate_timber_beam(_request("GL28h", 7.0, "100x300", 5.0))
    res = result["results"]
    assert result["success"] is True
    assert res["material"]["grade"] == "GL28h"
    assert res["material"]["gamma_M"] == 1.25
    assert res["MEd_kNm"] > 0
    assert res["deflection"]["delta_allow_mm"] == 7000.0 / 300.0
    assert res["eurocode"]["standard"] == "EN 1995-1-1"


def test_deflection_limit_configurable():
    base = _request("C24", 6.0, "90x270", 3.0)
    strict = base.model_copy(update={"geometry": TimberBeamGeometry(span_m=6.0, deflection_limit_ratio=500.0)})
    r_default = calculate_timber_beam(base)["results"]["deflection"]
    r_strict = calculate_timber_beam(strict)["results"]["deflection"]
    # Same deflection, tighter allowable -> larger utilization. Calculation logic unchanged.
    assert r_strict["delta_allow_mm"] < r_default["delta_allow_mm"]
    assert abs(r_strict["delta_max_mm"] - r_default["delta_max_mm"]) < 1e-6


def test_recommendation_smallest_passing():
    res = calculate_timber_beam(_request("C24", 5.0, "63x175", 8.0))["results"]
    recs = res["recommendations"]
    # Every recommended section must satisfy all three checks (utilization <= 1.0).
    for item in recs:
        assert item["util_bending"] <= 1.0
        assert item["util_shear"] <= 1.0
        assert item["util_deflection"] <= 1.0


def test_timber_api_returns_standard_response():
    response = client.post(
        "/calculate/timber-beam",
        json={
            "section_name": "75x225",
            "geometry": {"span_m": 5.0},
            "material": {"grade": "C24"},
            "loads": {"mode": "direct", "direct_w_kN_m": 4.0, "include_self_weight": True},
            "design": {"recommendation_limit": 5},
        },
    )
    body = response.json()
    assert response.status_code == 200
    assert body["success"] is True
    assert body["results"]["member_type"] == "Timber Beam"
    assert body["results"]["section"]["name"] == "75x225"


def test_timber_unknown_section_is_friendly():
    response = client.post(
        "/calculate/timber-beam",
        json={"section_name": "999x999", "geometry": {"span_m": 5.0}, "material": {"grade": "C24"}},
    )
    assert response.status_code == 422
    assert response.json()["success"] is False


def test_timber_report_endpoint_returns_pdf():
    response = client.post(
        "/reports/timber-beam",
        json={
            "section_name": "100x300",
            "geometry": {"span_m": 7.0},
            "material": {"grade": "GL28h"},
            "loads": {"mode": "direct", "direct_w_kN_m": 5.0, "include_self_weight": True},
            "design": {"recommendation_limit": 5},
        },
    )
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert response.content.startswith(b"%PDF")
    assert len(response.content) > 1000
