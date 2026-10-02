"""保持冻结BF16训练配方，仅替换Windows不安全的覆盖式执行记录。"""
from pathlib import Path
import json
import argparse
import importlib.util


def load(name,filename):
    spec=importlib.util.spec_from_file_location(name,Path(__file__).with_name(filename))
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


t=load('bf16_frozen_executor','train-conditional-nail-refinement-bf16-microfit.py')
j=load('bf16_execution_journal','conditional-refinement-execution-journal.py')
original_validate=t.validate


def validate(plan):
    records,feasibility=original_validate(plan)
    previous=t.a.read(t.a.checked(plan['inputs']['previousNumericalRepairPlan']))
    failure=t.a.read(t.a.checked(plan['inputs']['previousIoFailure']))
    for b in failure['inputs'].values():t.a.checked(b)
    for b in previous['inputs'].values():t.a.checked(b)
    for key in ['candidateIds','approval','training','loss','gates','precision','repairBudget','cacheCleanupRoots','full30PilotAllowed']:
        if plan[key]!=previous[key]:raise ValueError(f'IO repair changed frozen training contract: {key}')
    if failure['inputs']['plan']!=plan['inputs']['previousNumericalRepairPlan'] or not failure['budget']['attemptConsumed'] or failure['budget']['originalAttemptMayRestart']:raise ValueError('IO failure identity/budget')
    if plan['ioRepairBudget']!={'maximumExperiments':1,'previousAttemptMayRestart':False,'recording':'immutable per-event files; terminal snapshot once; distinct forensic checkpoint per8epochs'}:raise ValueError('once-only IO repair')
    return records,feasibility


def verify(path):
    result=t.verify(path);report=t.a.read(path);state=t.a.read(path.parent/'progress.json')
    result['journal']=j.verify_events(path.parent,state,report['history'])
    return result


def main():
    p=argparse.ArgumentParser();p.add_argument('--plan',type=Path);p.add_argument('--output',type=Path);p.add_argument('--verify-report',type=Path);args=p.parse_args()
    t.validate=validate;t.atomic_json=j.ExecutionJournal().write;t.forensic_checkpoint=j.checkpoint
    guard=t.old.load('journal_guard','train-yolo-seg.py');guard.install_read_only_ultralytics_image_check()
    plan=t.a.read(args.plan if args.plan else t.a.read(args.verify_report)['inputs']['plan']['path'])
    try:
        result=verify(args.verify_report) if args.verify_report else t.train(args.plan.resolve(),args.output.resolve())
        print(json.dumps({k:result[k] for k in ['ok','decision','metrics']},ensure_ascii=False),flush=True)
    finally:
        for root in plan['cacheCleanupRoots']:guard.remove_ultralytics_label_caches(Path(root))


if __name__=='__main__':main()
