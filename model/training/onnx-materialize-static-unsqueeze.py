"""将显式选中的不可变float32参数扩维物化；保留全部原参数字节与可逆图证明。"""
import copy
import hashlib
import numpy as np
import onnx


def static_value(model,name):
    initializers={v.name:v for v in model.graph.initializer}
    producers={x:n for n in model.graph.node for x in n.output}
    trail=[];current=name
    for _ in range(64):
        if current in initializers:
            return onnx.numpy_helper.to_array(initializers[current]),trail
        n=producers.get(current)
        if n is None:raise ValueError('not a frozen parameter or constant')
        trail.append(n.SerializeToString().hex())
        if n.op_type=='Identity' and len(n.input)==1:current=n.input[0]
        elif n.op_type=='Constant':
            values=[a.t for a in n.attribute if a.name=='value']
            if len(values)!=1:raise ValueError('tensor constant required')
            return onnx.numpy_helper.to_array(values[0]),trail
        else:raise ValueError('nonstatic parameter source')
    raise ValueError('static parameter chain too deep')


def transform(model,node_names):
    if len(set(node_names))!=len(node_names) or not node_names:raise ValueError('explicit unique source nodes required')
    selected=set(node_names);result=copy.deepcopy(model);proofs=[];added=[]
    for index,n in enumerate(model.graph.node):
        if n.name not in selected:continue
        if n.op_type!='Unsqueeze' or len(n.input)!=2 or len(n.output)!=1:raise ValueError('static Unsqueeze only')
        value,trail=static_value(model,n.input[0]);axes,axes_trail=static_value(model,n.input[1])
        if value.dtype!=np.float32 or value.ndim!=1 or value.shape[0] not in [16,32,64] or not np.isfinite(value).all():raise ValueError('native norm parameter domain')
        if axes.dtype!=np.int64 or axes.tolist()!=[1,2]:raise ValueError('frozen native norm broadcast axes')
        output=np.expand_dims(value,axis=(1,2)).copy()
        if output.shape!=(len(value),1,1) or output.tobytes()!=value.tobytes():raise ValueError('parameter storage must remain exact')
        if any(v.name==n.output[0] for v in model.graph.initializer):raise ValueError('initializer output collision')
        item=onnx.numpy_helper.from_array(output,name=n.output[0]);added.append(item)
        proofs.append(dict(sourceNodeName=n.name,sourceNodeIndex=index,originalNodeHex=n.SerializeToString().hex(),
                           originalParameterName=n.input[0],parameterTrace=trail,axesTrace=axes_trail,
                           addedInitializerName=item.name,addedInitializerSha256=hashlib.sha256(item.SerializeToString()).hexdigest(),
                           parameterBytesSha256=hashlib.sha256(value.tobytes()).hexdigest(),outputShape=list(output.shape)))
    if len(proofs)!=len(selected):raise ValueError('missing explicit source nodes')
    nodes=[copy.deepcopy(n) for n in result.graph.node if n.name not in selected]
    del result.graph.node[:];result.graph.node.extend(nodes);result.graph.initializer.extend(added)
    proof=dict(records=proofs,originalInitializerHashes={v.name:hashlib.sha256(v.SerializeToString()).hexdigest() for v in model.graph.initializer})
    if restore(result,proof).SerializeToString()!=model.SerializeToString():raise ValueError('full graph inverse bytes')
    onnx.checker.check_model(result,full_check=True)
    return result,proof


def restore(model,proof):
    result=copy.deepcopy(model);names={r['addedInitializerName']:r for r in proof['records']}
    originals=[]
    for v in result.graph.initializer:
        if v.name in names:
            if hashlib.sha256(v.SerializeToString()).hexdigest()!=names[v.name]['addedInitializerSha256']:raise ValueError('materialized parameter drift')
        else:
            if hashlib.sha256(v.SerializeToString()).hexdigest()!=proof['originalInitializerHashes'][v.name]:raise ValueError('original parameter drift')
            originals.append(copy.deepcopy(v))
    if {v.name for v in originals}!=set(proof['originalInitializerHashes']):raise ValueError('original initializer denominator')
    if {v.name for v in result.graph.initializer if v.name in names}!=set(names):raise ValueError('materialized initializer denominator')
    del result.graph.initializer[:];result.graph.initializer.extend(originals)
    nodes=[copy.deepcopy(n) for n in result.graph.node]
    for r in sorted(proof['records'],key=lambda x:x['sourceNodeIndex']):
        n=onnx.NodeProto();n.ParseFromString(bytes.fromhex(r['originalNodeHex']));nodes.insert(r['sourceNodeIndex'],n)
    del result.graph.node[:];result.graph.node.extend(nodes)
    return result
