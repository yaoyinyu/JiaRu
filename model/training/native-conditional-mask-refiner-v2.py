"""仅弱化初始粗mask logit先验，保留v1网络、数据语义与参数初始化。"""
import importlib.util
from pathlib import Path
sp=importlib.util.spec_from_file_location('weak_prior_native_original',Path(__file__).with_name('native-conditional-mask-refiner.py'))
original=importlib.util.module_from_spec(sp);sp.loader.exec_module(original)
class NativeConditionalMaskRefiner(original.NativeConditionalMaskRefiner):
 def forward(self,values):
  logits,presence=super().forward(values)
  # 8*(seed-.5) → 2*(seed-.5)；同零残差的初始二值mask不变。
  return logits-(values[:,3:4]*6-3),presence
candidate_loss=original.candidate_loss
pack=original.pack
decode=original.decode
