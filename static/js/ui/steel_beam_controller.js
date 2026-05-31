import { calculateSteelBeam, generateSteelBeamReport } from "../api/steel_beam_api.js";
import {
  isCurrentRequest,
  nextRequestId,
  setLoadingState,
  setQueuedCalculation,
  setReportLoadingState,
  steelBeamState,
  storeResults,
  storeValidationErrors
} from "../state/app_state.js";
import { value } from "../utils/dom.js";
import { DEBUG_STEEL_BEAM_API } from "../utils/debug.js";
import { downloadBlob } from "../utils/download.js";
import { paintApiFailure, paintResults, paintValidationErrors, paintWarnings, setCalculateButtonBusy, setReportButtonBusy, setWorkflowStatus } from "../rendering/steel_beam_renderer.js";
import { validateSteelBeamInputs } from "../validation/steel_beam_validation.js";
import { buildSteelBeamPayload } from "./steel_beam_form.js";

export function initSteelBeamController() {
  const legacyCompute = typeof window.compute === "function" ? window.compute : null;
  window.__STEEL_BEAM_API_ADAPTER_ACTIVE = true;

  async function computeSteelBeamViaApi() {
    if (steelBeamState.isCalculating) {
      setQueuedCalculation(true);
      return;
    }

    const validation = validateSteelBeamInputs();
    if (!validation.valid) {
      storeValidationErrors(validation.errors);
      if (DEBUG_STEEL_BEAM_API) console.log("[steel-beam] frontend validation failure", validation.errors);
      paintValidationErrors(validation.errors);
      return;
    }

    const requestId = nextRequestId();
    const payload = buildSteelBeamPayload();
    setLoadingState(true);
    setCalculateButtonBusy(true);
    setWorkflowStatus("", "Calculating...");
    paintWarnings([], []);

    const apiResult = await calculateSteelBeam(payload);
    if (!isCurrentRequest(requestId)) return;

    try {
      if (!apiResult.ok) {
        paintApiFailure(apiResult.payload, apiResult.statusCode);
        return;
      }
      storeResults(apiResult.payload);
      paintResults(apiResult.payload);
    } finally {
      if (isCurrentRequest(requestId)) {
        setLoadingState(false);
        setCalculateButtonBusy(false);
        if (steelBeamState.queuedCalculation) {
          setQueuedCalculation(false);
          computeSteelBeamViaApi();
        }
      }
    }
  }

  function computeRouter() {
    const mode = value("memberMode", "beam");
    steelBeamState.currentMode = mode;
    if (mode === "beam") {
      computeSteelBeamViaApi();
      return;
    }
    if (mode === "columnK" && typeof window.computeSteelColumnViaApi === "function") {
      window.computeSteelColumnViaApi();
      return;
    }
    if (legacyCompute) legacyCompute();
  }

  async function generateSteelBeamPdfReport() {
    if (steelBeamState.isReportGenerating) return;

    const mode = value("memberMode", "beam");
    if (mode !== "beam") {
      paintWarnings([], ["PDF report export is currently available for steel beam mode."]);
      return;
    }

    const validation = validateSteelBeamInputs();
    if (!validation.valid) {
      storeValidationErrors(validation.errors);
      if (DEBUG_STEEL_BEAM_API) console.log("[steel-beam-report] frontend validation failure", validation.errors);
      paintValidationErrors(validation.errors);
      return;
    }

    const payload = buildSteelBeamPayload();
    setReportLoadingState(true);
    setReportButtonBusy(true);
    setWorkflowStatus("", "Generating report...");

    try {
      const reportResult = await generateSteelBeamReport(payload);
      if (!reportResult.ok) {
        paintApiFailure(reportResult.payload, reportResult.statusCode);
        return;
      }
      downloadBlob(reportResult.blob, reportResult.filename);
      setWorkflowStatus("ok", "Report generated");
      paintWarnings([], []);
    } finally {
      setReportLoadingState(false);
      setReportButtonBusy(false);
    }
  }

  function generateActivePdfReport() {
    const mode = value("memberMode", "beam");
    if (mode === "beam") {
      generateSteelBeamPdfReport();
      return;
    }
    if (mode === "columnK" && typeof window.generateSteelColumnPdfReport === "function") {
      window.generateSteelColumnPdfReport();
      return;
    }
    paintWarnings([], ["PDF report export is currently available for steel beam and steel column modes."]);
  }

  function bindReportButton() {
    const button = document.getElementById("btnSteelBeamReport");
    if (!button || button.dataset.steelBeamReportBound === "true") return;
    button.dataset.steelBeamReportBound = "true";
    button.addEventListener("click", function () {
      generateActivePdfReport();
    });
  }

  try {
    window.computeBeam = computeSteelBeamViaApi;
    window.computeSteelBeamViaApi = computeSteelBeamViaApi;
    window.generateSteelBeamPdfReport = generateSteelBeamPdfReport;
    window.compute = computeRouter;
    bindReportButton();
  } catch (error) {
    paintWarnings([], ["Could not attach FastAPI steel beam adapter: " + error.message]);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", function () {
      bindReportButton();
      computeRouter();
    });
  } else {
    computeRouter();
  }
}
