import { el } from "../../utils/dom.js";
import { fmt } from "../../utils/format.js";

const DEFAULT_RANGE_TEXT = "-";

function finiteNumber(value) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function finiteSeries(values) {
  return Array.isArray(values)
    ? values.map(finiteNumber).filter(function (value) { return value !== null; })
    : [];
}

function minMax(values) {
  const clean = finiteSeries(values);
  if (!clean.length) return null;
  return {
    min: Math.min.apply(null, clean),
    max: Math.max.apply(null, clean)
  };
}

function clearCanvas(canvas) {
  if (!canvas) return;
  const context = canvas.getContext("2d");
  if (!context) return;
  context.clearRect(0, 0, canvas.width || 0, canvas.height || 0);
}

function setRangeText(rangeId, text) {
  const node = el(rangeId);
  if (node) node.textContent = text || DEFAULT_RANGE_TEXT;
}

function configureCanvas(canvas) {
  const rect = canvas.getBoundingClientRect();
  const parentWidth = canvas.parentElement ? canvas.parentElement.clientWidth : 0;
  const cssWidth = Math.max(rect.width || parentWidth || 720, 320);
  const cssHeight = Math.max(rect.height || 210, 180);
  const ratio = window.devicePixelRatio || 1;

  canvas.width = Math.round(cssWidth * ratio);
  canvas.height = Math.round(cssHeight * ratio);

  const context = canvas.getContext("2d");
  context.setTransform(ratio, 0, 0, ratio, 0, 0);
  return { context: context, width: cssWidth, height: cssHeight };
}

function drawGrid(context, plot) {
  context.lineWidth = 1;
  context.strokeStyle = "rgba(255,255,255,0.10)";

  for (let index = 0; index <= 6; index += 1) {
    const x = plot.left + (index * plot.width) / 6;
    context.beginPath();
    context.moveTo(x, plot.top);
    context.lineTo(x, plot.bottom);
    context.stroke();
  }

  for (let index = 0; index <= 5; index += 1) {
    const y = plot.top + (index * plot.height) / 5;
    context.beginPath();
    context.moveTo(plot.left, y);
    context.lineTo(plot.right, y);
    context.stroke();
  }
}

function drawLabels(context, plot, options) {
  const fontFamily = getComputedStyle(document.documentElement).getPropertyValue("--mono") || "monospace";
  context.fillStyle = "rgba(255,255,255,0.74)";
  context.font = "12px " + fontFamily;
  context.textAlign = "left";
  context.fillText(options.yLabel || "", 10, 24);
  context.textAlign = "center";
  context.fillText(options.xLabel || "x (m)", (plot.left + plot.right) / 2, plot.canvasHeight - 10);
}

function drawZeroAxis(context, plot, yToPx) {
  if (!(plot.yMin < 0 && plot.yMax > 0)) return;
  const y0 = yToPx(0);
  context.strokeStyle = "rgba(255,255,255,0.28)";
  context.lineWidth = 1.25;
  context.beginPath();
  context.moveTo(plot.left, y0);
  context.lineTo(plot.right, y0);
  context.stroke();
}

function markerIndex(marker, yValues) {
  if (marker && Number.isInteger(marker.index) && marker.index >= 0 && marker.index < yValues.length) {
    return marker.index;
  }
  if (!yValues.length) return null;
  let best = 0;
  for (let index = 1; index < yValues.length; index += 1) {
    if (Math.abs(yValues[index]) > Math.abs(yValues[best])) best = index;
  }
  return best;
}

function drawMarker(context, plot, xToPx, yToPx, xValues, yValues, marker, options) {
  const index = markerIndex(marker, yValues);
  if (index === null) return;
  const x = finiteNumber(xValues[index]);
  const y = finiteNumber(yValues[index]);
  if (x === null || y === null) return;

  const px = xToPx(x);
  const py = yToPx(y);
  context.fillStyle = options.markerColor || "rgba(255,209,102,0.95)";
  context.strokeStyle = "rgba(0,0,0,0.42)";
  context.lineWidth = 2;
  context.beginPath();
  context.arc(px, py, 4.5, 0, Math.PI * 2);
  context.fill();
  context.stroke();

  const exact = finiteNumber(marker && marker.abs_value);
  if (exact === null) return;
  const label = "max " + fmt(exact, options.digits || 3) + " " + (options.unit || "");
  context.font = "12px " + (getComputedStyle(document.documentElement).getPropertyValue("--mono") || "monospace");
  context.fillStyle = "rgba(255,255,255,0.82)";
  context.textAlign = px > (plot.left + plot.right) / 2 ? "right" : "left";
  context.fillText(label, px > (plot.left + plot.right) / 2 ? px - 8 : px + 8, Math.max(plot.top + 14, py - 8));
}

