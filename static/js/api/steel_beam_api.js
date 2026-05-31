import { DEBUG_STEEL_BEAM_API } from "../utils/debug.js";

const API_ENDPOINT = "/calculate/steel-beam";
const REPORT_ENDPOINT = "/reports/steel-beam";

export async function calculateSteelBeam(payload) {
  if (DEBUG_STEEL_BEAM_API) console.log("[steel-beam] request payload", payload);

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
        errors: ["Steel beam API returned invalid JSON."]
      };
    });

    if (DEBUG_STEEL_BEAM_API) console.log("[steel-beam] response payload", responsePayload);

    return {
      ok: response.ok && responsePayload.success === true,
      statusCode: response.status,
      payload: responsePayload
    };
  } catch (error) {
    const message = error && error.message ? error.message : String(error);
    console.log("[steel-beam] API failure", message);
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
  if (typeof disposition !== "string") return "steel_beam_report.pdf";
  const match = disposition.match(/filename\*?=(?:UTF-8''|")?([^";]+)/i);
  if (!match || !match[1]) return "steel_beam_report.pdf";
  return decodeURIComponent(match[1].replace(/"/g, "").trim());
}

export async function generateSteelBeamReport(payload) {
  if (DEBUG_STEEL_BEAM_API) console.log("[steel-beam-report] request payload", payload);

  try {
    const response = await fetch(REPORT_ENDPOINT, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });

    if (response.ok) {
      const blob = await response.blob();
      const filename = filenameFromDisposition(response.headers.get("Content-Disposition"));
      if (DEBUG_STEEL_BEAM_API) {
        console.log("[steel-beam-report] response blob", {
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
        errors: ["Steel beam report API returned an invalid error response."]
      };
    });
    if (DEBUG_STEEL_BEAM_API) console.log("[steel-beam-report] error response", responsePayload);
    return {
      ok: false,
      statusCode: response.status,
      payload: responsePayload
    };
  } catch (error) {
    const message = error && error.message ? error.message : String(error);
    console.log("[steel-beam-report] API failure", message);
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

export function friendlyFallbackFromStatus(statusCode) {
  if (statusCode === 422) return "One or more steel beam inputs are invalid. Check the highlighted fields.";
  if (statusCode === 404) return "Steel beam calculation service was not found.";
  if (statusCode >= 500) return "The calculation service encountered a backend error.";
  return "Steel beam API calculation failed.";
}

export function sanitizeApiMessage(message, statusCode) {
  if (typeof message !== "string" || !message.trim()) return friendlyFallbackFromStatus(statusCode);
  const text = message.trim();
  const lower = text.toLowerCase();

  if (lower.indexOf("traceback") !== -1 || lower.indexOf("stack trace") !== -1 || lower.indexOf("file \"") !== -1) {
    return friendlyFallbackFromStatus(statusCode);
  }
  if (text.indexOf("body.") === 0 || lower.indexOf("input should") !== -1 || lower.indexOf("field required") !== -1) {
    if (lower.indexOf("fy_mpa") !== -1) return "Steel yield strength must be greater than 0 MPa.";
    if (lower.indexOf("e_gpa") !== -1) return "Young's modulus must be greater than 0 GPa.";
    if (lower.indexOf("span_m") !== -1) return "Span must be greater than zero.";
    if (lower.indexOf("support_width_cm") !== -1) return "Support width must be greater than zero when provided.";
    if (lower.indexOf("direct_w_kn_m") !== -1 || lower.indexOf("w_kn_m") !== -1 || lower.indexOf("p_kn") !== -1) {
      return "Load values cannot be negative.";
    }
    return friendlyFallbackFromStatus(statusCode);
  }
  return text;
}

export function normalizeApiErrors(payload, statusCode) {
  const source = payload && Array.isArray(payload.errors) ? payload.errors : [];
  const errors = source.map(function (item) {
    return sanitizeApiMessage(item, statusCode);
  }).filter(Boolean);
  if (!errors.length) errors.push(friendlyFallbackFromStatus(statusCode));
  return errors.filter(function (item, index) { return errors.indexOf(item) === index; });
}
