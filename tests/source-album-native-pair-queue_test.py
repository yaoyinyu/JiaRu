import copy,importlib.util,json,tempfile,unittest
from pathlib import Path
R=Path(__file__).resolve().parents[1];sp=importlib.util.spec_from_file_location('album_queue',R/'model/training/build-source-album-native-pair-queue.py');m=importlib.util.module_from_spec(sp);sp.loader.exec_module(m)
class QueueTests(unittest.TestCase):
 def setUp(self):
  (R/'model/reviews/test-temp').mkdir(parents=True,exist_ok=True);self.tmp=tempfile.TemporaryDirectory(dir=R/'model/reviews/test-temp');self.root=Path(self.tmp.name)
 def tearDown(self):self.tmp.cleanup()
 def save(self,name,data):
  p=self.root/name;p.write_text(json.dumps(data),encoding='utf-8');return m.bind(p)
 def fixture(self,roles=None):
  def target(d):return {'imageSha256':d,'sourceImage':{'path':d,'sha256':d},'sourceGroup':'g'}
  def hit(d,role):return {'reference':{'image':{'path':d,'sha256':d},'roles':[role]},'result':{'recalled':True}}
  queries=[]
  for ordinal,(digest,refs) in enumerate(roles or [('a',[hit('b','consumedPositiveTest')]),('b',[hit('a','consumedPositiveTest')])],1):
   q={'ordinal':ordinal,'target':target(digest),'lowFeatureQuery':False,'recalledPairs':refs};qr=self.save(f'q{ordinal}.json',q);queries.append({'ordinal':ordinal,'report':qr,'recalledPairs':len(refs)})
  report={'ok':True,'executionStatus':'complete','results':queries,'counts':{'newTargets':len(queries),'recalledPairs':sum(q['recalledPairs'] for q in queries)}}
  acquisition={'groups':[{'sourceGroup':'g','currentCandidates':[{'identity':{'split':'train','fileName':'current','imageSha256':'current'}}]}]}
  return report,acquisition
 def run_build(self,report,acquisition):
  rp=self.save('report.json',report);ap=self.save('acq.json',acquisition);out=self.root/'queue.json';m.build(Path(rp['path']),Path(ap['path']),out);return json.loads(out.read_bytes())
 def test_bidirectional_pair_merged_without_losing_observations_or_roles(self):
  r,a=self.fixture();before=copy.deepcopy(r);q=self.run_build(r,a);self.assertEqual(q['counts']['uniqueUnorderedPairs'],1);self.assertEqual(len(q['pairs'][0]['observations']),2);self.assertEqual(q['counts']['recalledObservations'],2);self.assertEqual(r,before);self.assertFalse(q['trainingAllowed']);self.assertFalse(q['sourceParentIndependenceQualified'])
 def test_no_hit_kept_not_approved(self):
  r,a=self.fixture([('a',[])]);q=self.run_build(r,a);self.assertEqual(len(q['noHitTargets']),1);self.assertFalse(q['noHitTargets'][0]['independenceApproved'])
 def test_partial_or_out_of_order_target_denominator_rejected(self):
  for mutation in ['count','order']:
   r,a=self.fixture()
   if mutation=='count':r['counts']['newTargets']=3
   else:r['results'].reverse()
   with self.assertRaises(ValueError):self.run_build(r,a)
 def test_nonterminal_failed_recall_refused(self):
  r,a=self.fixture();r['executionStatus']='running'
  with self.assertRaises(ValueError):self.run_build(r,a)
 def test_source_owner_identity_not_changed_to_related_asset_identity(self):
  r,a=self.fixture();q=self.run_build(r,a);t=q['pairs'][0]['observations'][0]['target'];self.assertEqual(t['ownerCurrentIdentities'],[a['groups'][0]['currentCandidates'][0]['identity']]);self.assertNotEqual(t['ownerCurrentIdentities'][0]['imageSha256'],t['imageSha256'])
if __name__=='__main__':unittest.main()
