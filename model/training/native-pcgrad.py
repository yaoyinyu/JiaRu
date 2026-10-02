"""逐ROI目标的PCGrad式冲突投影；只是开发聚合变量，不保证质量。"""
import torch


def project_mean(gradients, *, generator):
    """遇到负内积，剔除当前梯度沿另一原始梯度的冲突分量。

    参考Yu等Gradient Surgery论文；这里是逐ROI实验适配，非论文多任务复现。
    使用独立CPU顺序generator；零向量跳过投影，但保留窗口完整平均分母。
    多次投影可能再次产生与更早方向的负内积，不能声称所有冲突被消除。
    """
    if gradients.ndim!=2 or gradients.shape[0]<1 or gradients.dtype!=torch.float32 or not torch.isfinite(gradients).all():
        raise ValueError('finite FP32 window gradients required')
    original=gradients.detach()
    projected=original.clone()
    changes=0
    for index in range(len(original)):
        order=torch.randperm(len(original),generator=generator).tolist()
        for other in order:
            if other==index:
                continue
            direction=original[other]
            square=torch.dot(direction,direction)
            if square.item()==0:
                continue
            dot=torch.dot(projected[index],direction)
            if dot.item()<0:
                projected[index]-=(dot/square)*direction
                changes+=1
    mean=projected.mean(dim=0)
    if not torch.isfinite(projected).all() or not torch.isfinite(mean).all():
        raise ValueError('nonfinite projected gradients')
    return mean, {'candidateCount':len(original),'projectionCount':changes,'emptyGradientCount':int((original.abs().sum(dim=1)==0).sum().item())}
