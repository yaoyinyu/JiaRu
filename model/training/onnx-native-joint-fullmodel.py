"""完整候选仅替换四个比例Div及末级GN求和，独立回剥验原图字节。"""
import copy
import numpy as np
import onnx
from onnx import helper,numpy_helper

RATIOS=[f'native_bilinear_{i}_{a}_ratio' for i in range(2) for a in ('y','x')]
TOTALS=['stable_gn_209_'+a+'_total_sum' for a in ('mean','variance')]

def verify_patch(original,patched):
    if len({n.name for n in original.graph.node})!=len(original.graph.node):raise ValueError('unique original node names required')
    restored=copy.deepcopy(patched);old={n.name:n for n in original.graph.node};ratio_names={n.name for n in original.graph.node if n.output[0] in RATIOS}
    targets=ratio_names|set(TOTALS);nodes=[]
    for node in restored.graph.node:
        if node.name.startswith('hierarchical_stable_gn_209_'):continue
        nodes.append(old[node.name] if node.name in targets else node)
    del restored.graph.node[:];restored.graph.node.extend(nodes)
    initializers=[v for v in restored.graph.initializer if not v.name.startswith(('full_host_ratio_axis_','hierarchical_stable_gn_209_'))]
    del restored.graph.initializer[:];restored.graph.initializer.extend(initializers)
    inputs=[v for v in restored.graph.input if v.name!='resizeRatios'];del restored.graph.input[:];restored.graph.input.extend(inputs)
    if restored.SerializeToString()!=original.SerializeToString():raise ValueError('reverse patch did not restore original bytes')
    if [v.name for v in patched.graph.input]!=[v.name for v in original.graph.input]+['resizeRatios']:raise ValueError('host input')

def rewrite_model(model,isolated_repair):
    original=copy.deepcopy(model);targets=[n for n in model.graph.node if n.op_type=='Div' and n.output[0] in RATIOS]
    if [n.output[0] for n in targets]!=RATIOS or any(v.name=='resizeRatios' for v in model.graph.input):raise ValueError('exact four ordered ratios / no input collision')
    for i,node in enumerate(targets):
        key=f'full_host_ratio_axis_{i}'
        if any(v.name==key for v in model.graph.initializer):raise ValueError('ratio constant collision')
        model.graph.initializer.append(numpy_helper.from_array(np.array(i,np.int64),name=key))
        node.CopyFrom(helper.make_node('Gather',['resizeRatios',key],list(node.output),name=node.name,axis=0))
    model.graph.input.append(helper.make_tensor_value_info('resizeRatios',onnx.TensorProto.FLOAT,[4]))
    isolated_repair.hierarchical_group_sum(model)
    verify_patch(original,model);onnx.checker.check_model(model,full_check=True)
    return model
