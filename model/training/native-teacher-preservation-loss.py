"""精确真值之外的原图保持约束；教师掩码只用于已通过训练真值的正例。"""
import torch
import torch.nn.functional as F


def preservation(logits, presence, teacher_logits, teacher_presence, band,
                 positive, mask_approved, counts):
    if teacher_logits.requires_grad or teacher_presence.requires_grad:
        raise ValueError('teacher must be detached')
    if logits.dtype != torch.float32 or presence.dtype != torch.float32:
        raise ValueError('float32 student heads required')
    if logits.shape != teacher_logits.shape or presence.shape != teacher_presence.shape:
        raise ValueError('same candidate/coordinate teacher heads required')
    for tensor in [logits, presence, teacher_logits, teacher_presence]:
        if not torch.isfinite(tensor).all():raise ValueError('nonfinite preservation tensor')
    class_count = counts['positiveInputs'] if positive else counts['rejectInputs']
    result = .25 * counts['candidateInputs'] / (2 * class_count) * F.smooth_l1_loss(
        presence, teacher_presence, beta=1.)
    if mask_approved:
        if not positive or band is None or band.shape != logits.shape or band.dtype != torch.bool:
            raise ValueError('approved positive complete target band required')
        weights = 1. + 4. * band.float()
        result = result + 2. * (weights * F.smooth_l1_loss(
            logits, teacher_logits, beta=1., reduction='none')).sum() / weights.sum()
    return result
