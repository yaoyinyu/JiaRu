const canvas = new OffscreenCanvas(96, 54);
const context = canvas.getContext("2d", { willReadFrequently: true });

self.onmessage = ({ data: { frame, crop } }) => {
  try {
    context.drawImage(frame, ...crop, 0, 0, canvas.width, canvas.height);
    const pixels = context.getImageData(0, 0, canvas.width, canvas.height);
    self.postMessage(pixels, [pixels.data.buffer]);
  } catch {
    self.postMessage(null);
  } finally {
    frame.close();
  }
};
