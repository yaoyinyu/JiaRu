"""已知正控的SIFT配准/全幅像素核验；无神经网络、无文件解码、无来源批准。"""
import cv2
import numpy as np
from PIL import Image

def footprint(matrix,size,targetSize):
    w,h=size;tw,th=targetSize
    if matrix is None or np.asarray(matrix).shape!=(3,3) or not np.isfinite(matrix).all() or np.linalg.matrix_rank(matrix)<3:
        return {'valid':False,'reason':'invalid_or_singular_matrix'}
    corners=np.float64([[0,0],[w-1,0],[w-1,h-1],[0,h-1]]).reshape(-1,1,2)
    quad=cv2.perspectiveTransform(corners,matrix).reshape(-1,2)
    if not np.isfinite(quad).all():return {'valid':False,'reason':'nonfinite_projection'}
    convex=bool(cv2.isContourConvex(quad.astype(np.float32)))
    inside=bool(np.all(quad[:,0]>=0) and np.all(quad[:,0]<=tw-1) and np.all(quad[:,1]>=0) and np.all(quad[:,1]<=th-1))
    area=abs(float(cv2.contourArea(quad.astype(np.float32))))/(tw*th)
    return {'valid':convex and inside,'reason':'geometry_ready' if convex and inside else 'nonconvex_or_outside_target','targetOriginalPixelQuad':quad.tolist(),'targetAreaFraction':area,'convex':convex,'insideTarget':inside}

def rgb_score(target,source,matrix):
    th,tw=target.shape[:2];h,w=source.shape[:2]
    warped=cv2.warpPerspective(source,matrix,(tw,th),flags=cv2.INTER_LINEAR,borderMode=cv2.BORDER_CONSTANT)
    mask=cv2.warpPerspective(np.full((h,w),255,np.uint8),matrix,(tw,th),flags=cv2.INTER_NEAREST)>0
    if not mask.any():return None
    diff=(target[mask].astype(np.float64)-warped[mask].astype(np.float64))/255
    inverse=np.linalg.inv(matrix)
    visible=cv2.warpPerspective(np.full((th,tw),255,np.uint8),inverse,(w,h),flags=cv2.INTER_NEAREST)>0
    return {'maeNormalizedRgb':float(np.mean(np.abs(diff))),'rmseNormalizedRgb':float(np.sqrt(np.mean(diff*diff))),'comparisonTargetPixels':int(mask.sum()),'sourceVisibleFraction':float(visible.mean()),'resampledDiagnosticOnly':True}

