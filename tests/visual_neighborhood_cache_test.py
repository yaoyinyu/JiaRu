import importlib.util,sys,unittest
from pathlib import Path
import torch
from torch import nn
T=Path(__file__).parents[1]/'model/training'
def load(name,path):
 s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s);sys.modules[name]=m;s.loader.exec_module(m);return m
net=load('neighbor_cache_net',T/'visual-neighborhood-radial-refiner.py');cache=load('neighbor_cache_helper',T/'cached-visual-neighborhood-training.py')
class Prior(nn.Module):
 def forward_with_radius(self,strip,coarse,bins,distance):
  radius=coarse+.25
  return (radius.gather(1,bins.reshape(1,-1)).reshape_as(distance)-distance)[:,None],torch.ones(1),radius
class Tests(unittest.TestCase):
 def test_nonzero_heads_and_all_gradients_exact(self):
  torch.set_num_threads(2);torch.manual_seed(3);model=net.VisualNeighborhoodRadialRefiner(Prior()).train();nn.init.normal_(model.head.weight,std=.03)
  args=(torch.rand(1,5,32,129),torch.full((1,32),40.),torch.arange(32).reshape(1,4,8),torch.ones(1,4,8)*39)
  direct=model.forward_with_radius(*args);direct[0].square().mean().backward();before=[p.grad.clone() for p in model.parameters() if p.requires_grad];model.zero_grad()
  _,presence,initial=model.previous.forward_with_radius(*args)
  saved=dict(features=cache.features(model,args[0],initial,args[1]),initial=initial,presence=presence)
  actual=cache.forward(model,saved,*args[1:]);actual[0].square().mean().backward()
  for a,b in zip(direct,actual):self.assertTrue(torch.equal(a,b))
  after=[p.grad for p in model.parameters() if p.requires_grad];self.assertEqual(len(after),20)
  for a,b in zip(before,after):self.assertTrue(torch.equal(a,b))
if __name__=='__main__':unittest.main()
