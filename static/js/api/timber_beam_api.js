const API_ENDPOINT = "/calculate/timber-beam";
const REPORT_ENDPOINT = "/reports/timber-beam";
const OPTIONS_ENDPOINT = "/timber/options";

export async function fetchTimberOptions() {
  try {
    const response = await fetch(OPTIONS_ENDPOINT);
    const payload = await response.json().catch(function () { return null; });
    if (response.ok && payload && payload.success) return payload.results || {};
  } catch (error) {
    console.log("[timber-beam] options fetch failed", error && error.message ? error.message : String(error));
  }
  return { grades: [], sections: [] };
}

export async function calculateTimberBeam(payload) {
  try {
    const response = await fetch(API_ENDPOINT, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });
    const responsePayload = await response.json().catch(function () {
      return { success: false, results: {}, warnings: [], errors: ["Timber beam API returned invalid JSON."] };
    });
    return { ok: response.ok && responsePayload.success === true, statusCode: response.status, payload: responsePayload };
  } catch (error) {
    const message = error && error.message ? error.message : String(error);
    return { ok: false, statusCode: 500, payload: { success: false, results: {}, warnings: [], errors: [message] } };
  }
}

function filenameFromDisposition(disposition) {
  if (typeof disposition !== "string") return "timber_beam_report.pdf";
  const match = disposition.match(/filename\*?=(?:UTF-8''|")?([^";]+)/i);
  if (!match || !match[1]) return "timber_beam_report.pdf";
  return decodeURIComponent(match[1].replace(/"/g, "").trim());
}

export async function generateTimberBeamReport(payload) {
  try {
    const response = await fetch(REPORT_ENDPOINT, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });
    if (response.ok) {
      const blob = await response.blob();
      const filename = filenameFromDisposition(response.headers.get("Content-Disposition"));
      return { ok: true, statusCode: response.status, filename: filename, blob: blob, payload: { success: true } };
    }
    const responsePayload = await response.json().catch(function () {
      return { success: false, results: {}, warnings: [], errors: ["Timber beam report API returned an invalid error response."] };
    });
    return { ok: false, statusCode: response.status, payload: responsePayload };
  } catch (error) {
    const message = error && error.message ? error.message : String(error);
    return { ok: false, statusCode: 500, payload: { success: false, results: {}, warnings: [], errors: [message] } };
  }
}

export function normalizeTimberApiErrors(payload, statusCode) {
  const source = payload && Array.isArray(payload.errors) ? payload.errors : [];
  const errors = source.filter(Boolean);
  if (!errors.length) {
    if (statusCode === 422) errors.push("One or more timber beam inputs are invalid. Check the highlighted fields.");
    else if (statusCode >= 500) errors.push("The timber calculation service encountered a backend error.");
    else errors.push("Timber beam API calculation failed.");
  }
  return errors.filter(function (item, index) { return errors.indexOf(item) === index; });
}
