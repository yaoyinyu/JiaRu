"""主机float32比例与末级GN分层求和，不修改学习参数或其余计算。"""
import numpy as np
import onnx
from onnx import helper,numpy_helper


def host_resize_ratios(model):
    before=onnx.ModelProto();before.CopyFrom(model);count=len(model.graph.initializer)
    if any(v.name=='hostRatios' for v in model.graph.input):raise ValueError('ratio input collision')
    targets=[n for n in model.graph.node if n.op_type=='Div' and n.output[0].endswith(('_y_ratio','_x_ratio'))]
    if len(targets)!=2 or [n.output[0].split('_')[-2] for n in targets]!=['y','x']:raise ValueError('two ordered scalar ratio nodes')
    for index,node in enumerate(targets):
        key=f'host_ratio_axis_{index}'
        if any(v.name==key for v in model.graph.initializer):raise ValueError('ratio constant collision')
        model.graph.initializer.append(numpy_helper.from_array(np.array(index,np.int64),name=key))
        node.CopyFrom(helper.make_node('Gather',['hostRatios',key],list(node.output),name=node.name,axis=0))
    model.graph.input.append(helper.make_tensor_value_info('hostRatios',onnx.TensorProto.FLOAT,[2]))
    restored=onnx.ModelProto();restored.CopyFrom(model);del restored.graph.initializer[count:];del restored.graph.input[-1:];del restored.graph.node[:];restored.graph.node.extend(before.graph.node)
    if restored.SerializeToString()!=before.SerializeToString():raise ValueError('non-ratio graph changed')
    onnx.checker.check_model(model,full_check=True)
    return model


def hierarchical_group_sum(model,prefix='stable_gn_209_'):
    before=onnx.ModelProto();before.CopyFrom(model);count=len(model.graph.initializer)
    names=[prefix+'mean_total_sum',prefix+'variance_total_sum'];found=[];updated=[]
    for node in before.graph.node:
        if node.name not in names:updated.append(node);continue
        if node.op_type!='ReduceSum' or len(node.input)!=2 or len(node.output)!=1:raise ValueError('expected total ReduceSum')
        stem='hierarchical_'+node.name+'_'
        def constant(name,value):
            key=stem+name
            if any(v.name==key for v in model.graph.initializer):raise ValueError('hierarchy name collision')
            model.graph.initializer.append(numpy_helper.from_array(np.array(value,np.int64),name=key));return key
        def op(kind,inputs,name,**attributes):
            out=stem+name;updated.append(helper.make_node(kind,inputs,[out],name=out,**attributes));return out
        last=constant('last',[-1]);first=constant('first',[0,1]);chunk=constant('chunk',[128]);rounding=constant('rounding',[127]);zeros=constant('zeros5',[0]*5);axis3=constant('axis3',[3])
        shape=op('Shape',[node.input[0]],'shape');length=op('Gather',[shape,last],'length',axis=0);head=op('Gather',[shape,first],'head',axis=0)
        extended=op('Add',[length,rounding],'extended');blocks=op('Div',[extended,chunk],'blocks');padded=op('Mul',[blocks,chunk],'padded');extra=op('Sub',[padded,length],'extra')
        pads=op('Concat',[zeros,extra],'pads',axis=0);target=op('Concat',[head,blocks,chunk],'target_shape',axis=0)
        value=op('Pad',[node.input[0],pads],'padded_value',mode='constant');matrix=op('Reshape',[value,target],'matrix');sums=op('ReduceSum',[matrix,axis3],'block_sum',keepdims=0)
        final=onnx.NodeProto();final.CopyFrom(node);final.input[0]=sums;updated.append(final);found.append(node.name)
    if found!=names:raise ValueError('both ordered mean and variance targets required')
    del model.graph.node[:];model.graph.node.extend(updated)
    restored=onnx.ModelProto();restored.CopyFrom(model);del restored.graph.initializer[count:];del restored.graph.node[:];restored.graph.node.extend(before.graph.node)
    if restored.SerializeToString()!=before.SerializeToString():raise ValueError('parameters / epsilon / graph metadata changed')
    onnx.checker.check_model(model,full_check=True)
    return model
