"""固定学习率实验的单变量及步数合同；无图片或模型执行。"""
def validate_training_change(current, previous):
    expected=dict(previous)
    if previous['learningRate']!=0.0003 or previous['minimumLearningRate']!=0.0000015:
        raise ValueError('unexpected frozen reference schedule')
    expected['minimumLearningRate']=previous['learningRate']
    if current!=expected:
        raise ValueError('only cosine eta_min may change')
    if current['epochs']!=64 or current['expectedOptimizerSteps']!=384 or current['accumulation']!=8:
        raise ValueError('fixed optimization budget')
    return {'initial':current['learningRate'],'minimum':current['minimumLearningRate'],'optimizerSteps':384}


def verify_recorded_rates(events, expected):
    attempts=[row for row in events if row['optimizerStepInFlight']]
    if [row['attemptedNextStep'] for row in attempts]!=list(range(1,expected['optimizerSteps']+1)):
        raise ValueError('recorded step budget mismatch')
    rates=[row['learningRate'] for row in attempts]
    if any(value!=expected['initial'] for value in rates):
        raise ValueError('recorded learning rate changed')
    return {'recordedOptimizerStepCount':len(rates),'uniqueRecordedLearningRates':sorted(set(rates))}
