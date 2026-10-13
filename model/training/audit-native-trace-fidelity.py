"""只读盘点新增输出追踪的原结果保真，失败时禁止中间统计归因。"""
import argparse
import hashlib
import importlib.util
import json
import math
import os
import threading
import time
import urllib.parse
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import numpy as np
import onnx
import onnxruntime as ort

HERE=Path(__file__).resolve().parent
s=importlib.util.spec_from_file_location('tail_operator_data',HERE/'reviewed-role-development-data.py')
d=importlib.util.module_from_spec(s);s.loader.exec_module(d)


def resources(execution):
    e=d.read(d.bind(execution));helper=d.load(d.checked(e['auditor']),'fidelity_trace_source')
    return helper.resources(execution)


def shapes(case,index):
    target=case['operations'][index]['expected']['shape']
    if index==0:return [target,[],[],[],[target[2]],[target[2]],[],[],[],[target[3]],[target[3]]]
    return [target,[1],*[ [1,4,1] for _ in range(5) ]]


def sequence(p,backends):
    return [(b,index,c['ordinal']) for b in backends for index in range(2) for c in p['cases']]


def validate_event(event,pair,case,spec,page):
    b,index,o=pair
    if set(event)!={'backend','operationIndex','operation','ordinal','candidateIdentity','inputSha256','targetShape','inputRequestId','pageRequestId'} or event['backend']!=b or event['operationIndex']!=index or event['operation']!=spec['name'] or event['ordinal']!=o or event['candidateIdentity']!=case['candidateIdentity'] or event['inputSha256']!=case['operations'][index]['input']['sha256'] or event['targetShape']!=case['operations'][index]['expected']['shape'] or event['pageRequestId']!=page:raise ValueError('ordered same-input event')
    if str(uuid.UUID(event['inputRequestId']))!=event['inputRequestId']:raise ValueError('unique request ID')


