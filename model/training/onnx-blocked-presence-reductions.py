"""presence三处空间归约改为float32分块累加，原节点/初始量可完整恢复。"""
import copy
import hashlib
import numpy as np
import onnx
from onnx import helper,numpy_helper


def inventory(model):
    constants={v.name:numpy_helper.to_array(v) for v in model.graph.initializer}
    for n in model.graph.node:
        if n.op_type=='Constant':
            for a in n.attribute:
                if a.name=='value':constants[n.output[0]]=numpy_helper.to_array(a.t)
    expected={'/ReduceSum':('ReduceSum','/Mul_28_output_0'),'/ReduceSum_1':('ReduceSum','/Div_12_output_0'),'/ReduceMean':('ReduceMean','/enc3/enc3.5/Mul_1_output_0')};targets=[]
    for n in model.graph.node:
        if n.name not in expected:continue
        op,source=expected[n.name];attrs={a.name:helper.get_attribute_value(a) for a in n.attribute}
        if n.op_type!=op or n.input[0]!=source or len(n.input)!=2 or attrs.get('keepdims',1)!=0 or list(constants.get(n.input[1],[]))!=[2,3]:raise ValueError('exact original spatial presence reduction required')
        targets.append(n)
    if len(targets)!=3:raise ValueError('complete three-reduction denominator')
    return targets


def transform(source):
    targets=inventory(source);model=copy.deepcopy(source);mapping={n.name:i for i,n in enumerate(targets)};new=[];added=[];prefixes=[];terminals={}
    for node in source.graph.node:
        if node.name not in mapping:new.append(copy.deepcopy(node));continue
        i=mapping[node.name];prefix=f'blocked_presence_v1_{i}_';prefixes.append(prefix)
        if any(n.name.startswith(prefix) for n in source.graph.node) or any(v.name.startswith(prefix) for v in source.graph.initializer):raise ValueError('prefix collision')
        def const(label,value):
            name=prefix+label;t=numpy_helper.from_array(np.asarray(value,np.int64),name=name);model.graph.initializer.append(t);added.append(name);return name
        def op(kind,inputs,label,**attrs):
            name=prefix+label;new.append(helper.make_node(kind,inputs,[name],name=name,**attrs));return name
        target=const('flat_shape',[0,0,-1]);last=const('last',[-1]);axes01=const('axes01',[0,1]);axis3=const('axis3',[3]);axis2=const('axis2',[2]);chunk=const('chunk',[128]);rounding=const('rounding',[127]);zeros5=const('zeros5',[0,0,0,0,0])
        value=op('Reshape',[node.input[0],target],'flat');original_shape=op('Shape',[value],'original_shape');length=op('Gather',[original_shape,last],'count',axis=0);count=op('Cast',[length],'float_count',to=onnx.TensorProto.FLOAT)
        for level in range(3):
            stem=f'level{level}_';shape=op('Shape',[value],stem+'shape');length=op('Gather',[shape,last],stem+'length',axis=0);head=op('Gather',[shape,axes01],stem+'head',axis=0)
            extended=op('Add',[length,rounding],stem+'extended');blocks=op('Div',[extended,chunk],stem+'blocks');size=op('Mul',[blocks,chunk],stem+'size');extra=op('Sub',[size,length],stem+'extra');pads=op('Concat',[zeros5,extra],stem+'pads',axis=0);dims=op('Concat',[head,blocks,chunk],stem+'dims',axis=0)
            padded=op('Pad',[value,pads],stem+'pad',mode='constant');matrix=op('Reshape',[padded,dims],stem+'matrix');value=op('ReduceSum',[matrix,axis3],stem+'sum',keepdims=0)
        total=op('ReduceSum',[value,axis2],'total',keepdims=1)
        if node.op_type=='ReduceMean':total=op('Div',[total,count],'mean')
        name=prefix+'final';new.append(helper.make_node('Squeeze',[total,axis2],list(node.output),name=name));terminals[name]=node.SerializeToString().hex()
    del model.graph.node[:];model.graph.node.extend(new)
    proof=dict(originalModelSha256=hashlib.sha256(source.SerializeToString()).hexdigest(),prefixes=prefixes,terminalOriginalNodes=terminals,addedInitializerNames=added,
               threeReductions=[n.name for n in targets],chunk=128,levels=3,float32Only=True,originalAxesAndDenominatorPreserved=True,allWeightsBiasAndThresholdsUnchanged=True)
    if restore(model,proof).SerializeToString()!=source.SerializeToString():raise ValueError('full graph inverse bytes mismatch')
    onnx.checker.check_model(model,full_check=True);return model,proof


def restore(model,proof):
    restored=copy.deepcopy(model);nodes=[];prefixes=tuple(proof['prefixes']);found=[]
    for n in model.graph.node:
        if n.name in proof['terminalOriginalNodes']:
            old=onnx.NodeProto();old.ParseFromString(bytes.fromhex(proof['terminalOriginalNodes'][n.name]));nodes.append(old);found.append(n.name)
        elif not n.name.startswith(prefixes):nodes.append(copy.deepcopy(n))
    if set(found)!=set(proof['terminalOriginalNodes']):raise ValueError('missing original reduction terminals')
    del restored.graph.node[:];restored.graph.node.extend(nodes);initializers=[copy.deepcopy(v) for v in restored.graph.initializer if v.name not in proof['addedInitializerNames']];del restored.graph.initializer[:];restored.graph.initializer.extend(initializers)
    if hashlib.sha256(restored.SerializeToString()).hexdigest()!=proof['originalModelSha256']:raise ValueError('inverse source identity mismatch')
    return restored
