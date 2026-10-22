"""只增加已存在的分块归一化均值/方差输出，完整原图字节可回剥。"""
import copy
import onnx
from onnx import helper


def transform(source):
    model=copy.deepcopy(source);nodes={n.name:n for n in model.graph.node};outputs={}
    if len(model.graph.output)!=2:raise ValueError('original two heads required')
    for i in range(16):
        for kind in ['mean','variance']:
            name=f'blocked_gn_v1_{i}_{kind}';node=nodes.get(name)
            if node is None or node.op_type!='Div' or list(node.output)!=[name]:raise ValueError('actual moment node mismatch')
            label=f'gn{i}_{kind}';outputs[label]=name
            model.graph.output.append(helper.make_tensor_value_info(name,onnx.TensorProto.FLOAT,[1,4,1]))
    restored=copy.deepcopy(model);del restored.graph.output[2:]
    if restored.SerializeToString()!=source.SerializeToString():raise ValueError('observer inverse bytes mismatch')
    onnx.checker.check_model(model,full_check=True)
    return model,dict(outputs=outputs,addedOutputs=32,addedNodes=0,addedInitializers=0,originalGraphInverseByteExact=True,
                      momentShape=[1,4,1],momentStorage='float32',perInputAdditionalOutputBytes=512)
