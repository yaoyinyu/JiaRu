"""开发训练来源筛选、完整polygon及不可覆盖事件的回归检查。"""
import concurrent.futures
import hashlib
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
R = Path(__file__).resolve().parents[1]


def load(name, file):
    spec = importlib.util.spec_from_file_location(name, R / 'model/training' / file)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


d = load('reviewed_data_tests', 'reviewed-role-development-data.py')
t = load('reviewed_train_tests', 'train-reviewed-stage-a-development.py')
t2 = load('reviewed_train_v2_tests', 'train-reviewed-stage-a-development-v2.py')


class Checks(unittest.TestCase):
    def test_binding_rejects_same_bytes_wrong_path_and_sha(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'a.json'; path.write_bytes(b'{}')
            ref = d.bind(path)
            bad = {**ref, 'path': str(path.parent / '.' / path.name).replace('a.json', 'missing.json')}
            with self.assertRaises(FileNotFoundError): d.checked(bad)
            with self.assertRaises(ValueError): d.checked({**ref, 'sha256': '0' * 64})
            with self.assertRaises(ValueError): d.checked({**ref, 'path': str(path.parent / '..' / path.parent.name / path.name)})

    def test_related_album_pending_pair_excludes_entire_owner_group(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'queue.json'
            path.write_text(json.dumps({'pairs': [{'pairIdentity': ['a', 'b'], 'observations': [{'target': {'sourceGroups': ['owner-group']}}]}]}), encoding='utf-8')
            disposition = {'inputs': {'queue': d.bind(path)}, 'pendingPairIdentities': [['a', 'b']], 'currentUncertainPairDecisions': []}
            self.assertEqual(d.unresolved_groups(disposition), {'owner-group'})
            disposition['pendingPairIdentities'] = []
            disposition['currentUncertainPairDecisions'] = [{'pairIdentity': ['a', 'b'], 'decision': 'uncertain'}]
            self.assertEqual(d.unresolved_groups(disposition), {'owner-group'})

    def test_overlap_and_image_identity_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'truth.json'
            ident = {'split': 'train', 'fileName': 'source.png', 'imageSha256': 'a' * 64}
            value = {'image': {'fileName': 'source.png'}, 'annotations': [{'polygon': [[0, 0], [6, 0], [6, 6], [0, 6]]}, {'polygon': [[3, 3], [9, 3], [9, 9], [3, 9]]}]}
            path.write_text(json.dumps(value), encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'overlap'): d.polygons(d.bind(path), 10, 10, ident)
            value['annotations'] = value['annotations'][:1]; value['image']['fileName'] = 'wrong.png'
            path.write_text(json.dumps(value), encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'identity'): d.polygons(d.bind(path), 10, 10, ident)

    def test_concurrent_writers_only_one_immutable_event_survives(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'event.json'
            def write(number):
                try: d.new(path, {'number': number}); return True
                except FileExistsError: return False
            with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
                self.assertEqual(sum(pool.map(write, range(8))), 1)
            original = path.read_bytes()
            with path.open('rb') as reader:
                with self.assertRaises(FileExistsError): d.new(path, {'number': 9})
                self.assertEqual(reader.read(), original)
            self.assertEqual(path.read_bytes(), original)

    def test_journal_only_successful_step_is_confirmed(self):
        with tempfile.TemporaryDirectory() as folder:
            journal = t.Journal(Path(folder))
            journal.before(None, (), {}); journal.after(None, (), {})
            journal.before(None, (), {})
            rows = [json.loads(p.read_bytes()) for p in sorted((Path(folder) / 'events').glob('*.json'))]
            self.assertEqual([r['confirmedOptimizerSteps'] for r in rows], [0, 1, 1])
            self.assertTrue(rows[-1]['optimizerStepInFlight'])
            self.assertEqual(rows[-1]['attemptedStep'], 2)

    def test_final_validation_callback_does_not_create_training_epoch(self):
        self.assertEqual(t2.epoch_callback_phase(30, 29, 150, 145, 30), 'epoch_completed')
        self.assertEqual(t2.epoch_callback_phase(31, 30, 150, 150, 30), 'final_validation_complete')
        with self.assertRaises(ValueError): t2.epoch_callback_phase(31, 30, 151, 150, 30)
        with self.assertRaises(ValueError): t2.epoch_callback_phase(30, 30, 150, 150, 30)


if __name__ == '__main__': unittest.main()
