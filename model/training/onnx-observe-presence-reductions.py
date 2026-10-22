"""原presence归约的只读观察：不增加节点或修改任何权重。"""
import copy
import onnx
from onnx import helper


def transform(source):
    graph=copy.deepcopy(source);nodes={n.name:n for n in source.graph.node}
    expected={
        '/ReduceSum':('ReduceSum',['/Mul_28_output_0','onnx::ReduceSum_1482']),
        '/ReduceSum_1':('ReduceSum',['/Div_12_output_0','onnx::ReduceSum_1482']),
        '/ReduceMean':('ReduceMean',['/enc3/enc3.5/Mul_1_output_0','/Constant_149_output_0']),
        '/Concat_15':('Concat',['/Div_13_output_0','/ReduceMean_output_0']),
        '/presence/Gemm':('Gemm',['/Concat_15_output_0','presence.weight','presence.bias'])}
    for name,(op,inputs) in expected.items():
        n=nodes[name]
        if n.op_type!=op or list(n.input)!=inputs:raise ValueError('presence semantic node mismatch')
    outputs=dict(features='/enc3/enc3.5/Mul_1_output_0',seed='/Div_12_output_0',local='/Div_13_output_0',globalMean='/ReduceMean_output_0',presenceInput='/Concat_15_output_0')
    shapes=dict(features=[1,64,'quarterH','quarterW'],seed=[1,1,'quarterH','quarterW'],local=[1,64],globalMean=[1,64],presenceInput=[1,128])
    for key,name in outputs.items():graph.graph.output.append(helper.make_tensor_value_info(name,onnx.TensorProto.FLOAT,shapes[key]))
    restored=copy.deepcopy(graph);del restored.graph.output[2:]
    if restored.SerializeToString()!=source.SerializeToString():raise ValueError('observer inverse bytes mismatch')
    onnx.checker.check_model(graph,full_check=True)
    return graph,dict(outputs=outputs,outputShapes=shapes,addedOutputs=5,addedNodes=0,addedInitializers=0,originalGraphInverseByteExact=True,quarterSize='floor(input/4)',float32Storage=True)
