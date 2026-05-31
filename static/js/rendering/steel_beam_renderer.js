import { normalizeApiErrors } from "../api/steel_beam_api.js";
import { renderSteelBeamPlots } from "./plots/steel_beam_plots.js";
import { el, setText } from "../utils/dom.js";
import { logBackendFieldMapping } from "../utils/debug.js";
import { fmt } from "../utils/format.js";

export function setWorkflowStatus(kind, text) {
  if (typeof window.setStatus === "function") window.setStatus(kind || "", text || "");
}

export function setEngineeringStatus(kind, text) {
  if (typeof window.setBeamResultStatus === "function") window.setBeamResultStatus(kind || "", text || "");
}

export function setCalculateButtonBusy(busy) {
  const button = el("btnCalc");
  if (!button) return;
  button.disabled = !!busy;
  button.setAttribute("aria-busy", busy ? "true" : "false");
  button.textContent = busy ? "Calculating..." : "Calculate";
}

export function setReportButtonBusy(busy) {
  const button = el("btnSteelBeamReport");
  if (!button) return;
  button.disabled = !!busy;
  button.setAttribute("aria-busy", busy ? "true" : "false");
  button.textContent = busy ? "Generating PDF..." : "Generate PDF Report";
}

function paintRecommendations(recommendations) {
  const bestEl = el("beamBestRec");
  const metaEl = el("beamRecMeta");
  const listEl = el("beamRecList");
  if (!metaEl || !listEl) return;

  listEl.innerHTML = "";
  if (!recommendations || !recommendations.length) {
    if (bestEl) bestEl.textContent = "No passing section found";
    metaEl.textContent = "No steel section in the current profile library satisfies the current backend checks.";
    return;
  }

  const best = recommendations[0];
  if (bestEl) bestEl.textContent = best.section || "-";
  metaEl.textContent = "Best suitable = lightest passing section. Control "
    + fmt(best.utilization, 3)
    + " | delta " + fmt(best.delta_mm, 2)
    + " / " + fmt(best.delta_allow_mm, 2)
    + " mm | " + fmt(best.weight_kg_m, 1)
    + " kg/m";

  recommendations.slice(0, 6).forEach(function (item, index) {
    const pill = document.createElement("span");
    pill.className = "recPill";
    pill.textContent = index === 0 ? "Best: " + item.section : item.section;
    if (item.section && typeof window.selectRecommendedBeamSection === "function") {
      pill.setAttribute("role", "button");
      pill.setAttribute("tabindex", "0");
      pill.title = "Click to select " + item.section;
      pill.addEventListener("click", function () {
        window.selectRecommendedBeamSection(item.section);
      });
      pill.addEventListener("keydown", function (event) {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          window.selectRecommendedBeamSection(item.section);
        }
      });
    }
    listEl.appendChild(pill);
  });
}

function paintSupportWidthRecommendations(recommendations, status) {
  if (typeof window.renderBackendSupportWidthRecommendations !== "function") return;
  window.renderBackendSupportWidthRecommendations(Array.isArray(recommendations) ? recommendations : [], status || {});
}

function safeUiPaint(label, painter, uiWarnings) {
  try {
    painter();
  } catch (error) {
    const message = "Could not render " + label + " from backend response.";
    console.warn("[steel-beam] " + message, error);
    if (Array.isArray(uiWarnings) && uiWarnings.indexOf(message) === -1) {
      uiWarnings.push(message);
    }
  }
}

function backendAutoBreakdown(result) {
  const loads = (result && result.loads) || {};
  return (result && result.auto_load_breakdown) || loads.automatic_takedown || {};
}

function paintAutoLoadBreakdown(result) {
  const box = el("beamAutoSummary");
  if (!box) return;

  const breakdown = backendAutoBreakdown(result);
  console.log("[steel-beam] auto load breakdown UI mapping", breakdown);

  box.classList.add("autoSummary");
  box.innerHTML =
    '<div>Auto dead line load Gk = <span class="value">' + fmt(breakdown.auto_dead_load_kN_m, 3) + ' kN/m</span></div>' +
    '<div>Auto live line load Qk = <span class="value">' + fmt(breakdown.auto_live_load_kN_m, 3) + ' kN/m</span></div>' +
    '<div>Floor contribution = <span class="value">' + fmt(breakdown.floor_contribution_kN_m, 3) + ' kN/m</span></div>' +
    '<div>Wall contribution = <span class="value">' + fmt(breakdown.wall_contribution_kN_m, 3) + ' kN/m</span></div>';
}

export function paintWarnings(warnings, errors) {
  const items = [];
  if (Array.isArray(errors)) errors.forEach(function (item) { items.push("ERROR: " + item); });
  if (Array.isArray(warnings)) warnings.forEach(function (item) { items.push(item); });
  if (typeof window.warnList === "function") window.warnList(items);
}

export function paintValidationErrors(errors) {
  paintWarnings([], errors);
  setWorkflowStatus("bad", "Validation error");
  setEngineeringStatus("bad", "Validation error");
}

