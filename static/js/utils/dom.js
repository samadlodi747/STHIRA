export function el(id) {
  return document.getElementById(id);
}

export function value(id, fallback) {
  const node = el(id);
  return node ? node.value : fallback;
}

export function checked(id, fallback) {
  const node = el(id);
  return node ? !!node.checked : fallback;
}

export function numberValue(id, fallback) {
  const raw = value(id, "");
  const parsed = Number(raw);
  return Number.isFinite(parsed) ? parsed : fallback;
}

export function numberFromNode(node, fallback) {
  if (!node) return fallback;
  const parsed = Number(node.value);
  return Number.isFinite(parsed) ? parsed : fallback;
}

export function setText(id, text) {
  const node = el(id);
  if (node) node.textContent = text;
}

export function pathValue(source, path) {
  return path.split(".").reduce(function (node, key) {
    if (node == null) return undefined;
    return node[key];
  }, source);
}
