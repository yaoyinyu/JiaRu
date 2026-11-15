"""联合几何训练的分组AdamW与可重放学习率校验。"""
import math
import torch


def rate(plan, epoch):
    if epoch <= 64:
        return plan['learningRate']
    return .0001 + .5 * (plan['learningRate'] - .0001) * (1 + math.cos(math.pi * (epoch - 64) / 64))


def build(model, plan):
    geometry, current, frozen = [], [], []
    for name, value in model.named_parameters():
        if name.startswith('previous.base.'):
            assert not value.requires_grad
            frozen.append(name)
        else:
            assert value.requires_grad
            (geometry if name.startswith('previous.') else current).append((name, value))
    assert (len(geometry), len(current), len(frozen)) == (24, 40, 77)
    assert len(model.previous.base.state_dict()) == 79
    assert 0 < plan['geometryLearningRateMultiplier'] < 1
    groups = [dict(params=[v for _, v in items], parameterNames=[n for n, _ in items],
                   branch=branch, lr=plan['learningRate'] * multiplier)
              for items, branch, multiplier in [(geometry, 'geometry', plan['geometryLearningRateMultiplier']),
                                                 (current, 'neighborhood', 1.)]]
    return torch.optim.AdamW(groups, weight_decay=plan['weightDecay'])


def start_epoch(optimizer, plan, epoch):
    assert [g['branch'] for g in optimizer.param_groups] == ['geometry', 'neighborhood']
    for group in optimizer.param_groups:
        group['lr'] = rate(plan, epoch) * (plan['geometryLearningRateMultiplier'] if group['branch'] == 'geometry' else 1.)


def verify_groups(optimizer, plan, steps):
    groups = optimizer['param_groups']
    assert len(groups) == 2
    epoch = max(1, math.ceil(steps / 80))
    for group, branch, count, offset, multiplier in zip(groups, ['geometry', 'neighborhood'], [24, 40], [0, 24],
            [plan['geometryLearningRateMultiplier'], 1.], strict=True):
        assert group['branch'] == branch and group['params'] == list(range(offset, offset + count))
        names = group['parameterNames']
        assert len(names) == len(set(names)) == count
        assert all((n.startswith('previous.') and not n.startswith('previous.base.')) if branch == 'geometry'
                   else not n.startswith('previous.') for n in names)
        assert group['lr'] == rate(plan, epoch) * multiplier
        assert group['weight_decay'] == plan['weightDecay']


def verify_event(event, plan, step):
    expected = rate(plan, max(1, math.ceil(step / 80)))
    assert event['learningRate'] == expected
    assert event['geometryLearningRate'] == expected * plan['geometryLearningRateMultiplier']
    return True
