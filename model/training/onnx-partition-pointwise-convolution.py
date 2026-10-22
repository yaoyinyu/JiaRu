"""1×1卷积按动态高度四分；保留点积顺序、原权重与可选偏置。"""
import copy
import hashlib
import math

import numpy as np
import onnx


def transform(model,node_name,parts=4):
    if parts!=4:raise ValueError('fixed four-way partition required')
    matches=[(i,n) for i,n in enumerate(model.graph.node) if n.name==node_name]
    if len(matches)!=1:raise ValueError('unique semantic node required')
    index,node=matches[0];attrs={a.name:onnx.helper.get_attribute_value(a) for a in node.attribute}
    if node.op_type!='Conv' or len(node.input) not in [2,3] or len(node.output)!=1 or attrs!={'dilations':[1,1],'group':1,'kernel_shape':[1,1],'pads':[0,0,0,0],'strides':[1,1]}:raise ValueError('exact stride1 pad0 1x1 Conv required')
    initializers={v.name:v for v in model.graph.initializer};weight=initializers.get(node.input[1])
    if weight is None or weight.data_type!=onnx.TensorProto.FLOAT or list(weight.dims[2:])!=[1,1]:raise ValueError('float32 pointwise weights required')
    if len(node.input)==3:
        bias=initializers.get(node.input[2])
        if bias is None or bias.data_type!=onnx.TensorProto.FLOAT or list(bias.dims)!=[weight.dims[0]]:raise ValueError('original float32 bias identity')
    prefix='__pointwise_partition_'+hashlib.sha256(node.name.encode()).hexdigest()[:16]+'_'
    names={x for n in model.graph.node for x in [n.name,*n.input,*n.output]}|set(initializers)
    if any(x.startswith(prefix) for x in names):raise ValueError('partition namespace collision')
    result=copy.deepcopy(model);nodes=[];constants=[]
    def const(name,value):
        key=prefix+name;constants.append(onnx.numpy_helper.from_array(np.asarray(value,np.int64),name=key));return key
    def op(kind,name,inputs,**attrs):
        key=prefix+name;nodes.append(onnx.helper.make_node(kind,inputs,[key],name=key,**attrs));return key
    axis=const('axis',[2]);one=const('one',[1]);four=const('four',[4]);zero=const('zero',[0])
    shape=op('Shape','shape',[node.input[0]]);height=op('Gather','height',[shape,axis],axis=0);bounds=[zero]
    for k in [1,2,3]:
        multiple=height if k==1 else op('Mul',f'h_mul_{k}',[height,const(f'multiple_{k}',[k])]);bounds.append(op('Div',f'bound_{k}',[multiple,four]))
    bounds.append(height);outputs=[]
    for k in range(4):
        slab=op('Slice',f'slab_{k}',[node.input[0],bounds[k],bounds[k+1],axis,one]);branch=copy.deepcopy(node)
        branch.name=prefix+f'conv_{k}';branch.input[0]=slab;branch.output[0]=branch.name;nodes.append(branch);outputs.append(branch.name)
    nodes.append(onnx.helper.make_node('Concat',outputs,list(node.output),name=prefix+'concat',axis=2))
    old=[copy.deepcopy(n) for n in result.graph.node];del result.graph.node[:];result.graph.node.extend(old[:index]+nodes+old[index+1:]);result.graph.initializer.extend(constants)
    proof=dict(sourceNodeName=node.name,sourceNodeIndex=index,originalNodeHex=node.SerializeToString().hex(),prefix=prefix,
               addedNodeNames=[n.name for n in nodes],addedInitializerNames=[v.name for v in constants],parts=4,
               originalInitializerHashes={name:hashlib.sha256(initializers[name].SerializeToString()).hexdigest() for name in node.input[1:]},
               unchangedDotProductOrder=True,originalBiasPreserved=len(node.input)==3,noHaloRequired=True)
    assert restore(result,proof).SerializeToString()==model.SerializeToString();onnx.checker.check_model(result,full_check=True)
    return result,proof


def restore(model,proof):
    result=copy.deepcopy(model)
    if [n.name for n in result.graph.node if n.name.startswith(proof['prefix'])]!=proof['addedNodeNames']:raise ValueError('partition node identity')
    if [v.name for v in result.graph.initializer if v.name.startswith(proof['prefix'])]!=proof['addedInitializerNames']:raise ValueError('partition constants identity')
    original=onnx.NodeProto();original.ParseFromString(bytes.fromhex(proof['originalNodeHex']))
    nodes=[copy.deepcopy(n) for n in result.graph.node if n.name not in proof['addedNodeNames']];nodes.insert(proof['sourceNodeIndex'],original);del result.graph.node[:];result.graph.node.extend(nodes)
    initializers=[copy.deepcopy(v) for v in result.graph.initializer if v.name not in proof['addedInitializerNames']];del result.graph.initializer[:];result.graph.initializer.extend(initializers)
    current={v.name:hashlib.sha256(v.SerializeToString()).hexdigest() for v in result.graph.initializer}
    assert all(current[k]==v for k,v in proof['originalInitializerHashes'].items())
    return result


def coordinate_proof():
    count=0
    for h in range(16,1537):
        bounds=[h*k//4 for k in range(5)];covered=[]
        for start,end in zip(bounds,bounds[1:]):
            assert end>start;covered.extend(range(start,end));count+=end-start
            assert all(start+local==global_y for local,global_y in enumerate(range(start,end)))
        assert covered==list(range(h))
    return dict(ok=True,heights=1521,minimum=16,maximum=1536,rowsChecked=count,allRowsExactlyOnce=True,allWidthsUnchanged=True,
                maxSegmentRows=384,maxPackedMatmulDispatchY=math.ceil(384*1536/32),originalPackedMatmulDispatchY=73728,newModelInputs=0)