function bindTooltip(canvas) {
  if (!canvas || canvas.dataset.steelPlotTooltipBound === "true") return;
  canvas.dataset.steelPlotTooltipBound = "true";

  function hide() {
    const tip = el("tip");
    if (tip) tip.style.display = "none";
  }

  function show(event) {
    const tip = el("tip");
    const state = canvas.__steelBeamPlotState;
    if (!tip || !state || !state.xValues.length || !state.yValues.length) {
      hide();
      return;
    }

    const rect = canvas.getBoundingClientRect();
    const localX = event.clientX - rect.left;
    let bestIndex = 0;
    let bestDistance = Number.POSITIVE_INFINITY;
    state.xValues.forEach(function (x, index) {
      const px = state.xToCssPx(Number(x));
      const distance = Math.abs(px - localX);
      if (distance < bestDistance) {
        bestDistance = distance;
        bestIndex = index;
      }
    });

    tip.style.display = "block";
    tip.style.left = (event.clientX + 14) + "px";
    tip.style.top = (event.clientY + 14) + "px";
    tip.innerHTML =
      "x = " + fmt(state.xValues[bestIndex], 3) + " m<br>" +
      state.tooltipName + " = " + fmt(state.yValues[bestIndex], state.digits) + " " + state.unit;
  }

  canvas.addEventListener("mousemove", show);
  canvas.addEventListener("mouseenter", show);
  canvas.addEventListener("mouseleave", hide);
}

export function clearLinePlot(canvasId, rangeId) {
  clearCanvas(el(canvasId));
  setRangeText(rangeId, DEFAULT_RANGE_TEXT);
}

export function renderLinePlot(options) {
  const canvas = el(options.canvasId);
  const xValues = Array.isArray(options.x) ? options.x.map(Number) : [];
  const yValues = Array.isArray(options.y) ? options.y.map(Number) : [];

  if (!canvas || !xValues.length || xValues.length !== yValues.length) {
    clearLinePlot(options.canvasId, options.rangeId);
    console.warn("[steel-beam-plots] missing or mismatched plot arrays", {
      canvasId: options.canvasId,
      xLength: xValues.length,
      yLength: yValues.length
    });
    return;
  }

  const yRange = minMax(yValues);
  const xRange = minMax(xValues);
  if (!xRange || !yRange || xRange.max <= xRange.min) {
    clearLinePlot(options.canvasId, options.rangeId);
    return;
  }

  const maxAbs = Math.max(Math.abs(yRange.min), Math.abs(yRange.max));
  const digits = options.digits || 3;
  setRangeText(
    options.rangeId,
    "min " + fmt(yRange.min, digits) + " | max " + fmt(yRange.max, digits) + " | max abs " + fmt(maxAbs, digits)
  );

  const canvasConfig = configureCanvas(canvas);
  const context = canvasConfig.context;
  const width = canvasConfig.width;
  const height = canvasConfig.height;
  const pad = { left: 58, right: 18, top: 16, bottom: 36 };
  const plot = {
    left: pad.left,
    right: width - pad.right,
    top: pad.top,
    bottom: height - pad.bottom,
    width: width - pad.left - pad.right,
    height: height - pad.top - pad.bottom,
    canvasHeight: height,
    yMin: Math.min(yRange.min, 0),
    yMax: Math.max(yRange.max, 0)
  };

  const ySpan = plot.yMax - plot.yMin || Math.max(1, Math.abs(plot.yMax), Math.abs(plot.yMin));
  plot.yMin -= ySpan * 0.08;
  plot.yMax += ySpan * 0.08;

  const xToPx = function (x) {
    return plot.left + ((x - xRange.min) * plot.width) / Math.max(xRange.max - xRange.min, 1e-9);
  };
  const yToPx = function (y) {
    return plot.top + ((plot.yMax - y) * plot.height) / Math.max(plot.yMax - plot.yMin, 1e-9);
  };

  context.clearRect(0, 0, width, height);
  drawGrid(context, plot);
  drawZeroAxis(context, plot, yToPx);
  drawLabels(context, plot, options);

  const zeroY = yToPx(0);
  context.fillStyle = options.fillColor || "rgba(122,167,255,0.10)";
  context.beginPath();
  xValues.forEach(function (x, index) {
    const px = xToPx(x);
    const py = yToPx(yValues[index]);
    if (index === 0) context.moveTo(px, zeroY);
    context.lineTo(px, py);
  });
  context.lineTo(xToPx(xValues[xValues.length - 1]), zeroY);
  context.closePath();
  context.fill();

  context.strokeStyle = options.color || "rgba(122,167,255,0.95)";
  context.lineWidth = 2;
  context.beginPath();
  xValues.forEach(function (x, index) {
    const px = xToPx(x);
    const py = yToPx(yValues[index]);
    if (index === 0) context.moveTo(px, py);
    else context.lineTo(px, py);
  });
  context.stroke();

  drawMarker(context, plot, xToPx, yToPx, xValues, yValues, options.marker || {}, options);

  canvas.__steelBeamPlotState = {
    xValues: xValues,
    yValues: yValues,
    xToCssPx: xToPx,
    tooltipName: options.tooltipName || options.yLabel || "",
    unit: options.unit || "",
    digits: digits
  };
  bindTooltip(canvas);
}

