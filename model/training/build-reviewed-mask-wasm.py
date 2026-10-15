"""编译隔离高精度mask WASM，冻结源码、工具链、参数和实际模块字节。"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[2]
EXPORTS = ['promote', 'conv3', 'gn4', 'gelu', 'pool2', 'resize64', 'final_mask', 'erf64', '__heap_base']


def binding(path):
    path = Path(path).resolve(strict=True)
    return {'path': str(path), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}


def new(path, data):
    with Path(path).open('xb') as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())


def build(compiler, output):
    output = output.resolve()
    if not output.is_relative_to(ROOT / 'model/reviews'):
        raise ValueError('isolated review output required')
    source = ROOT / 'model/runtime/nail-mask-f64.c'
    runtime = ROOT / 'model/runtime/nail-mask-f64.mjs'
    compiler = compiler.resolve(strict=True)
    linker = compiler.with_name('wasm-ld.exe')
    version = subprocess.run([str(compiler), '--version'], capture_output=True, check=True)
    resource = subprocess.run([str(compiler), '-print-resource-dir'], capture_output=True, check=True)
    header = Path(resource.stdout.decode().strip()) / 'include/wasm_simd128.h'
    inputs = {name: binding(path) for name, path in [('builder', __file__), ('cSource', source),
        ('jsRuntime', runtime), ('compiler', compiler), ('linker', linker), ('simdHeader', header)]}
    output.mkdir(exist_ok=False)
    module = output / 'mask-f64.wasm'
    command = [str(compiler), '--target=wasm32-unknown-unknown', '-O3', '-msimd128',
        '-ffp-contract=off', '-fno-fast-math', '-fno-builtin', '-nostdlib', str(source),
        '-Wl,--no-entry', '-Wl,--import-memory', '-Wl,--initial-memory=131072',
        '-Wl,--max-memory=268435456', '-Wl,-z,stack-size=65536',
        *['-Wl,--export=' + name for name in EXPORTS], '-o', str(module)]
    new(output / 'attempt.json', (json.dumps({'inputs': inputs, 'command': command,
        'neuralModelInputsAllowed': 0, 'overwriteAllowed': False}, ensure_ascii=False, indent=2) + '\n').encode())
    result = subprocess.run(command, capture_output=True)
    new(output / 'compiler.stdout', result.stdout)
    new(output / 'compiler.stderr', result.stderr)
    report = {'ok': result.returncode == 0, 'inputs': inputs, 'command': command,
        'exitCode': result.returncode, 'compilerVersion': version.stdout.decode(),
        'module': binding(module) if result.returncode == 0 else None,
        'expectedImports': ['env.memory', 'env.exp'], 'exports': EXPORTS,
        'fixedWasmMemoryLimitBytes': 268435456, 'hostExpDomain': 'javascript_number_float64',
        'presenceImplemented': False, 'projectModelInputs': 0, 'formalReleaseAllowed': False, 'productHold': True}
    new(output / 'report.json', (json.dumps(report, ensure_ascii=False, indent=2) + '\n').encode())
    if result.returncode:
        raise RuntimeError(result.stderr.decode(errors='replace'))
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--compiler', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = build(args.compiler, args.output)
    print(json.dumps({'ok': result['ok'], 'module': result['module']}))
