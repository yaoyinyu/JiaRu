"""固定分发包的同步观测补丁；逐条逆变换恢复原始字节，不修改安装包。"""
import hashlib
import json
from pathlib import Path

EXPECTED = 'df84c52a502d111dc25a50179f7e36d553776f3387d714aeff775d1d296296a3'


def transform(original):
    assert hashlib.sha256(original).hexdigest() == EXPECTED, 'unreviewed runtime build'
    text = original.decode('utf8')
    assert text.count('forceCpuNodeNames') == 0
    assert 'case"webgpu":if(i="JS"' in text
    patches = []

    def insert(before, after, purpose):
        nonlocal text
        assert text.count(before) == 1, (purpose, text.count(before))
        patches.append(dict(before=before, after=after, purpose=purpose))
        text = text.replace(before, after, 1)

    insert('this.storageCache.set(s.id,{gpuData:s,originalSize:Number(e)}),ue(',
           'this.storageCache.set(s.id,{gpuData:s,originalSize:Number(e)}),globalThis.__nailTrace.emit("allocate",{dataId:s.id,buffer:globalThis.__nailTrace.buffer(o),size:Number(e),capacity:t,usage:n}),ue(',
           'allocation: actual data ID and GPUBuffer object')
    insert('this.storageCache.delete(n),this.buffersPending.push(t.gpuData.buffer),t.originalSize}',
           'globalThis.__nailTrace.emit("release",{dataId:n,buffer:globalThis.__nailTrace.buffer(t.gpuData.buffer),size:t.originalSize}),this.storageCache.delete(n),this.buffersPending.push(t.gpuData.buffer),t.originalSize}',
           'release: before cache removal')
    insert('let c=this.backend.device.createCommandEncoder();c.copyBufferToBuffer(u,0,s.gpuData.buffer,0,a)',
           'globalThis.__nailTrace.emit("upload",{dataId:Number(e),buffer:globalThis.__nailTrace.buffer(s.gpuData.buffer),stagingBuffer:globalThis.__nailTrace.buffer(u),size:i,bytes:globalThis.__nailTrace.bytes(n)});let c=this.backend.device.createCommandEncoder();c.copyBufferToBuffer(u,0,s.gpuData.buffer,0,a)',
           'CPU upload: exact small bytes, no new GPU access')
    insert('this.backend.endComputePass(),a.copyBufferToBuffer(t.gpuData.buffer,0,o.gpuData.buffer,0,i)',
           'this.backend.endComputePass(),globalThis.__nailTrace.emit("copy",{sourceId:Number(e),destinationId:Number(n),sourceBuffer:globalThis.__nailTrace.buffer(t.gpuData.buffer),destinationBuffer:globalThis.__nailTrace.buffer(o.gpuData.buffer),size:t.originalSize}),a.copyBufferToBuffer(t.gpuData.buffer,0,o.gpuData.buffer,0,i)',
           'device copy: existing source/destination')
    insert('for(let e of this.buffersPending){let n=pg.get(e.size);',
           'for(let e of this.buffersPending){let n=pg.get(e.size);globalThis.__nailTrace.emit("recycle",{buffer:globalThis.__nailTrace.buffer(e),capacity:e.size,usage:e.usage,cache:((e.usage&GPUBufferUsage.STORAGE)===GPUBufferUsage.STORAGE||(e.usage&GPUBufferUsage.UNIFORM)===GPUBufferUsage.UNIFORM)&&n!==undefined&&((e.usage&GPUBufferUsage.STORAGE)===GPUBufferUsage.STORAGE?this.freeBuffers:this.freeUniformBuffers).get(e.size)?.length<n});',
           'free-list decision: preserve original branch and action')
    insert('this.kernels.set(n,a)}releaseKernel(',
           'this.kernels.set(n,a),globalThis.__nailTrace.emit("kernel_create",{kernelId:Number(n),op:e,name:o})}releaseKernel(',
           'actual JS kernel registration, including runtime name')
    insert('this.currentKernelId=e,u[0]&&',
           'this.currentKernelId=e,globalThis.__nailTrace.emit("kernel_begin",{kernelId:Number(e),op:i,name:a,inputs:n.inputs.map(v=>globalThis.__nailTrace.tensor(v,this.gpuDataManager))}),u[0]&&',
           'actual kernel input tensor IDs and dimensions')
    insert('this.temporaryData=[],this.currentKernelId=null}}registerBuffer(',
           'this.temporaryData=[],globalThis.__nailTrace.emit("kernel_end",{kernelId:Number(e)}),this.currentKernelId=null}}registerBuffer(',
           'kernel lifetime end')
    insert('this.device.queue.writeBuffer(P.buffer,0,S,0,w),this.gpuDataManager.release(P.id)',
           'globalThis.__nailTrace.emit("uniform_upload",{dataId:P.id,buffer:globalThis.__nailTrace.buffer(P.buffer),size:w,bytes:globalThis.__nailTrace.bytes(new Uint8Array(S))}),this.device.queue.writeBuffer(P.buffer,0,S,0,w),this.gpuDataManager.release(P.id)',
           'existing uniform upload, small host bytes only')
    insert('return this.programManager.run(b,s,f,m,h),Qe(e.name),p}upload(',
           'return globalThis.__nailTrace.emit("program",{kernelId:Number(this.currentKernelId),program:e.name,artifactProgram:b.programInfo.name,cacheKey:g,dispatch:Array.from(m),inputs:n.map(v=>globalThis.__nailTrace.tensor(v,this.gpuDataManager)),outputs:p.map(v=>globalThis.__nailTrace.tensor(v,this.gpuDataManager)),uniformBuffer:h?globalThis.__nailTrace.buffer(h.buffer):null}),this.programManager.run(b,s,f,m,h),Qe(e.name),p}upload(',
           'actual dispatch binding metadata, no added commands')
    output = text.encode('utf8')
    assert restore(output, patches) == original
    return output, patches


def restore(patched, patches):
    text = patched.decode('utf8')
    for p in reversed(patches):
        assert text.count(p['after']) == 1
        text = text.replace(p['after'], p['before'], 1)
    return text.encode('utf8')


if __name__ == '__main__':
    import argparse
    a = argparse.ArgumentParser(); a.add_argument('source', type=Path); a.add_argument('output', type=Path)
    v = a.parse_args(); output, patches = transform(v.source.read_bytes())
    with v.output.open('xb') as f: f.write(output)
    print(json.dumps(dict(ok=True, patches=len(patches), inverseByteExact=True)))
