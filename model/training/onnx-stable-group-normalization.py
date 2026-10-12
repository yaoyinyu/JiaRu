"""将GroupNorm的恒等InstanceNorm内核改为分块稳定float32统计，不改可学参数。"""
import onnx
import numpy as np
from onnx import helper,numpy_helper
def rewrite(path):
 model=onnx.load(path);graph=model.graph;constants={i.name:numpy_helper.to_array(i) for i in graph.initializer}
 for node in graph.node:
  if node.op_type=='Constant':
   for attr in node.attribute:
    if attr.name=='value':constants[node.output[0]]=numpy_helper.to_array(attr.t)
 converted=[];nodes=[]
 for index,node in enumerate(graph.node):
  if node.op_type!='InstanceNormalization':nodes.append(node);continue
  if not np.array_equal(constants.get(node.input[1]),np.ones(4,np.float32)) or not np.array_equal(constants.get(node.input[2]),np.zeros(4,np.float32)):
   raise ValueError('InstanceNorm is not the expected identity GroupNorm inner kernel')
  prefix=f'stable_gn_{index}_';epsilon=next(float(a.f) for a in node.attribute if a.name=='epsilon')
  def initializer(name,array):
   key=prefix+name;graph.initializer.append(numpy_helper.from_array(np.asarray(array),name=key));return key
  last=initializer('last',np.array([-1],np.int64));first=initializer('first',np.array([0,1],np.int64));axis3=initializer('axis3',np.array([3],np.int64));axis2=initializer('axis2',np.array([2],np.int64))
  zero=initializer('zero',np.array([0],np.int64));zeros5=initializer('zeros5',np.zeros(5,np.int64));chunk=initializer('chunk',np.array([128],np.int64));rounding=initializer('rounding',np.array([127],np.int64));eps=initializer('eps',np.array([epsilon],np.float32))
  def op(kind,inputs,name,**attrs):
   output=prefix+name;nodes.append(helper.make_node(kind,inputs,[output],name=output,**attrs));return output
  shape=op('Shape',[node.input[0]],'shape');length=op('Gather',[shape,last],'length',axis=0);head=op('Gather',[shape,first],'head',axis=0)
  extended=op('Add',[length,rounding],'extended');blocks=op('Div',[extended,chunk],'blocks');padded=op('Mul',[blocks,chunk],'padded');extra=op('Sub',[padded,length],'extra')
  pads=op('Concat',[zeros5,extra],'pads',axis=0);target_shape=op('Concat',[head,blocks,chunk],'target_shape',axis=0);count=op('Cast',[length],'count',to=onnx.TensorProto.FLOAT)
  def stable_sum(value,label):
   padded_value=op('Pad',[value,pads],label+'_pad',mode='constant');matrix=op('Reshape',[padded_value,target_shape],label+'_blocks')
   block_sums=op('ReduceSum',[matrix,axis3],label+'_block_sum',keepdims=0)
   return op('ReduceSum',[block_sums,axis2],label+'_total_sum',keepdims=1)
  mean=op('Div',[stable_sum(node.input[0],'mean'),count],'mean');centered=op('Sub',[node.input[0],mean],'centered')
  squared=op('Mul',[centered,centered],'squared');variance=op('Div',[stable_sum(squared,'variance'),count],'variance')
  shifted=op('Add',[variance,eps],'shifted');std=op('Sqrt',[shifted],'std')
  nodes.append(helper.make_node('Div',[centered,std],list(node.output),name=prefix+'normalized'))
  converted.append({'node':node.name,'epsilon':epsilon,'chunkLength':128,'math':'mean and centered variance over same flattened group; learned affine after node retained'})
 if len(converted)!=10:raise ValueError('expected all10 GroupNorm inner kernels')
 del graph.node[:];graph.node.extend(nodes);onnx.checker.check_model(model,full_check=True);onnx.save(model,path)
 return converted
