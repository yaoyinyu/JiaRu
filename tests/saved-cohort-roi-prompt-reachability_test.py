import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
import numpy as np
R=Path(__file__).resolve().parents[1]
def load(name,p):
    s=importlib.util.spec_from_file_location(name,p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
m=load('cohort_roi_fixture',R/'model/training/audit-saved-cohort-roi-prompt-reachability.py')
roi=load('roi_helper_fixture',R/'model/training/analyze-saved-nail-roi-coverage.py')
h=load('prediction_helper_fixture',R/'model/training/run-train-role-marker-sensitivity-probe.py')
t=load('truth_helper_fixture',R/'model/training/run-variable-train-role-marker-probe.py')
prompt=load('prompt_helper_fixture',R/'model/training/audit-saved-conditional-input-preflight.py')
class CohortRoiTests(unittest.TestCase):
    def test_one_large_roi_seed_cannot_count_as_multiple_truths(self):
        assignment=m.joint_oracle(np.ones((3,1),bool),np.ones((3,1)))
        self.assertEqual(len(assignment),1)
    def test_qualified_joint_oracle_is_separate_from_geometry_only_oracle(self):
        valid=np.array([[True,False],[False,True]])
        iou=np.array([[.1,.9],[.9,.1]])
        witness=m.joint_oracle(valid,iou)
        self.assertEqual([(a['truthIndex'],a['predictionIndex']) for a in witness],[(1,1),(2,2)])
    def test_candidate_cap_preserves_original_truth_denominator_and_assignment(self):
        original={'assignment':[{'truthIndex':1,'predictionIndex':1,'iou':.8},{'truthIndex':2,'predictionIndex':2,'iou':.9}]}
        stats=m.variant_stats([0],np.ones((2,2)),np.eye(2),np.eye(2,dtype=bool),original,roi)
        self.assertEqual(len(stats['primaryAssignmentPreserved']),2)
        self.assertEqual(stats['unresolvedOriginalTruthIndices'],[2])
    def test_prompt_tie_and_non_target_seed_never_qualify(self):
        self.assertFalse(prompt.seed_identity([4,4],0)['strictlyTargetDominant'])
        self.assertFalse(prompt.seed_identity([2,9],0)['strictlyTargetDominant'])
    def test_registered_marker_halo_intersection_is_geometry_not_mask_quality(self):
        self.assertEqual(prompt.overlap_area((0,0,10,10),(9,9,15,15)),1)
        self.assertEqual(prompt.overlap_area((0,0,10,10),(10,10,15,15)),0)
    def test_full_native_truth_coverage_is_exact_not_bbox_overlap(self):
        truth=np.zeros((1,10,10),bool);truth[0,2:8,2:8]=True
        _,coverage=roi.coverage_matrix(truth,np.array([[2,2,6,6]]),'native_xyxy_floor_ceil')
        self.assertLess(coverage[0,0],1)
    def test_original_reconstruction_rejects_score_and_assignment_drift(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);image=root/'original.dat';image.write_bytes(b'fixture only')
            ann=root/'ann.json';ann.write_text(json.dumps({'annotations':[{'polygon':[{'x':1,'y':1},{'x':4,'y':1},{'x':4,'y':4},{'x':1,'y':4}]}]}))
            source={'identity':{'fileName':'fixture'},'sourceImage':m.bind(image),'annotation':m.bind(ann),'imageSize':[8,8],
                'completeVisibleNails':1,'truthFormat':'original_pixel_polygon_annotation_json'}
            truth=t.truth_masks(source)
            ref=h.save_prediction(root/'p.npz',np.array([[1,1,4,4]],np.float32),np.array([.8],np.float32),np.zeros(1,np.float32),truth)
            boxes,conf,classes,masks=h.load_prediction(ref,[8,8])
            old={'prediction':ref,'boxesXyxy':boxes.tolist(),'confidence':conf.tolist(),'classes':classes.tolist(),
                'instanceCount':1,**h.match_masks(masks,truth,.75)}
            m.rebuild_original(source,old,h,t)
            for kind in ['confidence','assignment']:
                broken=copy.deepcopy(old)
                if kind=='confidence':broken['confidence']=[.7]
                else:broken['assignment'][0]['iou']=.9
                with self.assertRaisesRegex(ValueError,'reconstruction_mismatch'):m.rebuild_original(source,broken,h,t)
if __name__=='__main__':unittest.main()
