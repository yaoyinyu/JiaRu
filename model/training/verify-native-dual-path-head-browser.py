"""新双路径头的真实浏览器捕获重放；不继承旧模型通过结果。"""
from __future__ import annotations
import argparse
import importlib.util
import json
from pathlib import Path


def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value);return value


d=module('dual_browser_static',Path(__file__).with_name('audit-native-dual-path-head-feasibility.py'))
b=module('dual_browser_original',Path(__file__).with_name('verify-native-boundary-head-browser.py'))
a=d.a
b.s.validate=d.validate


def build(static_path,capture_path):
    static=a.read(static_path);plan=a.read(a.checked(static['inputs']['plan']))
    parent,_=d.validate(plan)
    if static['architecture']!=d.architecture_proof(parent['model']['seed']):raise ValueError('dual head identity')
    if plan['inputs']['browserVerifier']!=a.bind(Path(__file__)):raise ValueError('executed browser verifier not bound')
    report=b.build(static_path,capture_path)
    report['inputs']['sourceVerifier']=a.bind(Path(__file__))
    report['inputs']['originalVerifier']=a.bind(Path(b.__file__))
    report['architecture']=static['architecture']
    return report


def main():
    p=argparse.ArgumentParser();p.add_argument('--static-report',type=Path);p.add_argument('--capture',type=Path)
    p.add_argument('--output',type=Path);p.add_argument('--verify-report',type=Path);args=p.parse_args()
    if args.verify_report:
        saved=a.read(args.verify_report)
        for binding in saved['inputs'].values():a.checked(binding)
        report=build(Path(saved['inputs']['staticReport']['path']),Path(saved['inputs']['liveBrowser']['path']))
        if report!=saved:raise ValueError('dual browser report reconstruction_mismatch')
        path=args.verify_report
    else:
        report=build(args.static_report.resolve(),args.capture.resolve());a.write_new(args.output,report);path=args.output
    print(json.dumps({'ok':True,'decision':'verified' if args.verify_report else report['decision'],
                      'nativeCount':45,'capturedBinaryCount':len(report['capturedOutputs']),'report':a.bind(path)},ensure_ascii=False))


if __name__=='__main__':main()
