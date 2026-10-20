"""观察显式四维float32中间输出；调用者另验实际形状与完整最终头保真。"""
import copy
import re
import onnx


def observe(model,node_name,op_type,output_name,shape):
    matches=[n for n in model.graph.node if n.name==node_name]
    if len(matches)!=1 or matches[0].op_type!=op_type or output_name not in matches[0].output:
        raise ValueError('unique actual observation node/output')
    if sum(output_name in n.output for n in model.graph.node)!=1 or any(v.name==output_name for v in [*model.graph.input,*model.graph.output]):
        raise ValueError('observation identity is not new intermediate')
    if len(shape)!=4 or shape[0]!=1 or type(shape[1]) is not int or shape[1]<=0:
        raise ValueError('explicit native batch/channel shape required')
    for dim in shape[2:]:
        if not ((type(dim) is int and dim>0) or (isinstance(dim,str) and re.fullmatch(r'[A-Za-z_]\w*',dim))):
            raise ValueError('explicit positive or named spatial dimensions required')
    result=copy.deepcopy(model)
    result.graph.output.append(onnx.helper.make_tensor_value_info(output_name,onnx.TensorProto.FLOAT,shape))
    restored=copy.deepcopy(result);del restored.graph.output[-1:]
    if restored.SerializeToString()!=model.SerializeToString():
        raise ValueError('complete observation strip fidelity')
    onnx.checker.check_model(result,full_check=True)
    return result
