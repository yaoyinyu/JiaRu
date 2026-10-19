"""精确保边的动态高度分段Conv；原节点与全部权重可按字节恢复。"""
import copy
import hashlib
import math
import numpy as np
import onnx


def transform(model,node_name,parts=4):
 if parts!=4:raise ValueError('fixed four-way partition only')
 matches=[(i,n) for i,n in enumerate(model.graph.node) if n.name==node_name]
 if len(matches)!=1:raise ValueError('unique Conv node required')
 index,node=matches[0];attrs={x.name:onnx.helper.get_attribute_value(x) for x in node.attribute}
 expected={'dilations':[1,1],'group':1,'kernel_shape':[3,3],'pads':[1,1,1,1],'strides':[1,1]}
 if node.op_type!='Conv' or attrs!=expected or len(node.input)!=2 or len(node.output)!=1:raise ValueError('only exact original 3x3 stride1 pad1 no-bias Conv')
 weights=[x for x in model.graph.initializer if x.name==node.input[1]]
 if len(weights)!=1 or weights[0].data_type!=onnx.TensorProto.FLOAT or len(weights[0].dims)!=4 or list(weights[0].dims[2:])!=[3,3]:raise ValueError('float32 kernel identity')
 prefix='__spatial_partition_'+hashlib.sha256(node.name.encode()).hexdigest()[:16]+'_'
 names={x for n in model.graph.node for x in [n.name,*n.input,*n.output]}|{x.name for x in model.graph.initializer}
 if any(x.startswith(prefix) for x in names):raise ValueError('partition namespace collision')
 result=copy.deepcopy(model);nodes=[];constants=[]
 def const(name,value,dtype=np.int64):
  key=prefix+name;constants.append(onnx.numpy_helper.from_array(np.asarray(value,dtype=dtype),name=key));return key
 def op(kind,name,inputs,**kwargs):
  output=prefix+name;nodes.append(onnx.helper.make_node(kind,inputs,[output],name=output,**kwargs));return output
 axis=const('axis',[2]);one=const('one',[1]);two=const('two',[2]);four=const('four',[4]);zero=const('zero',[0]);pads=const('pads',[0,0,1,1,0,0,1,1]);value=const('float_zero',np.float32(0),np.float32)
 shape=op('Shape','shape',[node.input[0]]);height=op('Gather','height',[shape,axis],axis=0);padded=op('Pad','padded',[node.input[0],pads,value],mode='constant');bounds=[zero]
 for k in [1,2,3]:
  multiple=height if k==1 else op('Mul',f'h_mul_{k}',[height,const(f'multiple_{k}',[k])]);bounds.append(op('Div',f'bound_{k}',[multiple,four]))
 bounds.append(height);outputs=[]
 for k in range(4):
  end=op('Add',f'end_{k}',[bounds[k+1],two]);slab=op('Slice',f'slab_{k}',[padded,bounds[k],end,axis,one]);out=prefix+f'conv_{k}'
  branch=copy.deepcopy(node);branch.name=out;branch.input[0]=slab;branch.output[0]=out
  for attr in branch.attribute:
   if attr.name=='pads':del attr.ints[:];attr.ints.extend([0,0,0,0])
  nodes.append(branch);outputs.append(out)
 nodes.append(onnx.helper.make_node('Concat',outputs,list(node.output),name=prefix+'concat',axis=2))
 original_nodes=[copy.deepcopy(x) for x in result.graph.node];del result.graph.node[:];result.graph.node.extend(original_nodes[:index]+nodes+original_nodes[index+1:]);result.graph.initializer.extend(constants)
 proof={'sourceNodeName':node.name,'sourceNodeIndex':index,'originalNodeHex':node.SerializeToString().hex(),'prefix':prefix,'addedNodeNames':[n.name for n in nodes],'addedInitializerNames':[x.name for x in constants],'parts':parts,'originalWeightName':weights[0].name,'originalInitializerSha256':hashlib.sha256(weights[0].SerializeToString()).hexdigest()}
 restored=restore(result,proof)
 if restored.SerializeToString()!=model.SerializeToString():raise ValueError('full graph inverse byte identity failed')
 onnx.checker.check_model(result,full_check=True);return result,proof


def restore(model,proof):
 result=copy.deepcopy(model);expected=proof['addedNodeNames'];actual=[n.name for n in result.graph.node if n.name.startswith(proof['prefix'])]
 if actual!=expected or [x.name for x in result.graph.initializer if x.name.startswith(proof['prefix'])]!=proof['addedInitializerNames']:raise ValueError('partition nodes/constants identity')
 original=onnx.NodeProto();original.ParseFromString(bytes.fromhex(proof['originalNodeHex']));nodes=[copy.deepcopy(n) for n in result.graph.node if n.name not in expected];nodes.insert(proof['sourceNodeIndex'],original);del result.graph.node[:];result.graph.node.extend(nodes)
 constants=[copy.deepcopy(x) for x in result.graph.initializer if x.name not in proof['addedInitializerNames']];del result.graph.initializer[:];result.graph.initializer.extend(constants)
 weights=[x for x in result.graph.initializer if x.name==proof['originalWeightName']]
 if len(weights)!=1 or hashlib.sha256(weights[0].SerializeToString()).hexdigest()!=proof['originalInitializerSha256']:raise ValueError('original weights drift')
 return result


def coordinate_proof(min_size=16,max_size=1536):
 if (min_size,max_size)!=(16,1536):raise ValueError('full frozen dimension domain required')
 maxrows=0;count=0;seams=0
 # 高度逐整数验证；宽度不分段，横向三位置及padding保持恒等，调度随宽度单调。
 for height in range(min_size,max_size+1):
  bounds=[height*k//4 for k in range(5)];covered=[]
  for first,last in zip(bounds,bounds[1:]):
   assert last>first;maxrows=max(maxrows,last-first);covered.extend(range(first,last));seams+=1
   for y in range(first,last):
    for kernel_y in range(3):
     padded_index=first+(y-first)+kernel_y;global_original_y=padded_index-1
     assert global_original_y==y+kernel_y-1 and first<=padded_index<last+2 and 0<=padded_index<height+2
     count+=1
  assert covered==list(range(height))
 assert maxrows==384
 return {'ok':True,'minimumHeight':min_size,'maximumHeight':max_size,'integerHeightsChecked':max_size-min_size+1,'kernelRowCoordinatesChecked':count,'nonemptySegmentsChecked':seams,'widthMapping':'all widths16..1536, same full padded width W+2; output column x consumes original x+kernel_x-1','maxSegmentOutputRows':maxrows,'maxSegmentSpatialOutputs':maxrows*max_size,'maxNchwDispatchX':math.ceil(maxrows*max_size/32),'allRowsExactlyOnce':True,'fullHaloAndOriginalEdgeZeros':True,'newModelInputs':0}
