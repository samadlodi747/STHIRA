import { pathValue } from "./dom.js";

export const DEBUG_STEEL_BEAM_API = true;

export function logBackendFieldMapping(result) {
  if (!DEBUG_STEEL_BEAM_API) return;

  const requiredPaths = [
    "MEd",
    "VEd",
    "delta",
    "utilization",
    "status",
    "governing_combination",
    "reactions.left_kN",
    "reactions.right_kN",
    "deflection.delta_max_mm",
    "deflection.delta_allow_mm",
    "resistance.MRd_kNm",
    "resistance.VRd_kN",
    "auto_load_breakdown.auto_dead_load_kN_m",
    "auto_load_breakdown.auto_live_load_kN_m",
    "auto_load_breakdown.floor_contribution_kN_m",
    "auto_load_breakdown.wall_contribution_kN_m",
    "recommendations",
    "plots.x",
    "plots.shear",
    "plots.moment",
    "plots.deflection",
    "plots.markers"
  ];

  const missing = requiredPaths.filter(function (path) {
    return pathValue(result, path) === undefined;
  });

  console.log("[steel-beam] UI mapping from backend", {
    MEd: result.MEd,
    VEd: result.VEd,
    reactions: result.reactions,
    deflection: result.deflection,
    utilization: result.utilization,
    governing_combination: result.governing_combination,
    auto_load_breakdown: result.auto_load_breakdown,
    plots: result.plots,
    support_width_recommendations: result.support_width_recommendations,
    recommendation_count: Array.isArray(result.recommendations) ? result.recommendations.length : 0
  });

  if (missing.length) console.warn("[steel-beam] missing backend fields", missing);
}
