import { normalizeColumnApiErrors } from "../api/steel_column_api.js";
import { el, setText } from "../utils/dom.js";
import { fmt } from "../utils/format.js";

export function setColumnWorkflowStatus(kind, text) {
  if (typeof window.setStatus === "function") window.setStatus(kind || "", text || "");
}

export function setColumnEngineeringStatus(kind, text) {
  if (typeof window.setColumnResultStatus === "function") window.setColumnResultStatus(kind || "", text || "");
}

export function setColumnCalculateButtonBusy(busy) {
  const button = el("btnCalc");
  if (!button) return;
  button.disabled = !!busy;
  button.setAttribute("aria-busy", busy ? "true" : "false");
  button.textContent = busy ? "Calculating..." : "Calculate";
}

export function setColumnReportButtonBusy(busy) {
  const button = el("btnSteelBeamReport");
  if (!button) return;
  button.disabled = !!busy;
  button.setAttribute("aria-busy", busy ? "true" : "false");
  button.textContent = busy ? "Generating PDF..." : "Generate PDF Report";
}

export function paintColumnWarnings(warnings, errors) {
  const items = [];
  if (Array.isArray(errors)) errors.forEach(function (item) { items.push("ERROR: " + item); });
  if (Array.isArray(warnings)) warnings.forEach(function (item) { items.push(item); });
  if (typeof window.warnList === "function") window.warnList(items);
}

export function paintColumnValidationErrors(errors) {
  paintColumnWarnings([], errors);
  setColumnWorkflowStatus("bad", "Validation error");
  setColumnEngineeringStatus("bad", "Validation error");
}

export function paintColumnApiFailure(payload, statusCode) {
  const errors = normalizeColumnApiErrors(payload, statusCode);
  paintColumnWarnings((payload && payload.warnings) || [], errors);
  const statusText = statusCode === 422 ? "Validation error" : "Backend error";
  setColumnWorkflowStatus("bad", statusText);
  setColumnEngineeringStatus("bad", statusText);
}

function logColumnMapping(result) {
  console.log("[steel-column] UI mapping from backend", {
    effects: result.effects,
    resistance: result.resistance,
    utilization_detail: result.utilization_detail,
    buckling: result.buckling,
    deflection: result.deflection,
    recommendations: result.recommendations,
    governing_combination: result.governing_combination
  });
}

export function paintColumnResults(payload) {
  if (!payload || payload.success !== true) {
    paintColumnApiFailure(payload || {}, 500);
    return;
  }

  document.documentElement.dataset.columnCalculationEngine = "python-fastapi";
  const result = payload.results || {};
  logColumnMapping(result);
  const beamPlots = el("beamPlots");
  if (beamPlots) beamPlots.classList.add("hidden");

  const section = result.section || {};
  const effects = result.effects || {};
  const resistance = result.resistance || {};
  const utilization = result.utilization_detail || {};
  const buckling = result.buckling || {};
  const stability = result.stability_summary || {};
  const eurocode = result.eurocode || {};
  const sectionClassification = (eurocode.section_classification || section.classification || {});
  const deflection = result.deflection || {};
  const combos = result.combos || {};
  const governingUls = combos.governing_uls || {};
  const governingSls = combos.governing_sls || {};
  const recs = Array.isArray(result.recommendations) ? result.recommendations : [];
  const best = recs[0] || null;

  [
    ["resistance.NbRdy_kN", resistance.NbRdy_kN],
    ["resistance.NbRdz_kN", resistance.NbRdz_kN],
    ["buckling.lambda_bar_y", buckling.lambda_bar_y],
    ["buckling.lambda_bar_z", buckling.lambda_bar_z],
    ["buckling.buckling_curve_y", buckling.buckling_curve_y],
    ["stability_summary.governing_axis", stability.governing_axis]
  ].forEach(function (entry) {
    if (entry[1] === undefined || entry[1] === null) {
      console.warn("[steel-column] missing backend field for UI mapping", entry[0]);
    }
  });

  setText("colSecName", section.name || "-");
  setText("colWorstUls", governingUls.combo ? governingUls.combo.name : "-");
  setText("colWorstSls", governingSls.combo ? governingSls.combo.name : "-");
  const lambdaPair = fmt(buckling.lambda_bar_y, 3) + " / " + fmt(buckling.lambda_bar_z, 3);
  const chiPair = fmt(buckling.chi_y, 3) + " / " + fmt(buckling.chi_z, 3);
  const nbRdPair = fmt(resistance.NbRdy_kN, 2) + " / " + fmt(resistance.NbRdz_kN, 2);
  const curvePair = (buckling.buckling_curve_y || "-") + " / " + (buckling.buckling_curve_z || "-");
  const governingAxis = stability.governing_axis || buckling.governing_axis || "-";
  const governingAxisCurve = governingAxis === "-" ? "-" : governingAxis + "-axis / curves " + curvePair;

  setText("colNEd", fmt(effects.NEd_kN, 3));
  setText("colNRd", fmt(resistance.NcRd_kN, 2));
  setText("colVyEd", fmt(effects.VyEd_kN, 3));
  setText("colMyEd", fmt(effects.NEd_kN, 3));
  setText("colVzEd", nbRdPair);
  setText("colMzEd", fmt(effects.MzEd_kNm, 3));
  setText("colRA", chiPair);
  setText("colRB", lambdaPair);
  setText("colUcComp", fmt(utilization.compression, 3));
  setText("colUcShear", fmt(utilization.shear_y, 3) + " / " + fmt(utilization.shear_z, 3));
  setText("colUcMy", fmt(utilization.N_V_My, 3));
  setText("colUcMz", fmt(utilization.N_V_Mz, 3));
  setText("colUcMyMz", fmt(utilization.N_V_My_Mz, 3));
  setText("colUcStab", fmt(utilization.stability_y, 3) + " / " + fmt(utilization.stability_z, 3));
  setText("colChi", chiPair);
  setText("colChiLT", fmt(buckling.chi_lt, 3));
  setText("colSlender", fmt(buckling.slender_y, 1) + " / " + fmt(buckling.slender_z, 1));
  setText("colDefl", governingAxisCurve);
  setText("colUtilDefl", fmt(result.utilization, 3));
  const govCheck = result.governing_check_description || result.governing_check || "-";
  const govReason = result.governing_failure_reason || stability.governing_failure_reason || "";
  let govText = govCheck + " (" + governingAxis + "-axis) = " + fmt(result.utilization, 3);
  if (result.status_kind === "bad" && govReason) govText += " — " + govReason;
  setText("colGov", govText);
  setText("colRec", best ? best.section + " (" + fmt(best.utilization, 3) + ")" : "No passing K section found");
  setText("colNbRdy", fmt(resistance.NbRdy_kN, 2));
  setText("colNbRdz", fmt(resistance.NbRdz_kN, 2));
  setText("colLambdaBar", lambdaPair);
  setText("colGovAxis", governingAxis);
  setText("colBucklingCurve", curvePair);
  setText("colSectionClassAssumption", sectionClassification.assumption || "-");

  setColumnWorkflowStatus("ok", "Success");
  setColumnEngineeringStatus(result.status_kind || "", result.status || "");
  paintColumnWarnings(payload.warnings || result.warnings || [], payload.errors || []);
}
