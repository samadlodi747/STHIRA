import { calculateTimberBeam, generateTimberBeamReport } from "../api/timber_beam_api.js";
import { el, value, numberValue, checked } from "../utils/dom.js";
import { fmt } from "../utils/format.js";
import { downloadBlob } from "../utils/download.js";

// EN 1995-1-1 kmod (service class -> load-duration), mirroring the original STHIRA tables,
// so the EC5 overlay derives kmod from the existing Climate + Variable-load-category inputs.
const CATEGORY_DURATION = { A: "medium", B: "medium", C: "short", D: "medium", E: "long", X: "instant" };
const KMOD = {
  "1": { permanent: 0.6, long: 0.7, medium: 0.8, short: 0.9, instant: 1.1 },
  "2": { permanent: 0.6, long: 0.7, medium: 0.8, short: 0.9, instant: 1.1 },
  "3": { permanent: 0.5, long: 0.55, medium: 0.65, short: 0.7, instant: 0.9 }
};

function deriveKmod() {
  const climate = value("timberClimate", "1");
  const cat = value("timberVarCat", "A");
  const duration = CATEGORY_DURATION[cat] || "medium";
  const table = KMOD[climate] || KMOD["1"];
  return table[duration] || 0.8;
}

function parseFirstNumber(text) {
  const match = String(text == null ? "" : text).replace(",", ".").match(/-?\d+(\.\d+)?/);
  return match ? Number(match[0]) : NaN;
}

// δmax card text is "12.34 (allow 16.67)".
function parseDeflection(text) {
  const t = String(text || "");
  const dmax = parseFirstNumber(t.split("(")[0]);
  return Number.isFinite(dmax) ? dmax : 0;
}

function readOriginalEffects() {
  const MEd = parseFirstNumber(value("timberM", "") || (el("timberM") && el("timberM").textContent));
  const VEd = parseFirstNumber(value("timberV", "") || (el("timberV") && el("timberV").textContent));
  const dmax = parseDeflection(el("timberDefl") && el("timberDefl").textContent);
  return { MEd: Number.isFinite(MEd) ? Math.abs(MEd) : NaN, VEd: Number.isFinite(VEd) ? Math.abs(VEd) : NaN, delta: dmax };
}

// Build the EC5 payload from the ORIGINAL timber inputs + the take-down effects.
function buildEc5Payload() {
  const eff = readOriginalEffects();
  const payload = {
    section_name: "",
    geometry: {
      span_m: numberValue("timberL", 0),
      deflection_limit_ratio: numberValue("timberDeflLimit", 300),
      width_mm: numberValue("timberB", 0),
      height_mm: numberValue("timberH", 0)
    },
    material: { grade: value("timberGrade", "C24") },
    design: { kmod: deriveKmod(), recommendation_limit: 8 },
    loads: { mode: "comb", line_loads: [], point_loads: [], include_self_weight: checked("timberIncludeSelfWeight", true) }
  };
  if (Number.isFinite(eff.MEd) && Number.isFinite(eff.VEd)) {
    payload.effects = { MEd_kNm: eff.MEd, VEd_kN: eff.VEd, delta_mm: eff.delta };
  }
  return payload;
}

function setText(id, text) { const n = el(id); if (n) n.textContent = text; }

// EC5 runs internally for the PDF, recommendation engine and the Member Schedule, but the
// detailed EC5 verification breakdown is NOT shown on screen — the Timber Results panel is
// kept to the clean summary (Grade·b×h, Mmax, Vmax, RL, RR, δmax, Control, Status).
async function applyTimberEc5Overlay() {
  if (value("memberMode", "beam") !== "timberBeam") return;
  const payload = buildEc5Payload();
  const apiResult = await calculateTimberBeam(payload);
  if (!apiResult.ok) return;
  const r = apiResult.payload.results || {};
  const defl = r.deflection || {};

  // Grade · b × h summary card.
  setText("timberGradeSize", (r.material && r.material.grade ? r.material.grade : "-") + " · " + (r.section ? (r.section.width_mm + " × " + r.section.depth_mm + " mm") : "-"));

  // Make EC5 the source for the displayed core checks and the schedule capture.
  setText("timberM", fmt(r.MEd_kNm, 3));
  setText("timberV", fmt(r.VEd_kN, 3));
  setText("timberDefl", fmt(defl.delta_max_mm, 2) + " (allow " + fmt(defl.delta_allow_mm, 2) + ")");
  setText("timberUtilDefl", fmt(r.utilization, 3));
  if (typeof window.setTimberResultStatus === "function") window.setTimberResultStatus(r.status_kind || "", r.status || "");

  // Cache the EC5 result so the Member Schedule captures EC5 values even though the
  // schedule's synchronous compute() reads the cards before this async overlay completes.
  window.__lastTimberEc5 = {
    control: fmt(r.utilization, 3),
    status: r.status || "",
    statusKind: r.status_kind || "",
    MEd: fmt(r.MEd_kNm, 3),
    VEd: fmt(r.VEd_kN, 3),
    deflStr: fmt(defl.delta_max_mm, 2) + " (allow " + fmt(defl.delta_allow_mm, 2) + ")"
  };
}

async function generateTimberBeamPdfReport() {
  if (value("memberMode", "beam") !== "timberBeam") return;
  if (typeof window.setStatus === "function") window.setStatus("", "Generating report...");
  const reportResult = await generateTimberBeamReport(buildEc5Payload());
  if (!reportResult.ok) {
    if (typeof window.setStatus === "function") window.setStatus("bad", "Timber PDF could not be generated.");
    return;
  }
  downloadBlob(reportResult.blob, reportResult.filename);
  if (typeof window.setStatus === "function") window.setStatus("ok", "Report generated");
}

export function initTimberBeamController() {
  // Overlay only — the original timber UI, computeTimber take-down and workflow are untouched.
  window.applyTimberEc5Overlay = applyTimberEc5Overlay;
  window.generateTimberBeamPdfReport = generateTimberBeamPdfReport;
}
