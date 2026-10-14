"""正常训练事件审核拒绝缩水分母、重复候选、未确认优化及错误增强。"""
import copy
import importlib.util
import unittest
from pathlib import Path
R=Path(__file__).resolve().parents[1]
sp=importlib.util.spec_from_file_location('normal_ledger_tests',R/'model/training/verify-reviewed-stage-b-normal-training.py')
m=importlib.util.module_from_spec(sp);sp.loader.exec_module(m)

class Tests(unittest.TestCase):
    def fixture(self):
        ids=[{'identity':{'split':'train','fileName':f'{n}.png','imageSha256':str(n)},'predictionIndex':1} for n in (1,2)]
        plan={'candidateIdentities':ids,'budget':{'epochs':2,'optimizerSteps':2,'augmentedTrainingInputs':4}}
        events=[];steps=epochs=inputs=0;flight=False
        def event(phase,**extra):
            events.append({'phase':phase,'confirmedOptimizerSteps':steps,'completedEpochs':epochs,
                           'modelInputsStarted':inputs,'optimizerStepInFlight':flight,**extra})
        event('claimed')
        for epoch in (1,2):
            for ci in ids:
                inputs+=1;event('training_input_started',epoch=epoch,candidateIdentity=ci,
                                augmentation={'rotation':1,'flip':False,'brightness':1.,'contrast':1.})
            flight=True;event('optimizer_in_flight',attemptedStep=steps+1)
            flight=False;steps+=1;event('optimizer_confirmed')
            epochs=epoch;event('epoch_completed',meanLoss=.5)
        for ci in ids:inputs+=1;event('final_train_input_started',candidateIdentity=ci)
        event('closed')
        return events,plan

    def test_complete_budget(self):
        ledger,plan=self.fixture()
        self.assertEqual(m.validate_training_ledger(ledger,plan),{'completedEpochs':2,'confirmedOptimizerSteps':2,
            'augmentedTrainingInputs':4,'finalTrainInferenceInputs':2,'modelInputsStarted':6})

    def test_duplicate_candidate_does_not_fill_full_epoch(self):
        ledger,plan=copy.deepcopy(self.fixture());ledger[2]['candidateIdentity']=ledger[1]['candidateIdentity']
        with self.assertRaisesRegex(ValueError,'whole cohort'):m.validate_training_ledger(ledger,plan)

    def test_confirmation_without_started_optimizer_rejected(self):
        ledger,plan=self.fixture();ledger=[e for e in ledger if e['phase']!='optimizer_in_flight']
        with self.assertRaisesRegex(ValueError,'unstarted optimizer'):m.validate_training_ledger(ledger,plan)

    def test_stale_progress_count_rejected(self):
        ledger,plan=self.fixture();ledger[2]['modelInputsStarted']=1
        with self.assertRaisesRegex(ValueError,'persisted event state'):m.validate_training_ledger(ledger,plan)

    def test_fractional_geometry_rejected(self):
        ledger,plan=self.fixture();ledger[1]['augmentation']['rotation']=.5
        with self.assertRaisesRegex(ValueError,'augmentation contract'):m.validate_training_ledger(ledger,plan)

    def test_val_candidate_cannot_be_counted_as_train(self):
        ledger,plan=copy.deepcopy(self.fixture());ledger[1]['candidateIdentity']['identity']['split']='val'
        # fixture共享对象也可能影响plan，显式复原正式train清单。
        plan=self.fixture()[1]
        with self.assertRaisesRegex(ValueError,'whole cohort'):m.validate_training_ledger(ledger,plan)

    def test_final_inference_order_is_preserved(self):
        ledger,plan=copy.deepcopy(self.fixture());final=[e for e in ledger if e['phase']=='final_train_input_started']
        final[0]['candidateIdentity'],final[1]['candidateIdentity']=final[1]['candidateIdentity'],final[0]['candidateIdentity']
        with self.assertRaisesRegex(ValueError,'final inference order'):m.validate_training_ledger(ledger,plan)

if __name__=='__main__':unittest.main()
