"""原生两头完整图修复链；逐图解析统计内核和卷积，完整逆变换。"""
import copy
import importlib.util
from pathlib import Path

HERE=Path(__file__).resolve().parent


def load(name):
    spec=importlib.util.spec_from_file_location(name.replace('-','_'),HERE/(name+'.py'));m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m


def transform(source):
    gn=load('onnx-blocked-group-normalization');spatial=load('onnx-spatial-partition-convolution');point=load('onnx-partition-pointwise-convolution')
    model=copy.deepcopy(source);targets=gn.inventory(model)
    if len(targets)!=16:raise ValueError('complete native GroupNorm denominator')
    model,gnproof=gn.rewrite(model,targets);blocked_bytes=model.SerializeToString();proofs=[]
    for name in ['/enc1/enc1.0/Conv','/enc1/enc1.3/Conv','/dec1/dec1.0/Conv','/dec1/dec1.3/Conv']:
        model,proof=spatial.transform(model,name);proofs.append(proof)
    model,pointproof=point.transform(model,'/delta/Conv')
    restored=point.restore(model,pointproof)
    for proof in reversed(proofs):restored=spatial.restore(restored,proof)
    if restored.SerializeToString()!=blocked_bytes:raise ValueError('partition inverse does not restore blocked graph')
    originals={n.name:n for n in source.graph.node};terminal={f'blocked_gn_v1_{i}_normalized':originals[t['node']] for i,t in enumerate(targets)}
    prefixes=tuple(f'blocked_gn_v1_{i}_' for i in range(len(targets)));nodes=[]
    for node in restored.graph.node:
        if node.name in terminal:nodes.append(copy.deepcopy(terminal[node.name]))
        elif not node.name.startswith(prefixes):nodes.append(copy.deepcopy(node))
    del restored.graph.node[:];restored.graph.node.extend(nodes);initializers=[copy.deepcopy(v) for v in restored.graph.initializer if not v.name.startswith(prefixes)]
    del restored.graph.initializer[:];restored.graph.initializer.extend(initializers)
    if restored.SerializeToString()!=source.SerializeToString():raise ValueError('full graph inverse bytes mismatch')
    return model,dict(groupNormalization=gnproof,spatialPartitions=proofs,pointwisePartition=pointproof,allOriginalGraphBytesRestored=True,
                      originalWeightsAffineBiasAndEpsilonUnchanged=True,groupNorms=16,spatialConvolutions=4,pointwiseConvolutions=1)