def register_positive(target,positive,spec):
    if target.mode!='RGB' or positive.mode!='RGB':raise ValueError('explicit native RGB storage required')
    cv2.setNumThreads(1);cv2.setRNGSeed(spec['seed'])
    t=np.asarray(target,dtype=np.uint8)
    detector=cv2.SIFT_create(nfeatures=spec['maxFeatures'])
    tk,td=detector.detectAndCompute(cv2.cvtColor(t,cv2.COLOR_RGB2GRAY),None)
    results=[]
    for orientation in ('original','mirror_x'):
        native=positive if orientation=='original' else positive.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
        work=native.resize(tuple(spec['workingSize']),resample=Image.Resampling.BILINEAR);s=np.asarray(work,dtype=np.uint8)
        sk,sd=detector.detectAndCompute(cv2.cvtColor(s,cv2.COLOR_RGB2GRAY),None)
        out={'orientation':orientation,'targetFeatures':len(tk),'positiveFeatures':len(sk),'workingQuerySize':list(work.size),'sourceOriginalSize':list(positive.size),'positiveControlPassed':False,'nativeVisualApproved':False,'trainingAllowed':False}
        if sd is None or td is None or len(sd)<2 or len(td)<2:
            out['reason']='insufficient_descriptors';results.append(out);continue
        matcher=cv2.BFMatcher(cv2.NORM_L2)
        forward=matcher.knnMatch(sd,td,k=2);reverse=matcher.knnMatch(td,sd,k=2)
        backward={m.queryIdx:m.trainIdx for pair in reverse if len(pair)==2 for m,n in [pair] if m.distance<spec['ratioTest']*n.distance}
        matches=[m for pair in forward if len(pair)==2 for m,n in [pair] if m.distance<spec['ratioTest']*n.distance and backward.get(m.trainIdx)==m.queryIdx]
        out['reciprocalRatioMatches']=len(matches)
        if len(matches)<spec['minimumMatches']:
            out['reason']='insufficient_reciprocal_matches';results.append(out);continue
        left=np.float32([sk[m.queryIdx].pt for m in matches]).reshape(-1,1,2)
        right=np.float32([tk[m.trainIdx].pt for m in matches]).reshape(-1,1,2)
        cv2.setRNGSeed(spec['seed']);matrix,inlier=cv2.findHomography(left,right,cv2.RANSAC,spec['ransacThresholdTargetPixels'],maxIters=2000,confidence=.995)
        geometry=footprint(matrix,work.size,target.size);out['geometry']=geometry
        if not geometry['valid'] or inlier is None:
            out['reason']='invalid_full_source_geometry';results.append(out);continue
        selected=inlier.ravel().astype(bool);count=int(selected.sum())
        predicted=cv2.perspectiveTransform(left,matrix);error=np.linalg.norm(predicted-right,axis=2).ravel()
        hull=abs(float(cv2.contourArea(cv2.convexHull(left[selected].reshape(-1,2)))))/(work.width*work.height) if count>=3 else 0
        median=float(np.median(error[selected])) if count else None
        gates={'minimumInliers':count>=spec['minimumInliers'],'minimumInlierRatio':count/len(matches)>=spec['minimumInlierRatio'],'maximumMedianTargetReprojection':median is not None and median<=spec['maximumMedianTargetReprojection'],'minimumSourceFeatureHull':hull>=spec['minimumSourceFeatureHull'],'footprintArea':spec['minimumTargetAreaFraction']<=geometry['targetAreaFraction']<=spec['maximumTargetAreaFraction']}
        out.update({'workingQueryToTargetMatrix':matrix.tolist(),'inliers':count,'inlierRatio':count/len(matches),'sourceFeatureHullFraction':hull,'medianReprojectionTargetPixels':median,'geometryGates':gates,'inlierCorrespondences':[{'workingQueryPixel':left[i,0].tolist(),'targetOriginalPixel':right[i,0].tolist()} for i in range(len(matches)) if selected[i]]})
        sx,sy=work.width/positive.width,work.height/positive.height
        resize=np.float64([[sx,0,.5*sx-.5],[0,sy,.5*sy-.5],[0,0,1]])
        mirror=np.float64([[-1,0,positive.width-1],[0,1,0],[0,0,1]]) if orientation=='mirror_x' else np.eye(3)
        out['sourceOriginalPixelCenterToTargetMatrix']=(matrix@resize@mirror).tolist()
        if not all(gates.values()):
            out['reason']='full_source_geometry_gate_failed';results.append(out);continue
        photometric=rgb_score(t,s,matrix);competitors=[]
        dx,dy=target.width/3,target.height/3
        for yi in (-1,0,1):
            for xi in (-1,0,1):
                if xi==yi==0:continue
                other=np.float64([[1,0,xi*dx],[0,1,yi*dy],[0,0,1]])@matrix
                if footprint(other,work.size,target.size)['valid']:
                    value=rgb_score(t,s,other)
                    if value is not None:competitors.append({'translationTargetPixels':[xi*dx,yi*dy],'scores':value})
        second=min([x['scores']['maeNormalizedRgb'] for x in competitors],default=None)
        pixelGates={'minimumSourceVisibleFraction':photometric is not None and photometric['sourceVisibleFraction']>=spec['minimumSourceVisibleFraction'],'maximumMaeUnchanged':photometric is not None and photometric['maeNormalizedRgb']<=spec['maximumMaeNormalizedRgb'],'minimumWrongLocationControls':len(competitors)>=spec['minimumWrongLocationControls'],'bestToWrongLocationUnchanged':second is not None and photometric is not None and photometric['maeNormalizedRgb']<=spec['maximumBestToWrongRatio']*second}
        out.update({'photometric':photometric,'wrongLocationControls':competitors,'minimumWrongLocationMae':second,'pixelGates':pixelGates,'positiveControlPassed':all(pixelGates.values()),'reason':'method_positive_control_ready_not_source_approval' if all(pixelGates.values()) else 'positive_photometric_control_failed'})
        results.append(out)
    passed=[x for x in results if x['positiveControlPassed']]
    best=min(passed,key=lambda x:x['photometric']['maeNormalizedRgb']) if passed else None
    return {'variants':results,'positiveControlPassed':bool(passed),'selectedPassingOrientation':best['orientation'] if best else None,'meaning':'known_positive_local_registration_diagnostic_not_native_visual_or_origin_approval','candidateSourceCount':0,'candidateComparisonComputed':False,'nativeVisualApproved':False,'sourceParentIndependenceQualified':False,'trainingAllowed':False}
