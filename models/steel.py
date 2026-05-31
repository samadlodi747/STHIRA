from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


ActionType = Literal["G", "live", "wind", "snow"]
AxisType = Literal["major", "minor"]
LoadMode = Literal["direct", "comb"]
LeadAction = Literal["auto", "live", "wind", "snow"]
SlsCase = Literal["rare", "freq", "qp"]
SlabType = Literal["wood", "potten", "welfsels"]
AccessibilityType = Literal["not", "accessible"]


class LineLoad(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    # Input/output unit: kN/m, downward positive.
    w_kN_m: float = Field(default=0.0, ge=0.0)
    type: ActionType = "G"


class PointLoad(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    # Input/output unit: kN, downward positive.
    P_kN: float = Field(default=0.0, ge=0.0)
    # Input/output unit: m from the left support.
    a_m: float = Field(default=0.0, ge=0.0)
    type: ActionType = "live"


class AutomaticFloorLoad(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    level: str = ""
    slab_type: SlabType = "wood"
    subtype: str = ""
    span_m: float = Field(default=0.0, ge=0.0)
    accessible: AccessibilityType = "not"
    # Input unit: kN/m2. Used only for slab types with user-entered dead load.
    dead_kN_m2: float = Field(default=0.0, ge=0.0)
    additional_dead_kN_m2: float = Field(default=0.0, ge=0.0)


class AutomaticWallLoad(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    level: str = ""
    thickness_cm: float = Field(default=0.0, ge=0.0)
    density_kN_m3: float = Field(default=0.0, ge=0.0)
    height_m: float = Field(default=0.0, ge=0.0)
    percent: float = Field(default=100.0, ge=0.0)


class AutomaticLoadTakedown(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    enabled: bool = False
    include_wall: bool = True
    floor_rows: list[AutomaticFloorLoad] = Field(default_factory=list)
    wall_rows: list[AutomaticWallLoad] = Field(default_factory=list)


class SteelBeamGeometry(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    # Input unit: m. Internal unit: m/mm depending on formula context.
    span_m: float = Field(gt=0)
    axis: AxisType = "major"
    deflection_limit_ratio: float = Field(default=500.0, gt=0)


class SteelMaterial(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    # Input unit: MPa = N/mm2.
    fy_MPa: float = Field(default=235.0, gt=0)
    # Input unit: GPa, converted to N/mm2 in core.
    E_GPa: float = Field(default=210.0, gt=0)
    gamma_M0: float = Field(default=1.0, gt=0)


class SteelBeamLoads(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    mode: LoadMode = "direct"
    direct_w_kN_m: float = Field(default=0.0, ge=0.0)
    line_loads: list[LineLoad] = Field(default_factory=list)
    point_loads: list[PointLoad] = Field(default_factory=list)
    automatic: AutomaticLoadTakedown = Field(default_factory=AutomaticLoadTakedown)
    include_self_weight: bool = True
    gamma_G: float = Field(default=1.35, ge=0.0)
    gamma_Q: float = Field(default=1.50, ge=0.0)
    psi0: dict[str, float] = Field(default_factory=lambda: {"live": 0.7, "wind": 0.6, "snow": 0.5})
    psi1: dict[str, float] = Field(default_factory=lambda: {"live": 0.5, "wind": 0.2, "snow": 0.2})
    psi2: dict[str, float] = Field(default_factory=lambda: {"live": 0.3, "wind": 0.0, "snow": 0.0})
    sls_case: SlsCase = "rare"
    lead_action: LeadAction = "auto"

    @field_validator("psi0", "psi1", "psi2")
    @classmethod
    def validate_psi_factors(cls, values: dict[str, float]) -> dict[str, float]:
        for action in ("live", "wind", "snow"):
            value = float(values.get(action, 0.0))
            if value < 0.0:
                raise ValueError(f"psi factor for {action} cannot be negative")
            values[action] = value
        return values


class LtbOptions(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    enabled: bool = False
    unrestrained_length_m: float = Field(default=0.0, ge=0.0)
    C1: float = Field(default=1.0, gt=0.0)
    alpha_LT: float = Field(default=0.34, ge=0.0)
    gamma_M1: float = Field(default=1.0, gt=0.0)
    lambda_LT0: float = Field(default=0.4, ge=0.0)
    beta_LT: float = Field(default=0.75, ge=0.0)
    poisson_ratio: float = Field(default=0.3, ge=0.0, lt=0.5)


class SteelBeamDesignOptions(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    axial_NEd_kN: float = 0.0
    shear_area_override_cm2: float | None = Field(default=None, ge=0.0)
    reduce_bending_for_high_shear: bool = True
    # Legacy single support width, retained for backward compatibility. New clients send
    # independent left/right widths below; if only this is provided both ends use it.
    support_width_cm: float | None = Field(default=None, gt=0.0)
    left_support_width_cm: float | None = Field(default=None, gt=0.0)
    right_support_width_cm: float | None = Field(default=None, gt=0.0)
    recommendation_limit: int = Field(default=8, ge=0, le=50)
    ltb: LtbOptions = Field(default_factory=LtbOptions)

    @property
    def left_width_cm(self) -> float | None:
        return self.left_support_width_cm if self.left_support_width_cm is not None else self.support_width_cm

    @property
    def right_width_cm(self) -> float | None:
        return self.right_support_width_cm if self.right_support_width_cm is not None else self.support_width_cm

    @property
    def effective_support_width_cm(self) -> float | None:
        # The minimum support width governs the bearing condition, so support-width
        # recommendations and filtering are driven by min(left, right).
        widths = [w for w in (self.left_width_cm, self.right_width_cm) if w is not None and w > 0.0]
        return min(widths) if widths else None


class SteelBeamRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    profile_name: str
    geometry: SteelBeamGeometry
    material: SteelMaterial = Field(default_factory=SteelMaterial)
    loads: SteelBeamLoads = Field(default_factory=SteelBeamLoads)
    design: SteelBeamDesignOptions = Field(default_factory=SteelBeamDesignOptions)

    @field_validator("profile_name")
    @classmethod
    def validate_profile_name(cls, value: str) -> str:
        clean = value.strip()
        if not clean:
            raise ValueError("profile_name is required")
        return clean


class SteelBeamApiResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    success: bool
    results: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


class SteelColumnGeometry(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    # Input unit: m.
    length_m: float = Field(gt=0)
    buckling_length_y_m: float = Field(gt=0)
    buckling_length_z_m: float = Field(gt=0)
    ltb_length_m: float = Field(default=0.0, ge=0.0)
    deflection_limit_ratio: float = Field(default=500.0, gt=0)


class SteelColumnLoadCase(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    # Compression and lateral actions are positive in the design direction used by the legacy K-sheet workflow.
    N_kN: float = Field(default=0.0, ge=0.0)
    py_kN_m: float = Field(default=0.0, ge=0.0)
    pz_kN_m: float = Field(default=0.0, ge=0.0)
    Py_kN: float = Field(default=0.0, ge=0.0)
    ay_m: float = Field(default=0.0, ge=0.0)
    Pz_kN: float = Field(default=0.0, ge=0.0)
    az_m: float = Field(default=0.0, ge=0.0)


class SteelColumnLoads(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    permanent: SteelColumnLoadCase = Field(default_factory=SteelColumnLoadCase)
    snow: SteelColumnLoadCase = Field(default_factory=SteelColumnLoadCase)
    wind: SteelColumnLoadCase = Field(default_factory=SteelColumnLoadCase)
    variable: SteelColumnLoadCase = Field(default_factory=SteelColumnLoadCase)
    include_self_weight: bool = True


class SteelColumnDesignOptions(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    finish_type: Literal[1, 2] = 2
    load_position: Literal[-1, 0, 1] = 0
    gamma_M1: float = Field(default=1.0, gt=0.0)
    recommendation_limit: int = Field(default=8, ge=0, le=50)


class SteelColumnRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    profile_name: str
    geometry: SteelColumnGeometry
    material: SteelMaterial = Field(default_factory=SteelMaterial)
    loads: SteelColumnLoads = Field(default_factory=SteelColumnLoads)
    design: SteelColumnDesignOptions = Field(default_factory=SteelColumnDesignOptions)

    @field_validator("profile_name")
    @classmethod
    def validate_column_profile_name(cls, value: str) -> str:
        clean = value.strip()
        if not clean:
            raise ValueError("profile_name is required")
        return clean


class SteelColumnApiResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    success: bool
    results: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


Orientation = Literal["portrait", "landscape"]


class MemberScheduleRequest(BaseModel):
    # Project-level member schedule report. Members are saved member entries from the
    # frontend schedule (already-computed display values); the report does not recalculate.
    model_config = ConfigDict(extra="ignore")

    project_name: str = ""
    orientation: Orientation = "landscape"
    members: list[dict[str, Any]] = Field(default_factory=list)
