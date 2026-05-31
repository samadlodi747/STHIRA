import { el } from "../utils/dom.js";

function clearValidationState() {
  document.querySelectorAll(".is-invalid").forEach(function (node) {
    node.classList.remove("is-invalid");
    node.removeAttribute("aria-invalid");
    if (node.dataset && Object.prototype.hasOwnProperty.call(node.dataset, "validationTitle")) {
      const previousTitle = node.dataset.validationTitle;
      if (previousTitle) node.setAttribute("title", previousTitle);
      else node.removeAttribute("title");
      delete node.dataset.validationTitle;
    }
  });
}

function markInvalid(node, message) {
  if (!node) return;
  if (!node.classList.contains("is-invalid")) {
    node.dataset.validationTitle = node.getAttribute("title") || "";
  }
  node.classList.add("is-invalid");
  node.setAttribute("aria-invalid", "true");
  node.setAttribute("title", message);
}

function addError(errors, message, node) {
  if (errors.indexOf(message) === -1) errors.push(message);
  markInvalid(node, message);
}

function validateNumberNode(node, errors, options) {
  const opts = options || {};
  const label = opts.label || "Input";
  if (!node) {
    if (opts.required) addError(errors, label + " is missing.", null);
    return null;
  }

  const raw = String(node.value == null ? "" : node.value).trim();
  if (raw === "") {
    if (opts.required) addError(errors, opts.emptyMessage || label + " is required.", node);
    return null;
  }

  const parsed = Number(raw);
  if (!Number.isFinite(parsed)) {
    addError(errors, opts.numberMessage || label + " must be a valid finite number.", node);
    return null;
  }

  if (opts.gtZero && !(parsed > 0)) {
    addError(errors, opts.gtZeroMessage || label + " must be greater than zero.", node);
  }
  if (opts.geZero && !(parsed >= 0)) {
    addError(errors, opts.geZeroMessage || label + " cannot be negative.", node);
  }
  return parsed;
}

export function validateSteelColumnInputs() {
  const errors = [];
  clearValidationState();

  const profile = el("profile");
  if (!profile || !profile.value) {
    addError(errors, "Select a valid steel column section.", profile);
  }

  validateNumberNode(el("fy"), errors, {
    label: "Steel yield strength",
    required: true,
    gtZero: true,
    emptyMessage: "Steel yield strength must be greater than 0 MPa.",
    numberMessage: "Steel yield strength must be a valid number in MPa.",
    gtZeroMessage: "Steel yield strength must be greater than 0 MPa."
  });
  validateNumberNode(el("E"), errors, {
    label: "Young's modulus",
    required: true,
    gtZero: true,
    emptyMessage: "Young's modulus must be greater than 0 GPa.",
    numberMessage: "Young's modulus must be a valid number in GPa.",
    gtZeroMessage: "Young's modulus must be greater than 0 GPa."
  });
  validateNumberNode(el("colL"), errors, {
    label: "Column length",
    required: true,
    gtZero: true,
    emptyMessage: "Column length must be greater than zero.",
    numberMessage: "Column length must be a valid number in metres.",
    gtZeroMessage: "Column length must be greater than zero."
  });
  validateNumberNode(el("colLy"), errors, {
    label: "Buckling length y",
    required: true,
    gtZero: true,
    gtZeroMessage: "Column buckling lengths must be greater than zero."
  });
  validateNumberNode(el("colLz"), errors, {
    label: "Buckling length z",
    required: true,
    gtZero: true,
    gtZeroMessage: "Column buckling lengths must be greater than zero."
  });
  validateNumberNode(el("colLlt"), errors, {
    label: "LTB length",
    required: true,
    geZero: true,
    geZeroMessage: "Column LTB length cannot be negative."
  });
  validateNumberNode(el("colDeflLimit"), errors, {
    label: "Deflection limit",
    required: true,
    gtZero: true,
    gtZeroMessage: "Deflection limit ratio must be greater than zero."
  });
  validateNumberNode(el("colGammaM0"), errors, {
    label: "gamma M0",
    required: true,
    gtZero: true,
    gtZeroMessage: "Partial factor gamma M0 must be greater than zero."
  });
  validateNumberNode(el("colGammaM1"), errors, {
    label: "gamma M1",
    required: true,
    gtZero: true,
    gtZeroMessage: "Partial factor gamma M1 must be greater than zero."
  });

  ["c_perm_N", "c_snow_N", "c_wind_N", "c_var_N"].forEach(function (id) {
    validateNumberNode(el(id), errors, {
      label: "Column axial load",
      required: true,
      geZero: true,
      emptyMessage: "Column load values must be provided.",
      numberMessage: "Column load values must be valid finite numbers.",
      geZeroMessage: "Column load values cannot be negative."
    });
  });

  return { valid: errors.length === 0, errors: errors };
}

