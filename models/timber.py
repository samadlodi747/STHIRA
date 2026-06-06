from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

# Reuse the steel beam load model so the timber workflow shares the same load inputs
# (line loads by type, point loads, direct UDL, combination factors) and frontend form.
from models.steel import SteelBeamLoads


class TimberBeamGeometry(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    # Input unit: m.
    span_m: float = Field(gt=0)
    # Deflection limit ratio is configurable so future limits need no calculation change.
    deflection_limit_ratio: float = Field(default=300.0, gt=0)
    # Custom rectangular dimensions (mm). When provided, the user-entered section is used
    # directly; the section library is only used for recommendations.
    width_mm: float | None = Field(default=None, gt=0)
    height_mm: float | None = Field(default=None, gt=0)


class TimberMaterial(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    # Any grade present in the material database (validated in the engine).
    grade: str = "C24"


class TimberBeamDesignOptions(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    # EN 1995-1-1 modification factor (service class / load-duration). Default 0.8 =
    # service class 1, medium-term. Exposed so it can be configured without code changes.
    kmod: float = Field(default=0.8, gt=0.0, le=1.1)
    recommendation_limit: int = Field(default=8, ge=0, le=50)


class TimberAppliedEffects(BaseModel):
    """Pre-computed design effects from the original timber load take-down. When supplied,
    the EC5 engine uses these effects directly (bending/shear/deflection checks against EC5
    resistances) instead of recomputing loads — so the original load workflow is preserved."""

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    MEd_kNm: float = Field(ge=0.0)
    VEd_kN: float = Field(ge=0.0)
    delta_mm: float = Field(ge=0.0)


class TimberBeamRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    # Optional when custom geometry.width_mm/height_mm are supplied (the original UI lets
    # the user enter any size); otherwise a library section name is used.
    section_name: str = ""
    geometry: TimberBeamGeometry
    material: TimberMaterial = Field(default_factory=TimberMaterial)
    loads: SteelBeamLoads = Field(default_factory=SteelBeamLoads)
    design: TimberBeamDesignOptions = Field(default_factory=TimberBeamDesignOptions)
    # When provided, EC5 checks use these effects (from the original take-down) directly.
    effects: TimberAppliedEffects | None = None


class TimberBeamApiResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    success: bool
    results: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
