"""独占事件、原字节摘要索引和单次终态；读者无需反复解析文件路径。"""
import hashlib
import json
import os
import time


def encode(value):
    return (json.dumps(value,ensure_ascii=False,indent=2)+'\n').encode('utf8')


def save(path, value):
    raw=encode(value)
    with path.open('xb') as f:f.write(raw);f.flush();os.fsync(f.fileno())
    return {'path':str(path),'sha256':hashlib.sha256(raw).hexdigest()}


class Journal:
    def __init__(self,root):
        self.root=root;self.sequence=0;self.steps=0;self.epochs=0;self.inputs=0
        self.in_flight=False;self.started=time.monotonic();self.refs=[]
        (root/'events').mkdir(exist_ok=False)

    def event(self,phase,**extra):
        self.sequence+=1
        value={'sequence':self.sequence,'phase':phase,'confirmedOptimizerSteps':self.steps,
               'completedEpochs':self.epochs,'modelInputsStarted':self.inputs,
               'optimizerStepInFlight':self.in_flight,'elapsedSeconds':time.monotonic()-self.started,**extra}
        self.refs.append(save(self.root/'events'/f'{self.sequence:06d}.json',value))
        return value

    def terminal(self,phase,**extra):
        value=self.event(phase,**extra);save(self.root/'terminal.json',value)
        save(self.root/'event-index.json',{'events':self.refs,'terminal':self.refs[-1],
                                         'eventCount':self.sequence})