def reconstruct(root):
    prep=d.read(d.bind(root/'preparation.json'))
    for key in ('execution','auditor','html','config','cpuCaptures','analyticalStatistics'):d.checked(prep[key])
    e,p,models,precision,layer,runtime,environment,prior=resources(d.checked(prep['execution']))
    if prep['runtimeFiles']!=runtime:raise ValueError('runtime assets')
    config=d.read(prep['config']);live=d.read(d.bind(root/'live-browser.json'))['value'];claim=d.read(d.bind(root/'claim.json'))['value']['pageRequestId']
    if live['executionSha256']!=prep['execution']['sha256'] or live['configSha256']!=config['configSha256'] or live['pageRequestId']!=claim or live['errors'] or live['phase']!='terminal' or not live['captureComplete'] or not live['crossOriginIsolated']:raise ValueError('complete browser terminal')
    if live['userAgent']!=environment['userAgent'] or live['adapterInfo']!=environment['adapterInfo']:raise ValueError('same browser environment')
    pairs=sequence(p,['wasm','webgpu']);cases={c['ordinal']:c for c in p['cases']}
    if len(live['records'])!=272 or len(live['startedInputs'])!=272 or len(list((root/'started-inputs').glob('*.json')))!=272 or len(list((root/'browser-capture').glob('*.bin')))!=2448:raise ValueError('full272 starts /2448 tensors')
    captured={'cpu':d.read(prep['cpuCaptures']),'wasm':[],'webgpu':[]};events=[];ids=[]
    for pair,event,rec in zip(pairs,live['startedInputs'],live['records'],strict=True):
        b,i,o=pair;c=cases[o];validate_event(event,pair,c,p['operations'][i],claim);path=root/'started-inputs'/f'{b}-{i}-{o}.json';st=d.read(d.bind(path))
        if st['value']!=event or st['startedAtUnixNs']<=(events[-1]['time'] if events else 0):raise ValueError('start persistence/order')
        if {k:rec[k] for k in event}!=event or len(rec['outputs'])!=len(models[i]['outputNames']):raise ValueError('actual trace schema')
        outputs=[]
        for j,(schema,name,shape) in enumerate(zip(rec['outputs'],models[i]['outputNames'],shapes(c,i),strict=True)):
            if schema!={'name':name,'shape':shape,'dtype':'float32'}:raise ValueError('actual output shape/name/dtype')
            outputs.append({'name':name,'tensor':d.bind(root/'browser-capture'/f'{b}-{i}-{o}-{j}.bin')|{'shape':shape,'dtype':'float32'}})
        captured[b].append(event|{'outputs':outputs});events.append({'binding':d.bind(path),'time':st['startedAtUnixNs']});ids.append(event['inputRequestId'])
    if len(set(ids))!=272:raise ValueError('unique inputs')
    cpu_events=[];finals=[]
    # 先核验全部后端原结果；任何失败均禁止返回统计结论。
    for b,rows in captured.items():
        if len(rows)!=136 or [(r['operationIndex'],r['ordinal']) for r in rows]!=[(i,o) for _,i,o in sequence(p,[b])]:raise ValueError('full136 order')
        for cap in rows:
            i,o=cap['operationIndex'],cap['ordinal'];op=cases[o]['operations'][i]
            if cap['candidateIdentity']!=cases[o]['candidateIdentity'] or cap['inputSha256']!=op['input']['sha256'] or cap['targetShape']!=op['expected']['shape']:raise ValueError('same frozen input')
            if b=='cpu':
                path=root/'cpu'/f'{i}-{o}-start.json';st=d.read(d.bind(path))
                if {k:st[k] for k in cap if k!='outputs'}!={k:v for k,v in cap.items() if k!='outputs'}:raise ValueError('CPU event')
                cpu_events.append(d.bind(path))
            for out,name,shape in zip(cap['outputs'],models[i]['outputNames'],shapes(cases[o],i),strict=True):
                if out['name']!=name or out['tensor']['shape']!=shape:raise ValueError('stored trace shape/name')
                layer.read_tensor(precision,out['tensor'])
            original=next(c for c in prior['captures'][b] if c['operationIndex']==i and c['ordinal']==o)
            a=layer.read_tensor(precision,original['output']);y=layer.read_tensor(precision,cap['outputs'][0]['tensor'])
            finals.append({'backend':b,'operationIndex':i,'operation':models[i]['name'],'ordinal':o,'candidateIdentity':cap['candidateIdentity'],'original':original['output'],'actual':cap['outputs'][0]['tensor'],'bitwiseEqual':a.shape==y.shape and a.tobytes()==y.tobytes(),'difference':layer.differences(a,y)})
    uploads=[d.bind(path) for path in sorted((root/'upload-events').glob('*.json'))];expected_routes=['/claim']+[route for b,i,o in pairs for route in [f'/start/{b}/{i}/{o}',*[f'/capture/{b}-{i}-{o}-{j}.bin' for j in range(len(models[i]['outputNames']))]]]+['/terminal']
    if [d.read(ref)['route'] for ref in uploads]!=expected_routes:raise ValueError('upload order')
    summary={b:{str(i):{'count':68,'bitwiseEqualCount':sum(r['bitwiseEqual'] for r in finals if r['backend']==b and r['operationIndex']==i),'changedOrdinals':[r['ordinal'] for r in finals if r['backend']==b and r['operationIndex']==i and not r['bitwiseEqual']],'maxAbsFromOwnUninstrumentedOutput':max(r['difference']['maxAbs'] for r in finals if r['backend']==b and r['operationIndex']==i)} for i in range(2)} for b in captured}
    gate=all(r['bitwiseEqual'] for r in finals)
    failure=d.read(d.bind(root/'audit-failure.json'))
    if failure['ok'] or failure['decision']!='reconstruction_mismatch' or not failure['productHold'] or gate:raise ValueError('preserve original fidelity failure')
    return {'schemaVersion':1,'ok':True,'decision':'failed_trace_fidelity_inventory_reconstructed_no_intermediate_conclusions','inputs':{'preparation':d.bind(root/'preparation.json'),'failedAudit':d.bind(root/'audit-failure.json'),'traceAuditor':prep['auditor'],'inventoryAuditor':d.bind(__file__),'liveBrowser':d.bind(root/'live-browser.json')},'captures':captured,'cpuStartEvents':cpu_events,'browserStartEvents':events,'uploadEvents':uploads,'finalOutputRecords':finals,'summary':summary,'allFinalOperatorOutputsBitwiseIdenticalAllBackends':False,'intermediateTraceConclusionsAllowed':False,'coordinateOrGroupNormRootCauseEstablished':False,'traceOperatorInputsPerBackend':{'cpu':136,'wasm':136,'webgpu':136},'analyticalFp64StatisticsPrepared':68,'newInventoryModelCalls':0,'newFullModelInputs':0,'newTorchInputs':0,'optimizerSteps':0,'valModelInputs':0,'protectedModelInputs':0,'transportErrors':live['transportErrors'],'persistedAckRecoveries':live['persistedAckRecoveries'],'uploadOnlyRetries':live['uploadOnlyRetries'],'originalFailuresAndMissingWasm22Preserved':True,'fullModelBrowserGatePassed':False,'formalReleaseAllowed':False,'productHold':True}


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--input',type=Path,required=True);parser.add_argument('--output',type=Path,required=True);parser.add_argument('--verify-report',action='store_true');args=parser.parse_args()
    result=reconstruct(args.input.resolve())
    if args.verify_report:
        if result!=d.read(d.bind(args.output)):raise ValueError('inventory reconstruction_mismatch')
    else:d.new(args.output,result)
    print(json.dumps({k:result[k] for k in ('ok','decision','allFinalOperatorOutputsBitwiseIdenticalAllBackends','intermediateTraceConclusionsAllowed','summary')}))
