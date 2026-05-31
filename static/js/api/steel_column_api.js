const API_ENDPOINT = "/calculate/steel-column";
const REPORT_ENDPOINT = "/reports/steel-column";
const DEBUG_STEEL_COLUMN_API = true;

export async function calculateSteelColumn(payload) {
  if (DEBUG_STEEL_COLUMN_API) console.log("[steel-column] request payload", payload);

  try {
    const response = await fetch(API_ENDPOINT, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });
    const responsePayload = await response.json().catch(function () {
      return {
        success: false,
        results: {},
        warnings: [],
        errors: ["Steel column API returned invalid JSON."]
      };
    });
    if (DEBUG_STEEL_COLUMN_API) console.log("[steel-column] response payload", responsePayload);
    return {
      ok: response.ok && responsePayload.success === true,
      statusCode: response.status,
      payload: responsePayload
    };
  } catch (error) {
    const message = error && error.message ? error.message : String(error);
    console.log("[steel-column] API failure", message);
    return {
      ok: false,
      statusCode: 500,
      payload: {
        success: false,
        results: {},
        warnings: [],
        errors: [message]
      }
    };
  }
}

function filenameFromDisposition(disposition) {
  if (typeof disposition !== "string") return "steel_column_report.pdf";
  const match = disposition.match(/filename\*?=(?:UTF-8''|")?([^";]+)/i);
  if (!match || !match[1]) return "steel_column_report.pdf";
  return decodeURIComponent(match[1].replace(/"/g, "").trim());
}

export async function generateSteelColumnReport(payload) {
  if (DEBUG_STEEL_COLUMN_API) console.log("[steel-column-report] request payload", payload);

  try {
    const response = await fetch(REPORT_ENDPOINT, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });

    if (response.ok) {
      const blob = await response.blob();
      const filename = filenameFromDisposition(response.headers.get("Content-Disposition"));
      if (DEBUG_STEEL_COLUMN_API) {
        console.log("[steel-column-report] response blob", {
          filename: filename,
          size: blob.size,
          type: blob.type
        });
      }
      return {
        ok: true,
        statusCode: response.status,
        filename: filename,
        blob: blob,
        payload: { success: true, results: {}, warnings: [], errors: [] }
      };
    }

    const responsePayload = await response.json().catch(function () {
      return {
        success: false,
        results: {},
        warnings: [],
        errors: ["Steel column report API returned an invalid error response."]
      };
    });
    if (DEBUG_STEEL_COLUMN_API) console.log("[steel-column-report] error response", responsePayload);
    return {
      ok: false,
      statusCode: response.status,
      payload: responsePayload
    };
  } catch (error) {
    const message = error && error.message ? error.message : String(error);
    console.log("[steel-column-report] API failure", message);
    return {
      ok: false,
      statusCode: 500,
      payload: {
        success: false,
        results: {},
        warnings: [],
        errors: [message]
      }
    };
  }
}

function friendlyFallbackFromStatus(statusCode) {
  if (statusCode === 422) return "One or more steel column inputs are invalid. Check the highlighted fields.";
  if (statusCode === 404) return "Steel column calculation service was not found.";
  if (statusCode >= 500) return "The column calculation service encountered a backend error.";
  return "Steel column API calculation failed.";
}

export function sanitizeColumnApiMessage(message, statusCode) {
  if (typeof message !== "string" || !message.trim()) return friendlyFallbackFromStatus(statusCode);
  const text = message.trim();
  const lower = text.toLowerCase();

  if (lower.indexOf("traceback") !== -1 || lower.indexOf("stack trace") !== -1 || lower.indexOf("file \"") !== -1) {
    return friendlyFallbackFromStatus(statusCode);
  }
  if (text.indexOf("body.") === 0 || lower.indexOf("input should") !== -1 || lower.indexOf("field required") !== -1) {
    if (lower.indexOf("length_m") !== -1) return "Column length must be greater than zero.";
    if (lower.indexOf("buckling_length") !== -1) return "Column buckling lengths must be greater than zero.";
    if (lower.indexOf("fy_mpa") !== -1) return "Steel yield strength must be greater than 0 MPa.";
    if (lower.indexOf("e_gpa") !== -1) return "Young's modulus must be greater than 0 GPa.";
    if (lower.indexOf("n_kn") !== -1) return "Column load values cannot be negative.";
    return friendlyFallbackFromStatus(statusCode);
  }
  return text;
}

export function normalizeColumnApiErrors(payload, statusCode) {
  const source = payload && Array.isArray(payload.errors) ? payload.errors : [];
  const errors = source.map(function (item) {
    return sanitizeColumnApiMessage(item, statusCode);
  }).filter(Boolean);
  if (!errors.length) errors.push(friendlyFallbackFromStatus(statusCode));
  return errors.filter(function (item, index) { return errors.indexOf(item) === index; });
}

