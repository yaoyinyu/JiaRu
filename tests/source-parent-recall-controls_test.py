"""域外正控必须参与特征读取，不能改变比较分母。"""
import importlib.util
import unittest
from pathlib import Path

spec=importlib.util.spec_from_file_location('source_parent_recall',Path(__file__).resolve().parents[1]/'model/training/recall-source-parent-near-duplicates.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)

class FeatureInventoryTests(unittest.TestCase):
    def test_external_control_and_parent_are_included_without_reference_promotion(self):
        ref=lambda key:dict(path=key,sha256=key)
        inventory=dict(corpus=[dict(image=ref('reference'))])
        targets=dict(targets=[dict(imageSha256='target',sourceImage=ref('target'))])
        plan=dict(positiveControls=[dict(sourceImage=ref('outside'),referenceImage=ref('parent')),dict(sourceImage=ref('target'))])
        result=module.feature_image_inventory(plan,inventory,targets)
        self.assertEqual(set(result),{'reference','target','outside','parent'})
        self.assertEqual(len(inventory['corpus']),1)
        self.assertEqual(len(targets['targets']),1)
        self.assertEqual(result['outside'],ref('outside'))

if __name__=='__main__':unittest.main()
