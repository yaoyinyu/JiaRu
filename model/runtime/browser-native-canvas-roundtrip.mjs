import { originalMask, packedMask, canvasReadback } from './native-canvas-roundtrip.mjs';

const status = document.querySelector('#status');
async function sha(bytes) {
  return Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256', bytes)), x => x.toString(16).padStart(2, '0')).join('');
}
async function post(path, value) {
  const body = JSON.stringify(value);
  // ACK丢失只重传原请求，不重做变换。
  let error;
  for (let attempt = 0; attempt < 3; attempt++) {
    try {
      const response = await fetch(path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body });
      const result = await response.json();
      if (!response.ok || !result.ok) throw new Error(JSON.stringify(result));
      return result;
    } catch (problem) { error = problem; }
  }
  throw error;
}
async function floats(ref) {
  const response = await fetch(`/raw/${ref.id}`);
  if (!response.ok) throw new Error('saved head unavailable');
  const bytes = await response.arrayBuffer();
  if (await sha(bytes) !== ref.sha256) throw new Error('saved head SHA');
  return new Float32Array(bytes);
}
function base64(bytes) {
  let result = '';
  for (let i = 0; i < bytes.length; i += 8192) result += String.fromCharCode(...bytes.subarray(i, i + 8192));
  return btoa(result);
}
document.querySelector('button').addEventListener('click', async event => {
  event.target.disabled = true;
  try {
    const manifest = await (await fetch('/manifest')).json();
    const page = crypto.randomUUID();
    await post('/claim', { page, userAgent: navigator.userAgent, canvas: 'OffscreenCanvas 2D actual readback' });
    let sequence = 0;
    for (const item of manifest.items) {
      sequence++;
      const requestId = crypto.randomUUID();
      const identity = { sequence, key: item.key, page, requestId };
      await post('/start', identity);
      const logits = item.control ? new Float32Array(item.logits) : await floats(item.heads.mask);
      const presence = item.control ? item.presence : (await floats(item.heads.presence))[0];
      const pixels = originalMask(logits, presence, item.sourceSize, item.cropBox, item.nativeSize);
      const actual = canvasReadback(pixels, item.sourceSize);
      const packed = packedMask(actual);
      await post('/done', { ...identity, packed: base64(packed),
        pixelSha256: await sha(actual), packedSha256: await sha(packed),
        sourceSize: item.sourceSize, outputPixels: actual.reduce((sum, v) => sum + v, 0),
        presenceAccepted: presence >= 0 });
      status.textContent = `${sequence}/${manifest.items.length} 已捕获`;
    }
    await post('/finish', { page, sequence });
    status.textContent = `complete: ${sequence} transformations; model inputs 0`;
  } catch (error) {
    status.textContent = `failed: ${String(error)}`;
    console.error(error);
  }
});
