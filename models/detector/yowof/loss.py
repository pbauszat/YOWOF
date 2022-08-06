import torch
import torch.nn as nn
from .matcher import YoloMatcher
from utils.box_ops import *
from utils.misc import sigmoid_focal_loss
from utils.vis_tools import vis_targets
from utils.distributed_utils import get_world_size, is_dist_avail_and_initialized



class Criterion(object):
    def __init__(self, 
                 cfg, 
                 device,
                 anchor_size,
                 num_anchors,
                 num_classes,
                 loss_obj_weight=5.0,
                 loss_noobj_weight=1.0,
                 loss_cls_weight=1.0, 
                 loss_reg_weight=1.0):
        self.cfg = cfg
        self.device = device
        self.anchor_size = anchor_size
        self.num_anchors = num_anchors
        self.num_classes = num_classes
        self.loss_obj_weight = loss_obj_weight
        self.loss_noobj_weight = loss_noobj_weight
        self.loss_cls_weight = loss_cls_weight
        self.loss_reg_weight = loss_reg_weight

        # Matcher
        self.matcher = YoloMatcher(
            num_classes=num_classes,
            num_anchors=num_anchors,
            anchor_size=anchor_size,
            iou_thresh=cfg['ignore_thresh']
            )
        
        # Loss
        self.conf_loss = nn.MSELoss(reduction='none')
        self.cls_loss = nn.CrossEntropyLoss(reduction='none')


    def __call__(self, 
                 outputs, 
                 targets, 
                 video_clips=None, 
                 vis_data=False):
        """
            outputs['conf_pred']: [B, M, 1]
            outputs['cls_pred']: [B, M, C]
            outputs['box_pred]: [B, M, 4]
            outputs['stride']: Int -> stride of the model output
            anchor_size: (Tensor) [K, 2]
            targets: List[List] -> [List[B, N, 6], 
                                    ...,
                                    List[B, N, 6]],
            video_clips: Lits[Tensor] -> [Tensor[B, C, H, W], 
                                          ..., 
                                          Tensor[B, C, H, W]]
        """
        if vis_data:
            # To DO: 
            # vis video clip and targets
            vis_targets(video_clips, targets)

        # target of key-frame
        kf_target = targets[-1]
        device = outputs['conf_pred'].device
        batch_size = outputs['conf_pred'].shape[0]
            
        # reformat target
        kf_target = [{
            'boxes': t[:, :4].float(),  # [Ni, 4]
            'labels': t[:, 4].long(),   # [Ni,]
        } for t in kf_target]


        # Matcher for this frame
        (
            gt_conf, 
            gt_cls, 
            gt_bboxes
            ) = self.matcher(img_size=outputs['img_size'], 
                             stride=outputs['stride'], 
                             targets=kf_target)

        pred_conf = outputs['conf_pred'].view(-1)                  # [BM,]
        pred_cls = outputs['cls_pred'].view(-1, self.num_classes)  # [BM, C]
        pred_box = outputs['box_pred'].view(-1, 4)                 # [BM, 4]
        
        gt_conf = gt_conf.flatten().to(device).float()        # [BM,]
        gt_cls = gt_cls.flatten().to(device).long()           # [BM,]
        gt_bboxes = gt_bboxes.view(-1, 4).to(device).float()  # [BM, 4]

        # fore mask
        foreground_mask = (gt_conf > 0)

        # box loss
        matched_pred_box = pred_box[foreground_mask]
        matched_tgt_box = gt_bboxes[foreground_mask]
        ious = get_ious(matched_pred_box,
                        matched_tgt_box,
                        box_mode="xyxy",
                        iou_type='giou')
        loss_box = (1.0 - ious).sum() / batch_size

        # cls loss
        matched_pred_cls = pred_cls[foreground_mask]
        matched_tgt_cls = gt_cls[foreground_mask]
        loss_cls = self.cls_loss(matched_pred_cls, matched_tgt_cls)
        loss_cls = loss_cls.sum() / batch_size

        # conf loss
        gt_ious = torch.zeros_like(gt_conf)
        gt_ious[foreground_mask] = ious.clone().detach().clamp(0.)
        gt_conf = gt_conf * gt_ious
        loss = self.conf_loss(pred_conf.sigmoid(), gt_conf)
        ## obj & noobj
        obj_mask = (gt_conf > 0.)
        noobj_mask = (gt_conf == 0.)
        ## weighted loss of conf
        loss_conf = loss * obj_mask * self.loss_obj_weight + \
                    loss * noobj_mask * self.loss_noobj_weight
        loss_conf = loss_conf.sum() / batch_size

        # total loss
        losses = self.loss_obj_weight * loss_conf + \
                 self.loss_cls_weight * loss_cls + \
                 self.loss_reg_weight * loss_box

        loss_dict = dict(
                loss_conf = loss_conf,
                loss_cls = loss_cls,
                loss_box = loss_box,
                losses = losses
        )

        return loss_dict
    

if __name__ == "__main__":
    pass
