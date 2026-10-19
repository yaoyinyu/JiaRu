/** 原尺寸候选RGB通道矩规范化；与Python uint8格点及偶数舍入一致。 */
export function normalizeNativeRgb(rgb,width,height) {
  if (!(rgb instanceof Uint8Array) || !Number.isInteger(width) || !Number.isInteger(height) || Math.min(width,height)<16 || Math.max(width,height)>1536 || rgb.length!==width*height*3) throw new Error("native uint8 RGB sides16..1536 required");
  const count=width*height,sums=[0,0,0],squares=[0,0,0];
  for(let i=0;i<rgb.length;i++){const c=i%3,v=rgb[i];sums[c]+=v;squares[c]+=v*v;}
  const means=sums.map(v=>v/count),scales=squares.map((v,c)=>Math.sqrt(Math.max(1,v/count-means[c]*means[c]))),result=new Uint8Array(rgb.length);
  for(let i=0;i<rgb.length;i++){
    const c=i%3,v=Math.max(0,Math.min(1,.5+.2*((rgb[i]-means[c])/scales[c])))*255;
    const lower=Math.floor(v);result[i]=v-lower===.5?(lower%2===0?lower:lower+1):Math.round(v);
  }
  return result;
}
