"""GroupNorm以原float32统计组合scale/bias；不声称普通Mul/Add具有CUDA FMA。"""
import copy
import hashlib
import numpy as np
import onnx
from onnx import helper,numpy_helper


def transform(source):
    nodes={n.name:n for n in source.graph.node};constants={v.name:numpy_helper.to_array(v) for v in source.graph.initializer}
    for n in source.graph.node:
        if n.op_type=='Constant':
            for a in n.attribute:
                if a.name=='value':constants[n.output[0]]=numpy_helper.to_array(a.t)
        elif n.op_type=='Identity' and n.input[0] in constants:constants[n.output[0]]=constants[n.input[0]]
    model=copy.deepcopy(source);targets={};prefixes=[];originals={};initializers=[];proof_rows=[]
    for i in range(16):
        normalized=nodes[f'blocked_gn_v1_{i}_normalized'];assert normalized.op_type=='Div'
        parent=normalized.output[0].rsplit('/',1)[0];reshape=nodes[parent+'/Reshape'];mul=nodes[parent+'/Mul'];add=nodes[parent+'/Add'];gamma=nodes[parent+'/Unsqueeze'].input[0];beta=nodes[parent+'/Unsqueeze_1'].input[0]
        assert mul.op_type=='Mul' and list(mul.input)==[nodes[parent+'/Reshape_1'].output[0],nodes[parent+'/Unsqueeze'].output[0]]
        assert add.op_type=='Add' and list(add.input)==[mul.output[0],nodes[parent+'/Unsqueeze_1'].output[0]]
        assert normalized.input[1]==f'blocked_gn_v1_{i}_std' and nodes[f'blocked_gn_v1_{i}_mean'].op_type=='Div'
        g,b=constants[gamma],constants[beta];assert g.dtype==b.dtype==np.float32 and g.ndim==b.ndim==1 and g.shape==b.shape and len(g)%4==0
        prefix=f'cuda_style_affine_v1_{i}_';prefixes.append(prefix)
        assert not any(n.name.startswith(prefix) for n in source.graph.node) and not any(v.name.startswith(prefix) for v in source.graph.initializer)
        changed=[]
        def const(label,value):
            name=prefix+label;model.graph.initializer.append(numpy_helper.from_array(value,name=name));initializers.append(name);return name
        def op(kind,inputs,label,**attrs):
            name=prefix+label;changed.append(helper.make_node(kind,inputs,[name],name=name,**attrs));return name
        one=const('one',np.array([1.],np.float32));axis=const('axis',np.array([2],np.int64));group_shape=const('group_shape',np.array([1,4,-1,1],np.int64));channel_shape=const('channel_shape',np.array([1,-1,1,1],np.int64))
        rstd=op('Div',[one,f'blocked_gn_v1_{i}_std'],'rstd');rstd=op('Unsqueeze',[rstd,axis],'rstd_group');mean=op('Unsqueeze',[f'blocked_gn_v1_{i}_mean',axis],'mean_group')
        gamma_group=op('Reshape',[gamma,group_shape],'gamma_group');beta_group=op('Reshape',[beta,group_shape],'beta_group');scale=op('Mul',[rstd,gamma_group],'scale');shift=op('Mul',[scale,mean],'mean_scaled');bias=op('Sub',[beta_group,shift],'bias')
        scale=op('Reshape',[scale,channel_shape],'scale_channel');bias=op('Reshape',[bias,channel_shape],'bias_channel');value=op('Mul',[reshape.input[0],scale],'scaled_input');terminal=prefix+'final'
        changed.append(helper.make_node('Add',[value,bias],list(add.output),name=terminal));targets[add.name]=changed;originals[terminal]=add.SerializeToString().hex()
        proof_rows.append(dict(group=i,originalAffine=add.name,input=reshape.input[0],gamma=gamma,beta=beta,channels=len(g),gammaBytesSha256=hashlib.sha256(g.tobytes()).hexdigest(),betaBytesSha256=hashlib.sha256(b.tobytes()).hexdigest()))
    replaced=[]
    for n in source.graph.node:replaced.extend(targets.get(n.name,[copy.deepcopy(n)]))
    del model.graph.node[:];model.graph.node.extend(replaced)
    proof=dict(sourceSha256=hashlib.sha256(source.SerializeToString()).hexdigest(),prefixes=prefixes,originalTerminals=originals,addedInitializers=initializers,targets=proof_rows,float32Only=True,
               momentsVarianceAndEpsilonUnchanged=True,learnedParametersUnchanged=True,actualFmaGuaranteed=False,algorithm='a=gamma*(1/sqrt(var+eps)); b=beta-a*mean; y=x*a+b',
               sourceReference='https://github.com/pytorch/pytorch/blob/7269437d655783a26cba32aa88195b741ff496aa/aten/src/ATen/native/cuda/group_norm_kernel.cu')
    assert restore(model,proof).SerializeToString()==source.SerializeToString();onnx.checker.check_model(model,full_check=True);return model,proof


def restore(model,proof):
    restored=copy.deepcopy(model);nodes=[];prefixes=tuple(proof['prefixes']);found=[]
    for node in model.graph.node:
        if node.name in proof['originalTerminals']:
            old=onnx.NodeProto();old.ParseFromString(bytes.fromhex(proof['originalTerminals'][node.name]));nodes.append(old);found.append(node.name)
        elif not node.name.startswith(prefixes):nodes.append(copy.deepcopy(node))
    assert set(found)==set(proof['originalTerminals']);del restored.graph.node[:];restored.graph.node.extend(nodes)
    initializers=[copy.deepcopy(v) for v in model.graph.initializer if v.name not in proof['addedInitializers']];del restored.graph.initializer[:];restored.graph.initializer.extend(initializers)
    assert hashlib.sha256(restored.SerializeToString()).hexdigest()==proof['sourceSha256'];return restored
