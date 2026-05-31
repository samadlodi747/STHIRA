export const steelBeamState = {
  requestCounter: 0,
  isCalculating: false,
  isReportGenerating: false,
  queuedCalculation: false,
  currentMode: "beam",
  apiStatus: "idle",
  currentResults: null,
  validationErrors: [],
  warnings: [],
  recommendations: []
};

export const steelColumnState = {
  requestCounter: 0,
  isCalculating: false,
  isReportGenerating: false,
  queuedCalculation: false,
  currentMode: "columnK",
  apiStatus: "idle",
  currentResults: null,
  validationErrors: [],
  warnings: [],
  recommendations: []
};

export function nextRequestId() {
  steelBeamState.requestCounter += 1;
  return steelBeamState.requestCounter;
}

export function isCurrentRequest(requestId) {
  return requestId === steelBeamState.requestCounter;
}

export function setLoadingState(isLoading) {
  steelBeamState.isCalculating = !!isLoading;
  steelBeamState.apiStatus = isLoading ? "loading" : "idle";
}

export function setReportLoadingState(isLoading) {
  steelBeamState.isReportGenerating = !!isLoading;
}

export function setQueuedCalculation(value) {
  steelBeamState.queuedCalculation = !!value;
}

export function storeResults(payload) {
  const results = payload && payload.results ? payload.results : null;
  steelBeamState.currentResults = results;
  steelBeamState.warnings = (payload && payload.warnings) || (results && results.warnings) || [];
  steelBeamState.recommendations = (results && results.recommendations) || [];
}

export function storeValidationErrors(errors) {
  steelBeamState.validationErrors = Array.isArray(errors) ? errors : [];
}

export function nextColumnRequestId() {
  steelColumnState.requestCounter += 1;
  return steelColumnState.requestCounter;
}

export function isCurrentColumnRequest(requestId) {
  return requestId === steelColumnState.requestCounter;
}

export function setColumnLoadingState(isLoading) {
  steelColumnState.isCalculating = !!isLoading;
  steelColumnState.apiStatus = isLoading ? "loading" : "idle";
}

export function setColumnReportLoadingState(isLoading) {
  steelColumnState.isReportGenerating = !!isLoading;
}

export function setColumnQueuedCalculation(value) {
  steelColumnState.queuedCalculation = !!value;
}

export function storeColumnResults(payload) {
  const results = payload && payload.results ? payload.results : null;
  steelColumnState.currentResults = results;
  steelColumnState.warnings = (payload && payload.warnings) || (results && results.warnings) || [];
  steelColumnState.recommendations = (results && results.recommendations) || [];
}

export function storeColumnValidationErrors(errors) {
  steelColumnState.validationErrors = Array.isArray(errors) ? errors : [];
}
