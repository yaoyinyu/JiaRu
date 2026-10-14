"""按实际新图语义追加完整模块观测输出，静态回剥不构成运行保真证明。"""
import copy
import importlib.util
from pathlib import Path
import numpy as np
import onnx
HERE=Path(__file__).resolve().parent
s=importlib.util.spec_from_file_location('native_observation_data',HERE/'reviewed-role-development-data.py')
d=importlib.util.module_from_spec(s); s.loader.exec_module(d)


def mapping(model):
    nodes={}
    for node in model.graph.node:
        if node.name in nodes: raise ValueError('unique node identity')
        nodes[node.name]=node
    result=[]
    for block in ('enc1','enc2','enc3','dec2','dec1'):
        for index in range(6):
            op=('Conv','Add','Mul')[index%3]; name=f'/{block}/{block}.{index}/{op}'+('_1' if index%3==2 else '')
            node=nodes.get(name)
            if node is None or node.op_type!=op or len(node.output)!=1: raise ValueError('exact actual semantic module endpoint')
            result.append({'module':f'{block}.{index}','node':name,'tensor':node.output[0],
                'operation':('Conv2d','GroupNorm','GELU')[index%3]})
    node=nodes.get('/delta/Conv')
    if node is None or node.op_type!='Conv' or len(node.output)!=1: raise ValueError('actual delta endpoint')
    result.append({'module':'delta','node':node.name,'tensor':node.output[0],'operation':'Conv2d'})
    if len({r['tensor'] for r in result})!=len(result): raise ValueError('unique actual endpoints')
    return result


def specs(rows):
    return [{'key':'mask','name':'mask_logits','shapeKey':'mask'},{'key':'presence','name':'presence_logit','shapeKey':'presence'}]+[
        {'key':f'layer{i:02d}','name':row['tensor'],'shapeKey':row['module']} for i,row in enumerate(rows)]


def shapes(h,w,rows):
    if min(h,w)<4: raise ValueError('native pooling shape')
    shape={'enc1':[1,16,h,w],'enc2':[1,32,h//2,w//2],'enc3':[1,64,h//4,w//4],
        'dec2':[1,32,h//2,w//2],'dec1':[1,16,h,w],'delta':[1,1,h,w]}
    return {'mask':[1,1,h,w],'presence':[1,1]}|{f'layer{i:02d}':shape[row['module'].split('.')[0]] for i,row in enumerate(rows)}


def add_outputs(original,rows):
    if [x.name for x in original.graph.output]!=['mask_logits','presence_logit']: raise ValueError('original ordered two heads')
    if rows!=mapping(original): raise ValueError('actual graph semantic mapping')
    model=copy.deepcopy(original)
    for row in rows: model.graph.output.append(onnx.helper.make_tensor_value_info(row['tensor'],onnx.TensorProto.FLOAT,[1,None,None,None]))
    verify_graph(original,model,rows); return model


def verify_graph(original,model,rows):
    if rows!=mapping(original) or [o.name for o in model.graph.output]!=[r['name'] for r in specs(rows)]: raise ValueError('all actual ordered outputs')
    if any(o.type.tensor_type.elem_type!=onnx.TensorProto.FLOAT for o in model.graph.output): raise ValueError('all float32 outputs')
    stripped=copy.deepcopy(model); del stripped.graph.output[2:]
    if stripped.SerializeToString()!=original.SerializeToString(): raise ValueError('original complete graph bytes')
    onnx.checker.check_model(model)


def independent_input(h,w,seed):
    rng=np.random.default_rng(seed); x=rng.normal(0,.7,(1,4,h,w)).astype(np.float32)
    y,z=np.mgrid[:h,:w]; x[:,3]=( ((y-h/2)/(h*.32))**2+((z-w/2)/(w*.29))**2<1).astype(np.float32)
    if not np.isfinite(x).all() or not np.any(x[:,:3]) or set(np.unique(x[:,3]))!={0.,1.}: raise ValueError('nonzero independent RGB/binary seed')
    return x


def require_fidelity(report,count,kind):
    if report.get('syntheticBaselineOnly') or not report.get('ok') or report.get('kind')!=kind or not report.get('allOwnHeadsBitwiseIdenticalAllBackends'):
        raise ValueError('complete actual own-backend bitwise fidelity required')
    expected=[(b,o) for b in ('cpu','wasm','webgpu') for o in range(1,count+1)]
    if [(r['backend'],r['ordinal']) for r in report['records']]!=expected or not all(r['ownHeadsBitwiseIdentical'] for r in report['records']):
        raise ValueError('full fidelity denominator and per-input gate')
