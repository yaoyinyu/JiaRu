/* 同步只读跟踪；不创建、提交或读回任何GPU工作。 */
(() => {
  'use strict';
  const buffers = new WeakMap();
  let nextBuffer = 1, sequence = 0, active = null, totalBytes = 0, sealed = false;
  const completed = [];
  const encoder = new TextEncoder();
  const limits = Object.freeze({ events: 55720, bytes: 33554432, totalBytes: 335544320 });
  const buffer = value => {
    if (!value) return null;
    let id = buffers.get(value);
    if (id === undefined) { id = nextBuffer++; buffers.set(value, id); }
    return id;
  };
  const bytes = value => value.byteLength <= 256 ? Array.from(value) : null;
  const emit = (type, data) => {
    if (sealed) return; // 十个窗口已持久化后的会话销毁不在捕获范围内。
    if (active === null) throw Error('trace event outside frozen window: ' + type);
    const event = { seq: ++sequence, type, ...data };
    const line = JSON.stringify(event, (key, value) => {
      if (typeof value === 'number' && !Number.isFinite(value)) throw Error('nonfinite trace: ' + key);
      if (typeof value === 'bigint') throw Error('unconverted bigint trace: ' + key);
      return value;
    });
    active.bytes += encoder.encode(line).byteLength + 1;
    if (active.events.length >= limits.events || active.bytes > limits.bytes - 4096) {
      throw Error('trace bound exceeded; no truncation or continuation allowed');
    }
    active.events.push(line);
  };
  const tensor = (view, manager) => {
    const dataId = Number(view.data);
    const cached = manager.get(dataId);
    return { dataId, dtype: view.dataType, dims: Array.from(view.dims), buffer: cached ? buffer(cached.buffer) : null };
  };
  globalThis.__nailTrace = Object.freeze({
    buffer, bytes, emit, tensor, limits,
    begin(name) {
      if (active !== null || sealed) throw Error('trace window already active or sealed');
      const expected = completed.length === 0 ? 'setup' : 'run-' + completed.length;
      if (name !== expected || completed.length >= 10) throw Error('unexpected trace window');
      active = { name, events: [], bytes: 0, firstSeq: sequence + 1 };
    },
    finish(name) {
      if (active === null || active.name !== name) throw Error('trace window mismatch');
      const content = '{"window":' + JSON.stringify(name) + ',"firstSeq":' + active.firstSeq +
        ',"lastSeq":' + sequence + ',"eventCount":' + active.events.length +
        ',"stableGpuBufferIdentity":true,"truncated":false,"events":[' + active.events.join(',') + ']}';
      const encoded = encoder.encode(content);
      if (encoded.byteLength > limits.bytes || totalBytes + encoded.byteLength > limits.totalBytes) throw Error('trace byte bound exceeded');
      totalBytes += encoded.byteLength;
      completed.push(name);
      active = null;
      return encoded;
    },
    seal() {
      if (active !== null || completed.length !== 10 || sealed) throw Error('trace seal requires all ten complete windows');
      sealed = true;
      return { windows: completed.slice(), totalBytes, lastSeq: sequence, teardownOutsideCapture: true };
    }
  });
})();
