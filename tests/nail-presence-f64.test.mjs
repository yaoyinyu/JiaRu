import assert from "node:assert/strict";
import test from "node:test";
import { attachF64Presence, createPresenceComputer, presenceWorkspaceBytes } from "../model/runtime/nail-presence-f64.mjs";

function input(h, w, seed = () => 1) {
  const a = new Float32Array(4 * h * w);
  for (let y = 0; y < h; y++) for (let x = 0; x < w; x++) a[3 * h * w + y * w + x] = seed(y, x);
  return a;
}

test("full661 auxiliary arrays are bounded; unsupported dimensions reject", () => {
  assert.equal(presenceWorkspaceBytes(), 1972320);
  assert.ok(presenceWorkspaceBytes() < 8 * 1024 * 1024);
  for (const bad of [3, 662, 4.5, NaN]) assert.throws(() => presenceWorkspaceBytes(bad, 9), /controlled domain/);
});

test("empty seed removes only local features, global features and bias remain", () => {
  const w = new Float32Array(128); w[0] = 7; w[64] = 2;
  const c = createPresenceComputer(w, new Float32Array([3]), 7, 9);
  c.prepare(input(7, 9, () => 0), 7, 9);
  const e = new Float64Array(64 * 2); e[0] = 1; e[1] = 5;
  assert.equal(c.finish(e, [1, 64, 1, 2])[0], 9);
});

test("odd adaptive windows preserve F32 sequential divisions before F64 weighting", () => {
  const h = 9, w = 11, weights = new Float32Array(128); weights[0] = 1; weights[64] = .25;
  const c = createPresenceComputer(weights, new Float32Array([-.5]), h, w);
  const values = input(h, w, (y, x) => (y + 2 * x) % 5 === 0 ? 1 : 0);
  c.prepare(values, h, w);
  const e = new Float64Array(64 * 4); e.set([1, 3, 5, 11]);
  // 独立枚举四个5×6窗口，直接计数，不复用积分表或实现的范围公式。
  const windows = [[0,5,0,6], [0,5,5,11], [4,9,0,6], [4,9,5,11]];
  const seeds = windows.map(([y0,y1,x0,x1]) => {
    let count = 0;
    for (let y=y0;y<y1;y++) for(let x=x0;x<x1;x++) count += values[3*h*w+y*w+x];
    return Math.fround(Math.fround(count/5)/6);
  });
  const expected = Math.fround([1,3,5,11].reduce((s,v,i)=>s+v*seeds[i],0) / Math.max(seeds.reduce((s,v)=>s+v,0),1) + .25*5 - .5);
  assert.equal(c.finish(e, [1,64,2,2])[0], expected);
});

test("head retains F64 feature values and rounds only the final result", () => {
  const weights = new Float32Array(128); weights[0]=1; weights[64]=-1;
  const c = createPresenceComputer(weights, new Float32Array([0]), 4, 8);
  c.prepare(input(4,8,(_y,x)=>x<4?1:0),4,8);
  const e = new Float64Array(64*2);e[0]=1+2**-30;e[1]=1;
  assert.equal(c.finish(e,[1,64,1,2])[0], Math.fround(2**-31));
});

test("parameter copies and complete input validation protect fixed semantics", () => {
  const w=new Float32Array(128);w[64]=1;
  const c=createPresenceComputer(w,new Float32Array([0]),4,4);w[64]=100;
  assert.throws(()=>c.prepare(input(4,4,()=>.5),4,4),/binary coarse seed/);
  const bad=input(4,4);bad[0]=NaN;assert.throws(()=>c.prepare(bad,4,4),/finite F32 candidate/);
  c.prepare(input(4,4),4,4);
  assert.throws(()=>c.prepare(input(4,4),4,4),/already prepared/);
  assert.throws(()=>c.finish(new Float64Array(64),[1,64,2,1]),/enc3.5/);
  assert.equal(c.finish(new Float64Array(64).fill(2),[1,64,1,1])[0],2);
});

test("assembly consumes one encoder event and preserves the returned mask object and bytes",async()=>{
  const mask=new Float32Array([1,-3,7]);const original=mask.slice();
  const fake={plan:()=>({highWaterBytes:99}),async run(_a,_h,_w,_r,observe){
    observe({op:"gelu",name:"enc3",suffix:"5",values:new Float64Array(64).fill(2),shape:[1,64,1,1]});
    return {mask,presenceExecuted:false};}};
  const w=new Float32Array(128);w[0]=1;
  const runtime=attachF64Presence(fake,w,new Float32Array([1]));
  const result=await runtime.run(input(4,4),4,4,new Float32Array(4));
  assert.equal(result.mask,mask);assert.deepEqual(result.mask,original);assert.equal(result.presence[0],3);
  assert.equal(runtime.plan(4,4).processPeakMemoryMeasured,false);
});

test("missing or duplicate encoder events fail without falling back to an old head",async()=>{
  const event={op:"gelu",name:"enc3",suffix:"5",values:new Float64Array(64),shape:[1,64,1,1]};
  for(const n of [0,2]){
    const runtime=attachF64Presence({plan:()=>({}),async run(_a,_h,_w,_r,observe){for(let i=0;i<n;i++)observe(event);return {mask:new Float32Array(16)};}},new Float32Array(128),new Float32Array([0]));
    await assert.rejects(runtime.run(input(4,4),4,4,new Float32Array(4)),/missing|duplicate/);
  }
});

test("concurrent execution rejects and an execution error releases state for a new explicit caller",async()=>{
  let release;const gate=new Promise(resolve=>{release=resolve;});
  const runtime=attachF64Presence({plan:()=>({}),async run(){await gate;throw new Error("kernel execution failed");}},new Float32Array(128),new Float32Array([0]));
  const first=runtime.run(input(4,4),4,4,new Float32Array(4));
  await assert.rejects(runtime.run(input(4,4),4,4,new Float32Array(4)),/concurrent/);
  release();await assert.rejects(first,/kernel execution failed/);
  await assert.rejects(runtime.run(input(4,4),4,4,new Float32Array(4)),/kernel execution failed/);
});
