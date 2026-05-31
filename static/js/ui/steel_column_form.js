import { checked, numberValue, value } from "../utils/dom.js";

function columnLoadCase(prefix) {
  return {
    N_kN: numberValue("c_" + prefix + "_N", 0),
    py_kN_m: 0,
    pz_kN_m: 0,
    Py_kN: 0,
    ay_m: 0,
    Pz_kN: 0,
    az_m: 0
  };
}

export function buildSteelColumnPayload() {
  return {
    profile_name: value("profile", ""),
    geometry: {
      length_m: numberValue("colL", 0),
      buckling_length_y_m: numberValue("colLy", 0),
      buckling_length_z_m: numberValue("colLz", 0),
      ltb_length_m: numberValue("colLlt", 0),
      deflection_limit_ratio: numberValue("colDeflLimit", 500)
    },
    material: {
      fy_MPa: numberValue("fy", 235),
      E_GPa: numberValue("E", 210),
      gamma_M0: numberValue("colGammaM0", 1)
    },
    loads: {
      permanent: columnLoadCase("perm"),
      snow: columnLoadCase("snow"),
      wind: columnLoadCase("wind"),
      variable: columnLoadCase("var"),
      include_self_weight: checked("colIncludeSelfWeight", true)
    },
    design: {
      finish_type: Number(value("colFinish", "2")) || 2,
      load_position: Number(value("colLoadPos", "0")) || 0,
      gamma_M1: numberValue("colGammaM1", 1),
      recommendation_limit: 50
    }
  };
}

