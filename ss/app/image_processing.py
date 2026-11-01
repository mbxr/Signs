"""OpenCV alignment and configurable region extraction."""
from pathlib import Path
import numpy as np
import cv2
from PIL import Image, ImageOps
from .template import FIELD_LABELS

class AlignmentError(ValueError):
    """Extraction aborted instead of assigning handwriting to incorrect fields."""


def load_rgb(path: str | Path):
    with Image.open(path) as im:
        im=ImageOps.exif_transpose(im).convert('RGB')
        im.thumbnail((2000,2600),Image.Resampling.LANCZOS)
        return np.asarray(im)

def register_image(source: np.ndarray, reference: np.ndarray | None):
    """Align to the photographed template via ORB feature matching and RANSAC.
    Fail safely: return original with a warning rather than an incorrect warp.
    """
    if reference is None:
        return source, 'No reference photo configured: field positions are approximate; review all results'
    ref_h,ref_w=reference.shape[:2]
    gray_source=cv2.cvtColor(source,cv2.COLOR_RGB2GRAY)
    gray_ref=cv2.cvtColor(reference,cv2.COLOR_RGB2GRAY)
    detector=cv2.ORB_create(nfeatures=1800)
    kp1,des1=detector.detectAndCompute(gray_source,None)
    kp2,des2=detector.detectAndCompute(gray_ref,None)
    if des1 is None or des2 is None:
        return source, 'Alignment failed (not enough detectable landmarks); review all results'
    matches=cv2.BFMatcher(cv2.NORM_HAMMING).knnMatch(des1,des2,k=2)
    good=[m for pair in matches if len(pair)==2 for m,n in [pair] if m.distance<0.72*n.distance]
    if len(good)<12:
        return source, f'Alignment failed ({len(good)} matches); review all results'
    pts1=np.float32([kp1[m.queryIdx].pt for m in good]).reshape(-1,1,2)
    pts2=np.float32([kp2[m.trainIdx].pt for m in good]).reshape(-1,1,2)
    matrix,inliers=cv2.findHomography(pts1,pts2,cv2.RANSAC,5)
    if matrix is None or inliers is None or int(inliers.sum())<10:
        return source,'Alignment failed (poor homography); review all results'
    fraction=float(inliers.sum())/len(good)
    if fraction<0.50:
        return source,'Alignment failed (inconsistent landmarks); review all results'
    # Repeated printed lines can create a misleading cluster of feature matches.
    # Demand landmarks across a meaningful area of the reference page.
    inlier_ref=pts2[inliers.reshape(-1).astype(bool)].reshape(-1,2)
    spread=np.ptp(inlier_ref,axis=0)
    if spread[0]<0.30*ref_w or spread[1]<0.30*ref_h:
        return source,'Alignment failed (landmarks cover too little of the form); review manually'
    if not np.all(np.isfinite(matrix)):
        return source,'Alignment failed (invalid transform); review manually'
    aligned=cv2.warpPerspective(source,matrix,(ref_w,ref_h),borderMode=cv2.BORDER_CONSTANT,borderValue=(255,255,255))
    return aligned,None

def crop_box(rgb,region):
    h,w=rgb.shape[:2]
    x1,y1,x2,y2=region
    coords=[max(0,min(w-1,int(x1*w))),max(0,min(h-1,int(y1*h))),max(1,min(w,int(x2*w))),max(1,min(h,int(y2*h)))]
    x1,y1,x2,y2=coords
    if x2<=x1 or y2<=y1: raise ValueError('Invalid crop rectangle')
    return rgb[y1:y2,x1:x2]

def improve_for_ocr(crop):
    # Mild local contrast correction, without destructive binarization.
    lab=cv2.cvtColor(crop,cv2.COLOR_RGB2LAB)
    l,a,b=cv2.split(lab)
    l=cv2.createCLAHE(clipLimit=1.5,tileGridSize=(8,8)).apply(l)
    rgb=cv2.cvtColor(cv2.merge((l,a,b)),cv2.COLOR_LAB2RGB)
    if rgb.shape[1]<500:
        scale=min(3.0,500/max(1,rgb.shape[1]))
        rgb=cv2.resize(rgb,None,fx=scale,fy=scale,interpolation=cv2.INTER_CUBIC)
    return rgb

def checkbox_value(crop):
    """Conservative grayscale ink-density heuristic; always requires review."""
    gray=cv2.cvtColor(crop,cv2.COLOR_RGB2GRAY)
    h,w=gray.shape
    if h<8 or w<8:return 'Unclear',None
    center=gray[max(1,h//5):max(h//5+1,4*h//5),max(1,w//5):max(w//5+1,4*w//5)]
    ink=float(np.mean(center<110))
    # Do not present this as certain: printed box borders and handwriting overlap.
    guess='Possibly checked' if ink>0.15 else 'Possibly unchecked'
    return guess,ink

def process_document(path,reference_path,regions,crops_dir,ocr):
    source=load_rgb(path)
    reference=load_rgb(reference_path) if reference_path and Path(reference_path).is_file() else None
    aligned,alignment_note=register_image(source,reference)
    if alignment_note:
        raise AlignmentError(alignment_note + '. OCR was intentionally skipped to avoid incorrect field mapping. Use manual entry or retry with a clearer photo.')
    Path(crops_dir).mkdir(parents=True,exist_ok=True)
    fields={}
    for key in FIELD_LABELS:
        crop=crop_box(aligned,regions[key])
        cropfile=Path(crops_dir)/(key+'.jpg')
        Image.fromarray(crop).save(cropfile,quality=90)
        if key in ('delivery','pickup'):
            value,score=checkbox_value(crop)
            fields[key]={'raw_text':value,'value':value,'confidence':None,'warning':'Checkbox estimate requires manual verification','reviewed':False}
        else:
            text,score=ocr.recognize(improve_for_ocr(crop))
            from .validation import validate
            normalized,warning=validate(key,text)
            notices=[]
            if warning: notices.append(warning)
            if score is not None and score<0.75: notices.append('Low OCR score — check handwriting')
            if alignment_note: notices.append('Template alignment not verified')
            fields[key]={'raw_text':text,'value':normalized,'confidence':score,'warning':'; '.join(notices) or None,'reviewed':False}
    return fields,alignment_note
