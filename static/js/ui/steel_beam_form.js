import { checked, el, numberFromNode, numberValue, value } from "../utils/dom.js";

function normalizeAction(type) {
  const action = String(type || "live").toLowerCase();
  if (action === "g") return "G";
  if (action === "wind" || action === "snow" || action === "live") return action;
  return "live";
}

function legacyUdlRows() {
  try {
    if (typeof UDL_LOAD_ROWS !== "undefined" && Array.isArray(UDL_LOAD_ROWS)) return UDL_LOAD_ROWS;
  } catch (error) {}
  return Array.isArray(window.UDL_LOAD_ROWS) ? window.UDL_LOAD_ROWS : [];
}

function legacyPointRows() {
  try {
    if (typeof POINT_LOAD_ROWS !== "undefined" && Array.isArray(POINT_LOAD_ROWS)) return POINT_LOAD_ROWS;
  } catch (error) {}
  return Array.isArray(window.POINT_LOAD_ROWS) ? window.POINT_LOAD_ROWS : [];
}

function readManualLineLoads() {
  const host = el("udlRows");
  const rows = [];
  if (host) {
    Array.from(host.children).forEach(function (row) {
      const input = row.querySelector("input");
      const select = row.querySelector("select");
      if (!input || input.readOnly) return;
      rows.push({
        w_kN_m: numberFromNode(input, 0),
        type: normalizeAction(select && select.value)
      });
    });
    return rows;
  }

  return legacyUdlRows()
    .filter(function (row) { return !(row && row.__auto); })
    .map(function (row) {
      return {
        w_kN_m: Number(row && row.w) || 0,
        type: normalizeAction(row && row.type)
      };
    });
}

function readPointLoads() {
  return legacyPointRows().map(function (row) {
    return {
      P_kN: Number(row && row.P) || 0,
      a_m: Number(row && row.a) || 0,
      type: normalizeAction(row && row.type)
    };
  }).filter(function (row) {
    return Math.abs(row.P_kN) > 1e-12;
  });
}

function readAutomaticFloorRows() {
  const host = el("beamAutoFloorRows");
  if (!host) return [];
  return Array.from(host.children).map(function (row) {
    const inputs = row.querySelectorAll("input");
    const selects = row.querySelectorAll("select");
    const slabType = (selects[0] && selects[0].value) || "wood";
    const hasSubtype = selects.length >= 3;
    return {
      level: (inputs[0] && inputs[0].value) || "",
      slab_type: slabType,
      subtype: hasSubtype ? ((selects[1] && selects[1].value) || "") : "",
      span_m: numberFromNode(inputs[1], 0),
      accessible: hasSubtype
        ? ((selects[2] && selects[2].value) || "not")
        : ((selects[1] && selects[1].value) || "not"),
      dead_kN_m2: numberFromNode(inputs[2], 0),
      additional_dead_kN_m2: numberFromNode(inputs[3], 0)
    };
  });
}

function readAutomaticWallRows() {
  const host = el("beamAutoWallRows");
  if (!host) return [];
  return Array.from(host.children).map(function (row) {
    const inputs = row.querySelectorAll("input");
    return {
      level: (inputs[0] && inputs[0].value) || "",
      thickness_cm: numberFromNode(inputs[1], 0),
      density_kN_m3: numberFromNode(inputs[2], 0),
      height_m: numberFromNode(inputs[3], 0),
      percent: numberFromNode(inputs[4], 100)
    };
  });
}

function readAutomaticLoadTakedown() {
  const isCombinationMode = value("loadMode", "direct") === "comb";
  return {
    enabled: isCombinationMode && checked("beamAutoLoadsToggle", false),
    include_wall: checked("beamAutoIncludeWall", true),
    floor_rows: readAutomaticFloorRows(),
    wall_rows: readAutomaticWallRows()
  };
}

export function buildSteelBeamPayload() {
  const loadMode = value("loadMode", "direct");
  return {
    profile_name: value("profile", ""),
    geometry: {
      span_m: numberValue("L", 0),
      axis: value("axis", "major"),
      deflection_limit_ratio: numberValue("deflLimit", 500)
    },
    material: {
      fy_MPa: numberValue("fy", 235),
      E_GPa: numberValue("E", 210),
      gamma_M0: numberValue("gammaM0", 1)
    },
    loads: {
      mode: loadMode,
      direct_w_kN_m: loadMode === "direct" ? numberValue("w", 0) : 0,
      line_loads: readManualLineLoads(),
      point_loads: readPointLoads(),
      automatic: readAutomaticLoadTakedown(),
      include_self_weight: checked("includeSelfWeight", true),
      gamma_G: numberValue("gammaG", 1.35),
      gamma_Q: numberValue("gammaQ", 1.5),
      psi0: {
        live: numberValue("psi0_live", 0.7),
        wind: numberValue("psi0_wind", 0.6),
        snow: numberValue("psi0_snow", 0.5)
      },
      psi1: {
        live: numberValue("psi1_live", 0.5),
        wind: numberValue("psi1_wind", 0.2),
        snow: numberValue("psi1_snow", 0.2)
      },
      psi2: {
        live: numberValue("psi2_live", 0.3),
        wind: numberValue("psi2_wind", 0),
        snow: numberValue("psi2_snow", 0)
      },
      sls_case: value("slsCase", "rare"),
      lead_action: value("leadAction", "auto")
    },
    design: {
      axial_NEd_kN: numberValue("Ned", 0),
      shear_area_override_cm2: value("AvOverride", "") === "" ? null : numberValue("AvOverride", null),
      reduce_bending_for_high_shear: checked("useHighShearReduction", true),
      left_support_width_cm: value("beamLeftSupportWidthCm", "") === "" ? null : numberValue("beamLeftSupportWidthCm", null),
      right_support_width_cm: value("beamRightSupportWidthCm", "") === "" ? null : numberValue("beamRightSupportWidthCm", null),
      recommendation_limit: 50,
      ltb: {
        enabled: checked("checkLTB", false),
        unrestrained_length_m: numberValue("Lb", 0),
        C1: numberValue("C1", 1),
        alpha_LT: numberValue("alphaLT", 0.34),
        gamma_M1: numberValue("gammaM1", 1),
        lambda_LT0: numberValue("lambdaLT0", 0.4),
        beta_LT: numberValue("betaLT", 0.75),
        poisson_ratio: numberValue("nu", 0.3)
      }
    }
  };
}
