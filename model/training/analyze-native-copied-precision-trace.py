"""只读复算副本坐标运算链与GN求和/除法，不作完整模型因果或质量结论。"""
import argparse
import importlib.util
import json
from pathlib import Path

import numpy as np

HERE=Path(__file__).resolve().parent
s=importlib.util.spec_from_file_location('copied_trace_analysis_data',HERE/'reviewed-role-development-data.py')
d=importlib.util.module_from_spec(s);s.loader.exec_module(d)


def coordinates(ratio,incoming,outgoing):
    centered=np.float32(np.arange(outgoing,dtype=np.float32)+np.float32(.5))
    shifted=np.float32(np.float32(ratio*centered)-np.float32(.5))
    clipped=np.maximum(shifted,np.float32(0));lower=np.minimum(np.floor(clipped).astype(np.int64),incoming-1).astype(np.float32)
    return shifted,np.float32(clipped-lower)


def reconstruct(contract):
    plan=d.read(d.bind(contract));report=d.read(plan['traceReport']);d.checked(plan['auditor'])
    if plan['auditor']!=d.bind(__file__) or plan['newModelCallsAllowed']!=0 or plan['newFp64StatisticsInputsAllowed']!=0 or plan['fullModelCausalConclusionAllowed'] or plan['formalReleaseAllowed'] or not plan['productHold']:raise ValueError('readonly diagnostic contract')
    if not report['ok'] or not report['allFinalOperatorOutputsBitwiseIdenticalAllBackends'] or report['traceOperatorInputsPerBackend']!={'cpu':136,'wasm':136,'webgpu':136}:raise ValueError('all68 original-output fidelity before conclusions')
    prep=d.read(report['inputs']['preparation']);execution=d.read(prep['execution']);scope=d.read(execution['scope'])
    for ref in [report['inputs']['auditor'],*execution['helpers'].values()]:d.checked(ref)
    precision=d.load(d.checked(execution['helpers']['buffer']),'analysis_buffer');layer=d.load(d.checked(execution['helpers']['layer']),'analysis_layer')
    fp64=d.read(prep['analyticalStatistics']);cases=scope['cases'];rows=[]
    if len(cases)!=68 or len(fp64)!=68:raise ValueError('whole68 statistics and identities')
    for backend,records in report['captures'].items():
        if len(records)!=136 or [(r['operationIndex'],r['ordinal']) for r in records]!=[(i,o) for i in range(2) for o in range(1,69)]:raise ValueError('whole ordered backend scope')
        for cap in records:
            i,o=cap['operationIndex'],cap['ordinal'];case=cases[o-1]
            if cap['candidateIdentity']!=case['candidateIdentity'] or fp64[o-1]['candidateIdentity']!=case['candidateIdentity']:raise ValueError('stable train identity')
            outs={t['name']:layer.read_tensor(precision,t['tensor']) for t in cap['outputs'][1:]}
            row={'backend':backend,'operationIndex':i,'ordinal':o,'candidateIdentity':case['candidateIdentity']}
            if i==0:
                axes=[]
                for axis,label in ((2,'y'),(3,'x')):
                    incoming=case['operations'][i]['input']['shape'][axis];outgoing=case['operations'][i]['expected']['shape'][axis];prefix=f'native_bilinear_0_{label}_'
                    if float(outs[prefix+'input_float'])!=incoming or float(outs[prefix+'output_float'])!=outgoing:raise ValueError('coordinate operand / source dimensions')
                    observed=outs[prefix+'ratio'];ieee=np.float32(np.float32(incoming)/np.float32(outgoing)).reshape(())
                    shifted,weight=coordinates(observed,incoming,outgoing)
                    axes.append({'axis':label,'inputSize':incoming,'outputSize':outgoing,'observedRatio':float(observed),'ieeeFloat32Ratio':float(ieee),'ratioUlpDifference':abs(int(observed.view(np.uint32))-int(ieee.view(np.uint32))),
                                 'shiftedReconstructedFromOwnRatioBitwise':shifted.tobytes()==outs['observation_'+prefix+'shifted'].tobytes(),'weightReconstructedFromOwnRatioBitwise':weight.tobytes()==outs['observation_'+prefix+'lambda1'].tobytes()})
                row['axes']=axes
            else:
                count=case['operations'][i]['input']['shape'][2]*case['operations'][i]['input']['shape'][3]*4
                if fp64[o-1]['count']!=count or float(outs['stable_gn_209_count'][0])!=count:raise ValueError('GN original count')
                row['count']=count;row['statistics']={}
                for name in ('mean','variance'):
                    total=outs[f'stable_gn_209_{name}_total_sum'];value=outs[f'stable_gn_209_{name}'];own_div=np.float32(total/np.float32(count))
                    row['statistics'][name]={'divisionReconstructedFromOwnSumBitwise':own_div.tobytes()==value.tobytes(),'maxAbsOwnDivision':float(np.max(np.abs(own_div.astype(np.float64)-value.astype(np.float64)))),
                                             'maxAbsDiagnosticFp64':float(np.max(np.abs(value.astype(np.float64)-np.asarray(fp64[o-1][name],np.float64))))}
            rows.append(row)
    summary={backend:{'resize':{'candidateCount':68,'ratioDifferentOrdinals':[r['ordinal'] for r in rows if r['backend']==backend and r['operationIndex']==0 and any(a['ratioUlpDifference'] for a in r['axes'])],
                                  'maxRatioUlpDifference':max(a['ratioUlpDifference'] for r in rows if r['backend']==backend and r['operationIndex']==0 for a in r['axes']),
                                  'coordinateOrWeightNotExplainedByOwnRatioOrdinals':[r['ordinal'] for r in rows if r['backend']==backend and r['operationIndex']==0 and any(not a['shiftedReconstructedFromOwnRatioBitwise'] or not a['weightReconstructedFromOwnRatioBitwise'] for a in r['axes'])]},
                      'groupNorm':{'candidateCount':68,'ownSumDivisionMismatchOrdinals':{name:[r['ordinal'] for r in rows if r['backend']==backend and r['operationIndex']==1 and not r['statistics'][name]['divisionReconstructedFromOwnSumBitwise']] for name in ('mean','variance')},
                                   'maxDiagnosticFp64Error':{name:max(r['statistics'][name]['maxAbsDiagnosticFp64'] for r in rows if r['backend']==backend and r['operationIndex']==1) for name in ('mean','variance')}}} for backend in report['captures']}
    return {'schemaVersion':1,'ok':True,'decision':'copied_trace_float32_chain_and_statistics_reconstructed_readonly','inputs':{'contract':d.bind(contract),'traceReport':plan['traceReport'],'auditor':d.bind(__file__),'preparedFp64Statistics':prep['analyticalStatistics']},'records':rows,'summary':summary,'originalOutputFidelityGateInherited':True,'newModelCalls':0,'newFp64StatisticsInputs':0,'newSourcePixelsRead':0,'newChatImageInputs':0,'optimizerSteps':0,'coordinateChainNotFullModelCausalProof':True,'fp64StatisticsNotCudaReference':True,'fullModelBrowserGatePassed':False,'formalReleaseAllowed':False,'productHold':True}


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--contract',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--verify-report',action='store_true');a=p.parse_args();result=reconstruct(a.contract.resolve())
    if a.verify_report:
        if result!=d.read(d.bind(a.output)):raise ValueError('analysis reconstruction_mismatch')
    else:d.new(a.output,result)
    print(json.dumps({k:result[k] for k in ('ok','decision','summary','newModelCalls')}))
