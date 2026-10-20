"""按显式切入张量提取上游闭包，保留所有选中节点和常量的原始字节。"""
import copy
import hashlib

import onnx
from onnx import helper


def extract(model, input_name, input_shape, output_names):
    if len(input_shape)!=4 or input_shape[0]!=1 or not output_names or len(set(output_names))!=len(output_names):
        raise ValueError('explicit batch-one four-dimensional boundary and unique outputs required')
    nodes={x:n for n in model.graph.node for x in n.output}
    constants={v.name:v for v in model.graph.initializer}
    if input_name not in nodes:
        raise ValueError('cut must identify an actual graph tensor producer')
    selected=set();initializers=set();visiting=set();crossed=set()
    def visit(name):
        if name==input_name:
            crossed.add(name);return
        if name in constants:
            initializers.add(name);return
        if not name:
            return
        if name not in nodes or name in visiting:
            raise ValueError('unbound input or cyclic dependency')
        n=nodes[name]
        if n.name in selected:
            return
        visiting.add(name)
        for x in n.input:visit(x)
        visiting.remove(name)
        selected.add(n.name)
    for name in output_names:visit(name)
    if crossed!={input_name} or len(selected)!=len([n for n in model.graph.node if n.name in selected]):
        raise ValueError('boundary unreachable or duplicate selected node identities')
    result=copy.deepcopy(model)
    chosen=[copy.deepcopy(n) for n in model.graph.node if n.name in selected]
    values=[copy.deepcopy(v) for v in model.graph.initializer if v.name in initializers]
    for field in ['node','initializer','input','output','value_info']:
        del getattr(result.graph,field)[:]
    result.graph.node.extend(chosen);result.graph.initializer.extend(values)
    result.graph.input.append(helper.make_tensor_value_info(input_name,onnx.TensorProto.FLOAT,input_shape))
    result.graph.output.extend(helper.make_tensor_value_info(x,onnx.TensorProto.FLOAT,input_shape) for x in output_names)
    onnx.checker.check_model(result,full_check=True)
    proof=dict(inputBoundary=input_name,inputShape=input_shape,outputs=output_names,
               nodes=[dict(index=i,name=n.name,sha256=hashlib.sha256(n.SerializeToString()).hexdigest()) for i,n in enumerate(model.graph.node) if n.name in selected],
               initializers=[dict(index=i,name=v.name,sha256=hashlib.sha256(v.SerializeToString()).hexdigest()) for i,v in enumerate(model.graph.initializer) if v.name in initializers],
               allSelectedNodeAndInitializerBytesPreserved=True,doesNotClaimFullGraphRuntimeEquivalence=True)
    return result,proof
