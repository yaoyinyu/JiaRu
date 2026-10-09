"""固定暗字候选支持域与局部NS修复/配对残差，不批准视觉语义或训练。"""
import numpy as np
import cv2
POLICY={'version':1,'glyphCandidate':'RGB_to_gray_BLACKHAT_rect15_threshold16_and_gray_le215_then_ellipse3_dilation','supportMeaning':'candidate_dark_glyph_and_possible_texture_requires_native_visual_review','inpaint':'OpenCV_INPAINT_NS_radius3_full_native_RGB_uint8_only_support_pixels','blankRemoval':'same_translated_support_shape_and_same_inpaint_rule_at_C','move':'same_M_removed_base_add_original_minus_removed_M_residual_at_D','blankMove':'same_M_removed_base_add_original_minus_blank_removed_C_residual_at_same_D','placement':'integer_translation_same_MCD_size_no_resampling','registrationBoxesMayOverlapOnlyIfActualSupportsDisjoint':True,'backgroundMatchRequiresNativeReview':True,'newModelCallsAllowed':0,'trainingAllowed':False}
def _box(box,w,h):
 if len(box)!=4 or not all(isinstance(x,int) for x in box):raise ValueError('integer registration box required')
 x0,y0,x1,y1=box
 if not (0<=x0<x1<=w and 0<=y0<y1<=h):raise ValueError('registration outside image')
 return tuple(box)
def support_mask(rgb,box):
 if rgb.dtype!=np.uint8 or rgb.ndim!=3 or rgb.shape[2]!=3:raise ValueError('native RGB uint8 required')
 h,w=rgb.shape[:2];x0,y0,x1,y1=_box(box,w,h);gray=cv2.cvtColor(rgb,cv2.COLOR_RGB2GRAY);residual=cv2.morphologyEx(gray,cv2.MORPH_BLACKHAT,np.ones((15,15),np.uint8));base=((residual>=16)&(gray<=215)).astype('uint8');mask=np.zeros((h,w),np.uint8);mask[y0:y1,x0:x1]=base[y0:y1,x0:x1];mask=cv2.dilate(mask,cv2.getStructuringElement(cv2.MORPH_ELLIPSE,(3,3)));allowed=np.zeros_like(mask);allowed[y0:y1,x0:x1]=1;mask&=allowed
 if not mask.any():raise ValueError('empty candidate glyph support')
 return mask
def translate_support(mask,M,B):
 h,w=mask.shape;M=_box(M,w,h);B=_box(B,w,h)
 if (M[2]-M[0],M[3]-M[1])!=(B[2]-B[0],B[3]-B[1]):raise ValueError('registration size drift')
 allowed=np.zeros_like(mask);allowed[M[1]:M[3],M[0]:M[2]]=1
 if (mask&~allowed).any():raise ValueError('support outside registered marker')
 result=np.zeros_like(mask);result[B[1]:B[3],B[0]:B[2]]=mask[M[1]:M[3],M[0]:M[2]];return result
def build_variants(rgb,support,M,C,D):
 if rgb.dtype!=np.uint8 or rgb.ndim!=3 or rgb.shape[2]!=3 or support.shape!=rgb.shape[:2] or not np.isin(support,[0,1]).all() or not support.any():raise ValueError('native RGB/binary support contract')
 cm=translate_support(support,M,C);dm=translate_support(support,M,D)
 if any((a&b).any() for a,b in [(support,cm),(support,dm),(cm,dm)]):raise ValueError('actual intervention supports overlap')
 rem=cv2.inpaint(rgb,support*255,3,cv2.INPAINT_NS);blank=cv2.inpaint(rgb,cm*255,3,cv2.INPAINT_NS)
 if np.any(rem[support==0]!=rgb[support==0]) or np.any(blank[cm==0]!=rgb[cm==0]):raise ValueError('inpaint changed pixels outside support')
 mr=rgb.astype('int16')-rem.astype('int16');cr=rgb.astype('int16')-blank.astype('int16');move=rem.copy();bm=rem.copy();x0,y0,x1,y1=D
 for out,res,box in [(move,mr,M),(bm,cr,C)]:
  patch=res[box[1]:box[3],box[0]:box[2]];out[y0:y1,x0:x1]=np.clip(rem[y0:y1,x0:x1].astype('int16')+patch,0,255).astype('uint8')
 if np.any(move[dm==0]!=bm[dm==0]):raise ValueError('paired difference outside destination')
 return {'original':rgb.copy(),'remove':rem,'blank_remove_control':blank,'move_marker':move,'blank_move_control':bm},{'M':support.copy(),'C':cm,'D':dm}
