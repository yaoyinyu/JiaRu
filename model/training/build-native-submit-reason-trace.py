"""在已冻结逐程序提交运行时上增补同步原因日志，完整字节可逆。"""
import hashlib


def transform(original):
    text=original.decode('utf8');patches=[]
    assert text.count('this.maxDispatchNumber=1;globalThis.__nailSubmissionStats=')==1
    assert text.count('.queue.submit(')==2, 'unreviewed submission paths'
    def change(before,after,purpose):
        nonlocal text
        assert text.count(before)==1,(purpose,text.count(before))
        text=text.replace(before,after,1);patches.append(dict(before=before,after=after,purpose=purpose))
    change('flush(){if(!this.commandEncoder)return;',
           'flush(__nailReason="other"){globalThis.__nailTrace.emit("flush_attempt",{reason:__nailReason,pending:this.pendingDispatchNumber,hasEncoder:!!this.commandEncoder});if(!this.commandEncoder)return;',
           'all backend flush attempts, including no-op')
    change('this.device.queue.submit([this.commandEncoder.finish()]),globalThis.__nailSubmissionStats.flushes++',
           'globalThis.__nailTrace.emit("encoder_submit",{reason:__nailReason,pending:this.pendingDispatchNumber,kernelId:this.currentKernelId}),this.device.queue.submit([this.commandEncoder.finish()]),globalThis.__nailSubmissionStats.flushes++',
           'actual encoder submission')
    change('this.backend.pendingDispatchNumber>=this.backend.maxDispatchNumber&&this.backend.flush()',
           'this.backend.pendingDispatchNumber>=this.backend.maxDispatchNumber&&this.backend.flush("program")',
           'existing compute-triggered call reason only')
    change('a.copyBufferToBuffer(e,0,i,0,o),r.flush(),await i.mapAsync',
           'a.copyBufferToBuffer(e,0,i,0,o),globalThis.__nailTrace.emit("readback_copy",{sourceBuffer:globalThis.__nailTrace.buffer(e),bytes:Number(n)}),r.flush("readback"),await i.mapAsync',
           'existing readback copy and its submission')
    change('this.backend.device.queue.submit([c.finish()]),u.destroy()',
           'globalThis.__nailTrace.emit("upload_submit",{dataId:Number(e),bytes:i,buffer:globalThis.__nailTrace.buffer(s.gpuData.buffer)}),this.backend.device.queue.submit([c.finish()]),u.destroy()',
           'direct upload submission outside backend encoder')
    change('this.backend.pendingDispatchNumber++,globalThis.__nailSubmissionStats.programs++',
           'this.backend.pendingDispatchNumber++,globalThis.__nailTrace.emit("program",{kernelId:this.backend.currentKernelId,program:e.programInfo.name,pending:this.backend.pendingDispatchNumber}),globalThis.__nailSubmissionStats.programs++',
           'actual program immediately before submit test')
    change('this.kernels.set(n,a)}releaseKernel(',
           'this.kernels.set(n,a),globalThis.__nailTrace.emit("kernel_create",{kernelId:Number(n),op:e,name:o})}releaseKernel(',
           'runtime kernel identity')
    change('this.currentKernelId=e,u[0]&&',
           'this.currentKernelId=e,globalThis.__nailTrace.emit("kernel_begin",{kernelId:Number(e),op:i,name:a}),u[0]&&',
           'runtime kernel begin')
    change('this.temporaryData=[],this.currentKernelId=null}}registerBuffer(',
           'this.temporaryData=[],globalThis.__nailTrace.emit("kernel_end",{kernelId:Number(e)}),this.currentKernelId=null}}registerBuffer(',
           'runtime kernel end')
    out=text.encode('utf8');assert restore(out,patches)==original
    return out,patches


def restore(patched,patches):
    text=patched.decode('utf8')
    for p in reversed(patches):
        assert text.count(p['after'])==1;text=text.replace(p['after'],p['before'],1)
    return text.encode('utf8')
