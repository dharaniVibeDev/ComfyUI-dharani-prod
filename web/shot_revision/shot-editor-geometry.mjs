export function imagePoint(view, x, y) {
  return { x: (x - view.x) / view.scale, y: (y - view.y) / view.scale };
}

export function fitView(width, height, imageWidth, imageHeight, padding = 32) {
  const scale = Math.max(.001, Math.min((width - padding * 2) / imageWidth, (height - padding * 2) / imageHeight));
  return { scale, x: (width - imageWidth * scale) / 2, y: (height - imageHeight * scale) / 2 };
}

export function zoomView(view, scale, x, y) {
  const point = imagePoint(view, x, y);
  return { scale, x: x - point.x * scale, y: y - point.y * scale };
}