export function paintApiFailure(payload, statusCode) {
  const errors = normalizeApiErrors(payload, statusCode);
  paintWarnings((payload && payload.warnings) || [], errors);
  const statusText = statusCode === 422 ? "Validation error" : "Backend error";
  setWorkflowStatus("bad", statusText);
  setEngineeringStatus("bad", statusText);
}

export function paintResults(payload) {
  if (!payload || payload.success !== true) {
    paintApiFailure(payload || {}, 500);
    return;
  }

  document.documentElement.dataset.calculationEngine = "python-fastapi";
  const result = payload.results || {};
  const uiWarnings = [];
  logBackendFieldMapping(result);
  const section = result.section || {};
  const loads = result.loads || {};
  const reactions = result.reactions || {};
  const resistance = result.resistance || {};
  const utilization = result.utilization_detail || {};
  const deflection = result.deflection || {};
  const bearing = result.support_bearing || {};
  const bearingLeft = result.support_bearing_left || bearing;
  const bearingRight = result.support_bearing_right || bearing;
  const sectionClass = section.class || {};
  const ltb = result.ltb || null;

  setText("secName", section.name + " (h " + fmt(section.height_mm, 0) + " mm, b " + fmt(section.width_mm, 0) + " mm)");
  setText(
    "secClass",
    (sectionClass.overall ? "Class " + sectionClass.overall : "-")
      + (sectionClass.c_over_t ? " (flange " + fmt(sectionClass.c_over_t, 1) + ", web " + fmt(sectionClass.d_over_t, 1) + ")" : "")
  );
  setText("Wused", fmt(section.Wuse_cm3, 1) + " (" + (section.Wuse_kind || "-") + ")");
  setText("wULS", fmt(loads.w_ULS_kN_m, 4));
  setText("wSLS", fmt(loads.w_SLS_kN_m, 4));
  safeUiPaint("auto load breakdown", function () {
    paintAutoLoadBreakdown(result);
  }, uiWarnings);

  setText("MEd", fmt(result.MEd, 3));
  setText("VEd", fmt(result.VEd, 3));
  setText("beamRA", fmt(reactions.left_kN, 3));
  setText("beamRB", fmt(reactions.right_kN, 3));

  const live = reactions.live;
  const dead = reactions.dead;
  setText("beamRALive", live ? fmt(live.RA_kN, 3) : "-");
  setText("beamRBLive", live ? fmt(live.RB_kN, 3) : "-");
  setText("beamRADead", dead ? fmt(dead.RA_kN, 3) : "-");
  setText("beamRBDead", dead ? fmt(dead.RB_kN, 3) : "-");

  setText("beamSlofWidth", fmt(bearingLeft.width_cm, 0));
  setText("beamSlofLength", fmt(bearingLeft.length_cm, 2));
  setText("beamSlofWidth2", fmt(bearingRight.width_cm, 0));
  setText("beamSlofLength2", fmt(bearingRight.length_cm, 2));
  setText("beamSlofReinfMid", fmt(bearing.reinforcement_mid_cm2, 3));
  setText("beamSlofReinfHead", fmt(bearing.reinforcement_head_cm2, 3));

  setText("beamNEd", fmt(resistance.NEd_kN, 3));
  setText("beamNRd", fmt(resistance.NRd_kN, 2));
  setText("MRd", fmt(resistance.MRd_kNm, 2));
  setText("VRd", fmt(resistance.VRd_kN, 2));

  setText("utilM", fmt(utilization.M, 3));
  setText("utilV", fmt(utilization.V, 3));
  setText("utilInt", fmt(utilization.M_plus_V, 3));
  setText("utilN", fmt(utilization.N, 3));
  setText("utilNM", fmt(utilization.N_plus_M, 3));
  setText("utilD", fmt(result.utilization, 3));
  setText("delta", fmt(deflection.delta_max_mm || result.delta, 2) + " (allow " + fmt(deflection.delta_allow_mm, 2) + ")");

  const ltbBlock = el("ltbBlock");
  if (ltb && ltbBlock) {
    ltbBlock.classList.remove("hidden");
    setText("Mcr", fmt(ltb.Mcr_kNm, 2));
    setText("chiLT", fmt(ltb.chi_LT, 3));
    setText("MbRd", fmt(ltb.MbRd_kNm, 2));
    setText("utilLTB", fmt(ltb.utilization, 3));
  } else if (ltbBlock) {
    ltbBlock.classList.add("hidden");
  }

  setWorkflowStatus("ok", "Success");
  setEngineeringStatus(result.status_kind || "", result.status || "");

  safeUiPaint("section recommendations", function () {
    paintRecommendations(result.recommendations || []);
  }, uiWarnings);
  safeUiPaint("support-width recommendations", function () {
    paintSupportWidthRecommendations(
      result.support_width_recommendations || [],
      result.support_width_recommendation_status || {}
    );
  }, uiWarnings);
  safeUiPaint("engineering diagrams", function () {
    renderSteelBeamPlots(result.plots || {});
  }, uiWarnings);
  paintWarnings((payload.warnings || result.warnings || []).concat(uiWarnings), payload.errors || []);
}
