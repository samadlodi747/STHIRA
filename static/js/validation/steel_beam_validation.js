import { checked, el, value } from "../utils/dom.js";

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
    if (opts.required) {
      addError(errors, opts.emptyMessage || label + " is required.", node);
    }
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
  if (opts.ltValue !== undefined && !(parsed < opts.ltValue)) {
    addError(errors, opts.ltMessage || label + " is outside the allowed range.", node);
  }
  if (opts.leValue !== undefined && !(parsed <= opts.leValue)) {
    addError(errors, opts.leMessage || label + " is outside the allowed range.", node);
  }
  return parsed;
}

export function validateSteelBeamInputs() {
  const errors = [];
  clearValidationState();

  const profile = el("profile");
  if (!profile || !profile.value) {
    addError(errors, "Select a valid steel section.", profile);
  }

  const fy = validateNumberNode(el("fy"), errors, {
    label: "Steel yield strength",
    required: true,
    gtZero: true,
    emptyMessage: "Steel yield strength must be greater than 0 MPa.",
    numberMessage: "Steel yield strength must be a valid number in MPa.",
    gtZeroMessage: "Steel yield strength must be greater than 0 MPa."
  });

  const youngsModulus = validateNumberNode(el("E"), errors, {
    label: "Young's modulus",
    required: true,
    gtZero: true,
    emptyMessage: "Young's modulus must be greater than 0 GPa.",
    numberMessage: "Young's modulus must be a valid number in GPa.",
    gtZeroMessage: "Young's modulus must be greater than 0 GPa."
  });

  const span = validateNumberNode(el("L"), errors, {
    label: "Span",
    required: true,
    gtZero: true,
    emptyMessage: "Span must be greater than zero.",
    numberMessage: "Span must be a valid number in metres.",
    gtZeroMessage: "Span must be greater than zero."
  });

  validateNumberNode(el("gammaM0"), errors, {
    label: "gamma M0",
    required: true,
    gtZero: true,
    gtZeroMessage: "Partial factor gamma M0 must be greater than zero."
  });

  validateNumberNode(el("deflLimit"), errors, {
    label: "Deflection limit",
    required: true,
    gtZero: true,
    gtZeroMessage: "Deflection limit ratio must be greater than zero."
  });

  const leftSupportWidth = el("beamLeftSupportWidthCm");
  if (leftSupportWidth && String(leftSupportWidth.value || "").trim() !== "") {
    validateNumberNode(leftSupportWidth, errors, {
      label: "Left support width",
      gtZero: true,
      gtZeroMessage: "Left support width must be greater than zero when provided."
    });
  }

  const rightSupportWidth = el("beamRightSupportWidthCm");
  if (rightSupportWidth && String(rightSupportWidth.value || "").trim() !== "") {
    validateNumberNode(rightSupportWidth, errors, {
      label: "Right support width",
      gtZero: true,
      gtZeroMessage: "Right support width must be greater than zero when provided."
    });
  }

  const loadMode = value("loadMode", "direct");
  if (loadMode === "direct") {
    validateNumberNode(el("w"), errors, {
      label: "UDL load",
      required: true,
      geZero: true,
      emptyMessage: "UDL load must be provided.",
      numberMessage: "Load values must be valid finite numbers.",
      geZeroMessage: "Load values cannot be negative."
    });
  } else {
    validateNumberNode(el("gammaG"), errors, {
      label: "gamma G",
      required: true,
      geZero: true,
      geZeroMessage: "Load factors cannot be negative."
    });
    validateNumberNode(el("gammaQ"), errors, {
      label: "gamma Q",
      required: true,
      geZero: true,
      geZeroMessage: "Load factors cannot be negative."
    });
    ["psi0_live", "psi1_live", "psi2_live", "psi0_wind", "psi1_wind", "psi2_wind", "psi0_snow", "psi1_snow", "psi2_snow"].forEach(function (id) {
      validateNumberNode(el(id), errors, {
        label: "Combination factor",
        required: true,
        geZero: true,
        geZeroMessage: "Combination factors cannot be negative."
      });
    });

    const udlHost = el("udlRows");
    if (udlHost) {
      Array.from(udlHost.children).forEach(function (row) {
        const input = row.querySelector("input");
        if (!input || input.readOnly) return;
        validateNumberNode(input, errors, {
          label: "Line load",
          required: true,
          geZero: true,
          emptyMessage: "Line load values must be provided.",
          numberMessage: "Load values must be valid finite numbers.",
          geZeroMessage: "Load values cannot be negative."
        });
      });
    }
  }

  const pointHost = el("plRows");
  if (pointHost) {
    Array.from(pointHost.children).forEach(function (row) {
      const inputs = row.querySelectorAll("input");
      const loadInput = inputs[0];
      const positionInput = inputs[1];
      validateNumberNode(loadInput, errors, {
        label: "Point load",
        required: true,
        geZero: true,
        emptyMessage: "Point load values must be provided.",
        numberMessage: "Load values must be valid finite numbers.",
        geZeroMessage: "Load values cannot be negative."
      });
      const position = validateNumberNode(positionInput, errors, {
        label: "Point load position",
        required: true,
        geZero: true,
        emptyMessage: "Point load position must be provided.",
        geZeroMessage: "Point load position cannot be negative."
      });
      if (Number.isFinite(span) && Number.isFinite(position) && position > span) {
        addError(errors, "Point load position must lie within the beam span.", positionInput);
      }
    });
  }

  const autoFloorHost = el("beamAutoFloorRows");
  if (autoFloorHost) {
    Array.from(autoFloorHost.children).forEach(function (row) {
      const inputs = row.querySelectorAll("input");
      [inputs[1], inputs[2], inputs[3]].forEach(function (input) {
        validateNumberNode(input, errors, {
          label: "Automatic floor load input",
          required: true,
          geZero: true,
          numberMessage: "Automatic load take-down values must be valid finite numbers.",
          geZeroMessage: "Automatic load take-down dimensions and loads cannot be negative."
        });
      });
    });
  }

  const autoWallHost = el("beamAutoWallRows");
  if (autoWallHost) {
    Array.from(autoWallHost.children).forEach(function (row) {
      const inputs = row.querySelectorAll("input");
      [inputs[1], inputs[2], inputs[3], inputs[4]].forEach(function (input) {
        validateNumberNode(input, errors, {
          label: "Automatic wall load input",
          required: true,
          geZero: true,
          numberMessage: "Automatic wall load values must be valid finite numbers.",
          geZeroMessage: "Automatic load take-down dimensions and loads cannot be negative."
        });
      });
    });
  }

  validateNumberNode(el("Lb"), errors, {
    label: "Unbraced length",
    required: true,
    geZero: true,
    geZeroMessage: "Unbraced length cannot be negative."
  });
  if (checked("checkLTB", false)) {
    validateNumberNode(el("Lb"), errors, {
      label: "Unbraced length",
      required: true,
      gtZero: true,
      gtZeroMessage: "Unbraced length must be greater than zero when LTB is enabled."
    });
  }
  validateNumberNode(el("C1"), errors, {
    label: "LTB moment factor C1",
    required: true,
    gtZero: true,
    gtZeroMessage: "LTB moment factor C1 must be greater than zero."
  });
  validateNumberNode(el("alphaLT"), errors, {
    label: "LTB imperfection factor",
    required: true,
    geZero: true,
    geZeroMessage: "LTB imperfection factor cannot be negative."
  });
  validateNumberNode(el("gammaM1"), errors, {
    label: "gamma M1",
    required: true,
    gtZero: true,
    gtZeroMessage: "Partial factor gamma M1 must be greater than zero."
  });
  validateNumberNode(el("lambdaLT0"), errors, {
    label: "LTB lambda LT0",
    required: true,
    geZero: true,
    geZeroMessage: "LTB lambda LT0 cannot be negative."
  });
  validateNumberNode(el("betaLT"), errors, {
    label: "LTB beta",
    required: true,
    geZero: true,
    geZeroMessage: "LTB beta cannot be negative."
  });
  validateNumberNode(el("nu"), errors, {
    label: "Poisson ratio",
    required: true,
    geZero: true,
    ltValue: 0.5,
    geZeroMessage: "Poisson ratio cannot be negative.",
    ltMessage: "Poisson ratio must be less than 0.5."
  });

  if (!Number.isFinite(fy) || !Number.isFinite(youngsModulus) || !Number.isFinite(span)) {
    return { valid: false, errors: errors };
  }

  return { valid: errors.length === 0, errors: errors };
}
