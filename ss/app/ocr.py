"""Lazy, local PaddleOCR 3.x adapter. Worker image installs PaddlePaddle+PaddleOCR.
No image bytes are ever sent to hosted APIs.
"""
import os
import numpy as np

class LocalOCR:
    def __init__(self):
        # Paddle OCR model caches are persisted under /data/models by the worker container.
        os.environ.setdefault('PADDLE_PDX_MODEL_SOURCE', 'BOS')
        os.environ.setdefault('DISABLE_MODEL_SOURCE_CHECK', 'True')
        os.environ.setdefault('OMP_NUM_THREADS','2')
        try:
            from paddleocr import PaddleOCR
        except ImportError as exc:
            raise RuntimeError('PaddleOCR missing. Use the Docker Compose worker image. Do not run jobs in the API image.') from exc
        self.engine = PaddleOCR(
            lang='en',
            ocr_version=os.getenv('OCR_MODEL','PP-OCRv5'),
            use_doc_orientation_classify=False,
            use_doc_unwarping=False,
            use_textline_orientation=False,
        )

    def recognize(self, rgb_image: np.ndarray):
        # On 3.x returns a sequence of OCRResult objects, with dict-like access.
        results=self.engine.predict(rgb_image)
        rows=[]
        for result in results:
            payload=getattr(result,'json',None)
            if payload is not None:
                data=payload.get('res',payload)
            else:
                data=result.get('res',result)
            texts=list(data.get('rec_texts',[]))
            scores=list(data.get('rec_scores',[]))
            boxes=data.get('rec_boxes',[])
            for i,text in enumerate(texts):
                score=float(scores[i]) if i<len(scores) else None
                box=boxes[i] if i<len(boxes) else [0,i*10,0,i*10]
                rows.append((int(box[1]),int(box[0]),str(text),score))
        rows.sort(key=lambda x:(round(x[0]/15),x[1]))
        return '\n'.join(r[2] for r in rows).strip(), (min((r[3] for r in rows if r[3] is not None), default=None))

if __name__=='__main__':
    print('Loading local PaddleOCR model (first run may download model weights)...')
    model=LocalOCR()
    print('PaddleOCR model ready. No customer data was used.')
