// 隔离的NCHW分块卷积；顺序依据冻结的oneDNN AVX2执行证据。
const scratch = new ArrayBuffer(4);
const floatView = new Float32Array(scratch);
const bitsView = new Uint32Array(scratch);

function fused(left, right, accumulator, statistics) {
  const product = left * right; // 两个binary32的乘积在binary64中精确。
  const sum = product + accumulator;
  const rounded = Math.fround(sum);
  if (!Number.isFinite(rounded)) throw new RangeError('Nonfinite convolution result');
  if (sum === rounded) return rounded;
  floatView[0] = rounded;
  if (rounded === 0) bitsView[0] = sum > 0 ? 1 : 0x80000001;
  else bitsView[0] += ((sum > rounded) === (rounded > 0)) ? 1 : -1;
  const neighbor = floatView[0];
  if (sum !== (rounded + neighbor) * 0.5) return rounded;
  statistics.midpointHits++;
  const virtualAccumulator = sum - product;
  const residual = (product - (sum - virtualAccumulator)) + (accumulator - virtualAccumulator);
  if (residual === 0) return rounded;
  statistics.correctedMidpoints++;
  return residual > 0 ? Math.max(rounded, neighbor) : Math.min(rounded, neighbor);
}

export function fmaFloat32(left, right, accumulator, statistics = { midpointHits: 0, correctedMidpoints: 0 }) {
  for (const value of [left, right, accumulator]) {
    if (!Number.isFinite(value) || !Object.is(value, Math.fround(value))) {
      throw new TypeError('FMA requires finite binary32 operands');
    }
  }
  return fused(left, right, accumulator, statistics);
}

function dimensions(value, count, allowZero = false) {
  if (!Array.isArray(value) || value.length !== count ||
      value.some(n => !Number.isSafeInteger(n) || n < (allowZero ? 0 : 1))) {
    throw new TypeError('Invalid convolution dimensions');
  }
}

function tensor(value, length) {
  if (!(value instanceof Float32Array) || !Number.isSafeInteger(length) || value.length !== length) {
    throw new TypeError('Convolution requires exact Float32Array lengths');
  }
  for (let i = 0; i < value.length; i++) {
    if (!Number.isFinite(value[i])) throw new RangeError('Nonfinite convolution input');
  }
}

export function convolveStageABlocked({ input, inputShape, weights, weightShape, bias, strides, pads }) {
  dimensions(inputShape, 4); dimensions(weightShape, 4);
  dimensions(strides, 2); dimensions(pads, 4, true);
  const [batch, channels, height, width] = inputShape;
  const [outputs, weightChannels, kh, kw] = weightShape;
  if (batch !== 1 || channels !== weightChannels || (channels !== 3 && channels % 8 !== 0)) {
    throw new RangeError('Only batch1, groups1, flat3 or complete channel blocks8 are supported');
  }
  tensor(input, channels * height * width);
  tensor(weights, outputs * channels * kh * kw); tensor(bias, outputs);
  const [sy, sx] = strides; const [top, left, bottom, right] = pads;
  const oh = Math.floor((height + top + bottom - kh) / sy) + 1;
  const ow = Math.floor((width + left + right - kw) / sx) + 1;
  const length = outputs * oh * ow;
  if (oh < 1 || ow < 1 || !Number.isSafeInteger(length) || length > 16777216) {
    throw new RangeError('Invalid or unsupported output allocation');
  }
  const result = new Float32Array(length);
  const plane = oh * ow;
  for (let o = 0; o < outputs; o++) result.fill(bias[o], o * plane, (o + 1) * plane);
  const block = channels === 3 ? 3 : 8;
  const statistics = { midpointHits: 0, correctedMidpoints: 0 };
  for (let first = 0; first < channels; first += block) {
    for (let y = 0; y < kh; y++) {
      const h0 = Math.max(0, Math.ceil((top - y) / sy));
      const h1 = Math.min(oh, Math.floor((height - 1 + top - y) / sy) + 1);
      for (let x = 0; x < kw; x++) {
        const w0 = Math.max(0, Math.ceil((left - x) / sx));
        const w1 = Math.min(ow, Math.floor((width - 1 + left - x) / sx) + 1);
        for (let c = first; c < Math.min(first + block, channels); c++) {
          for (let o = 0; o < outputs; o++) {
            const coefficient = weights[((o * channels + c) * kh + y) * kw + x];
            for (let h = h0; h < h1; h++) {
              let source = (c * height + h * sy + y - top) * width + w0 * sx + x - left;
              let target = o * plane + h * ow + w0;
              for (let w = w0; w < w1; w++, source += sx, target++) {
                result[target] = fused(coefficient, input[source], result[target], statistics);
              }
            }
          }
        }
      }
    }
  }
  return { data: result, shape: [1, outputs, oh, ow], statistics };
}
