import { calculateSteelColumn, generateSteelColumnReport } from "../api/steel_column_api.js";
import {
  isCurrentColumnRequest,
  nextColumnRequestId,
  setColumnLoadingState,
  setColumnQueuedCalculation,
  setColumnReportLoadingState,
  steelColumnState,
  storeColumnResults,
  storeColumnValidationErrors
} from "../state/app_state.js";
import { downloadBlob } from "../utils/download.js";
import {
  paintColumnApiFailure,
  paintColumnResults,
  paintColumnValidationErrors,
  paintColumnWarnings,
  setColumnCalculateButtonBusy,
  setColumnReportButtonBusy,
  setColumnWorkflowStatus
} from "../rendering/steel_column_renderer.js";
import { validateSteelColumnInputs } from "../validation/steel_column_validation.js";
import { buildSteelColumnPayload } from "./steel_column_form.js";

export function initSteelColumnController() {
  async function computeSteelColumnViaApi() {
    if (steelColumnState.isCalculating) {
      setColumnQueuedCalculation(true);
      return;
    }

    const validation = validateSteelColumnInputs();
    if (!validation.valid) {
      storeColumnValidationErrors(validation.errors);
      console.log("[steel-column] frontend validation failure", validation.errors);
      paintColumnValidationErrors(validation.errors);
      return;
    }

    const requestId = nextColumnRequestId();
    const payload = buildSteelColumnPayload();
    setColumnLoadingState(true);
    setColumnCalculateButtonBusy(true);
    setColumnWorkflowStatus("", "Calculating...");
    paintColumnWarnings([], []);

    const apiResult = await calculateSteelColumn(payload);
    if (!isCurrentColumnRequest(requestId)) return;

    try {
      if (!apiResult.ok) {
        paintColumnApiFailure(apiResult.payload, apiResult.statusCode);
        return;
      }
      storeColumnResults(apiResult.payload);
      paintColumnResults(apiResult.payload);
    } finally {
      if (isCurrentColumnRequest(requestId)) {
        setColumnLoadingState(false);
        setColumnCalculateButtonBusy(false);
        if (steelColumnState.queuedCalculation) {
          setColumnQueuedCalculation(false);
          computeSteelColumnViaApi();
        }
      }
    }
  }

  async function generateSteelColumnPdfReport() {
    if (steelColumnState.isReportGenerating) return;

    const validation = validateSteelColumnInputs();
    if (!validation.valid) {
      storeColumnValidationErrors(validation.errors);
      console.log("[steel-column-report] frontend validation failure", validation.errors);
      paintColumnValidationErrors(validation.errors);
      return;
    }

    const payload = buildSteelColumnPayload();
    setColumnReportLoadingState(true);
    setColumnReportButtonBusy(true);
    setColumnWorkflowStatus("", "Generating report...");

    try {
      const reportResult = await generateSteelColumnReport(payload);
      if (!reportResult.ok) {
        paintColumnApiFailure(reportResult.payload, reportResult.statusCode);
        return;
      }
      downloadBlob(reportResult.blob, reportResult.filename);
      setColumnWorkflowStatus("ok", "Report generated");
      paintColumnWarnings([], []);
    } finally {
      setColumnReportLoadingState(false);
      setColumnReportButtonBusy(false);
    }
  }

  window.computeSteelColumnViaApi = computeSteelColumnViaApi;
  window.generateSteelColumnPdfReport = generateSteelColumnPdfReport;
}

