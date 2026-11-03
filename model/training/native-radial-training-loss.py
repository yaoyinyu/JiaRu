"""原尺寸径向网络监督；真值半径仅用于训练辅助项。"""
import torch
import torch.nn.functional as F


def objective(mask, presence, radius, truth, target_radius):
    if mask.shape != truth.shape or radius.shape != target_radius.shape:
        raise ValueError('aligned full native truth and angular radius required')
    probability = mask.sigmoid()
    bce = F.binary_cross_entropy_with_logits(mask, truth)
    dice = 1 - (2 * (probability * truth).sum() + 1) / (probability.sum() + truth.sum() + 1)
    # 八像素归一化、beta=1/8，转折点对应一个原像素。
    radial = F.smooth_l1_loss(radius / 8, target_radius / 8, beta=.125)
    present = F.binary_cross_entropy_with_logits(presence, torch.ones_like(presence))
    return bce + dice + .5 * radial + .25 * present
