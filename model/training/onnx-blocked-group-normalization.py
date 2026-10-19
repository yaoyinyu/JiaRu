"""仅展开恒等GroupNorm内核为float32三级分块统计，可逐字节逆变换。"""
import copy
import numpy as np
import onnx
from onnx import helper,numpy_helper


def inventory(model):
 constants={v.name:numpy_helper.to_array(v) for v in model.graph.initializer}
 for node in model.graph.node:
  if node.op_type=='Constant':
   for attr in node.attribute:
    if attr.name=='value':constants[node.output[0]]=numpy_helper.to_array(attr.t)
  elif node.op_type=='Identity' and node.input[0] in constants:constants[node.output[0]]=constants[node.input[0]]
 result=[]
 for node in model.graph.node:
  if node.op_type!='InstanceNormalization':continue
  scale=constants.get(node.input[1]);bias=constants.get(node.input[2])
  if scale is None or bias is None or scale.dtype!=np.float32 or bias.dtype!=np.float32 or not np.array_equal(scale,np.ones(4,np.float32)) or not np.array_equal(bias,np.zeros(4,np.float32)):raise ValueError('nonidentity GroupNorm inner affine')
  epsilon=[a.f for a in node.attribute if a.name=='epsilon']
  if len(epsilon)!=1 or epsilon[0]<=0:raise ValueError('explicit positive epsilon required')
  result.append({'node':node.name,'inputs':list(node.input),'outputs':list(node.output),'epsilonFloat32':float(np.float32(epsilon[0]))})
 if not result or len({r['node'] for r in result})!=len(result):raise ValueError('unique GroupNorm targets required')
 return result


def rewrite(model,targets):
 original=copy.deepcopy(model)
 if inventory(original)!=targets:raise ValueError('actual semantic targets mismatch')
 names={r['node']:i for i,r in enumerate(targets)};new=[];prefixes=[]
 for node in original.graph.node:
  if node.name not in names:new.append(node);continue
  index=names[node.name];prefix=f'blocked_gn_v1_{index}_';prefixes.append(prefix)
  if any(n.name.startswith(prefix) for n in original.graph.node) or any(v.name.startswith(prefix) for v in original.graph.initializer):raise ValueError('prefix collision')
  def const(label,value):
   name=prefix+label;model.graph.initializer.append(numpy_helper.from_array(value,name=name));return name
  def op(kind,inputs,label,**attrs):
   name=prefix+label;new.append(helper.make_node(kind,inputs,[name],name=name,**attrs));return name
  last=const('last',np.array([-1],np.int64));head_axes=const('head_axes',np.array([0,1],np.int64));axis3=const('axis3',np.array([3],np.int64));axis2=const('axis2',np.array([2],np.int64));chunk=const('chunk',np.array([128],np.int64));rounding=const('rounding',np.array([127],np.int64));zeros5=const('zeros5',np.zeros(5,np.int64));eps=const('epsilon',np.array([targets[index]['epsilonFloat32']],np.float32))
  shape=op('Shape',[node.input[0]],'shape');length=op('Gather',[shape,last],'length',axis=0);count=op('Cast',[length],'count',to=onnx.TensorProto.FLOAT)
  def blocked_sum(value,label):
   for level in range(3):
    stem=label+str(level)+'_';shape=op('Shape',[value],stem+'shape');length=op('Gather',[shape,last],stem+'length',axis=0);head=op('Gather',[shape,head_axes],stem+'head',axis=0)
    extended=op('Add',[length,rounding],stem+'extended');blocks=op('Div',[extended,chunk],stem+'blocks');size=op('Mul',[blocks,chunk],stem+'size');extra=op('Sub',[size,length],stem+'extra');pads=op('Concat',[zeros5,extra],stem+'pads',axis=0);target=op('Concat',[head,blocks,chunk],stem+'target',axis=0)
    padded=op('Pad',[value,pads],stem+'pad',mode='constant');matrix=op('Reshape',[padded,target],stem+'matrix');value=op('ReduceSum',[matrix,axis3],stem+'sum',keepdims=0)
   return op('ReduceSum',[value,axis2],label+'total',keepdims=1)
  mean=op('Div',[blocked_sum(node.input[0],'mean_'),count],'mean');centered=op('Sub',[node.input[0],mean],'centered');squared=op('Mul',[centered,centered],'squared');var=op('Div',[blocked_sum(squared,'variance_'),count],'variance');shifted=op('Add',[var,eps],'shifted');std=op('Sqrt',[shifted],'std')
  new.append(helper.make_node('Div',[centered,std],list(node.output),name=prefix+'normalized'))
 del model.graph.node[:];model.graph.node.extend(new)
 # 删除全部新增节点/常量并按最终输出位置放回旧节点，必须恢复完整ModelProto字节。
 restored=copy.deepcopy(model);nodes=[];mapping={f'blocked_gn_v1_{i}_normalized':n for n in original.graph.node if n.name in names for i in [names[n.name]]}
 for node in model.graph.node:
  if node.name in mapping:nodes.append(mapping[node.name])
  elif not any(node.name.startswith(prefix) for prefix in prefixes):nodes.append(node)
 del restored.graph.node[:];restored.graph.node.extend(nodes);del restored.graph.initializer[len(original.graph.initializer):]
 if restored.SerializeToString()!=original.SerializeToString():raise ValueError('inverse does not restore exact graph bytes')
 onnx.checker.check_model(model,full_check=True)
 return model,{'targets':targets,'chunk':128,'levels':3,'float32Only':True,'allOtherGraphAndInitializersInverseByteExact':True,'affineAndEpsilonUnchanged':True,'originalModelSha256':__import__('hashlib').sha256(original.SerializeToString()).hexdigest()}
