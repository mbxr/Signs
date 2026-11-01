"""Authenticated API and lightweight one-page interface."""
import hashlib, io, json, secrets, time, re, uuid
from contextlib import asynccontextmanager
from datetime import timedelta
from pathlib import Path
from fastapi import FastAPI, Depends, HTTPException, Request, UploadFile, File, Query
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from pydantic import BaseModel, Field as PField
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from PIL import Image, UnidentifiedImageError
from . import config
from .db import initialize, SessionLocal, User, Session as LoginSession, Batch, Order, Field, FieldRevision, Job, Template, now
from .security import authenticated, get_db, make_session, password_check, digest_token
from .template import FIELD_LABELS, validate_regions
from .export import build_workbook
from .image_processing import load_rgb, register_image

@asynccontextmanager
async def lifespan(app: FastAPI):
    initialize()
    yield

app=FastAPI(title='Surprise Signs Digitizer',docs_url=None,redoc_url=None,openapi_url=None,lifespan=lifespan)
app.add_middleware(TrustedHostMiddleware,allowed_hosts=config.ALLOWED_HOSTS)
app.mount('/static',StaticFiles(directory=Path(__file__).resolve().parent.parent/'static'),name='static')

@app.middleware('http')
async def security_headers(request,call_next):
    response=await call_next(request)
    response.headers['X-Content-Type-Options']='nosniff'
    response.headers['Referrer-Policy']='no-referrer'
    response.headers['X-Frame-Options']='DENY'
    response.headers['Content-Security-Policy']="default-src 'self'; style-src 'self' 'unsafe-inline'; script-src 'self'; img-src 'self' blob: data:; connect-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'none'"
    response.headers['Cache-Control']='no-store'
    if config.COOKIE_SECURE: response.headers['Strict-Transport-Security']='max-age=31536000; includeSubDomains'
    return response

@app.get('/')
def home():
    return FileResponse(Path(__file__).resolve().parent.parent/'static'/'index.html')

@app.get('/api/health')
def health(): return {'status':'ok'}

class LoginData(BaseModel):
    username:str
    password:str

# Per-process rate limit helps suppress brute forcing; use reverse-proxy rate limits as well.
login_failures={}

@app.post('/api/auth/login')
def login(data:LoginData,request:Request,db:Session=Depends(get_db)):
    ip=request.client.host if request.client else 'unknown'
    stamp=time.monotonic()
    recent=[v for v in login_failures.get(ip,[]) if stamp-v<900]
    if len(recent)>=8: raise HTTPException(429,'Too many login attempts. Try again later.')
    user=db.query(User).filter(User.username==data.username).first()
    if not user or not password_check(data.password,user.password_hash):
        recent.append(stamp);login_failures[ip]=recent
        raise HTTPException(401,'Incorrect username or password')
    login_failures.pop(ip,None)
    token,csrf=make_session(db,user);db.commit()
    from fastapi.responses import JSONResponse
    response=JSONResponse({'username':user.username,'csrf':csrf})
    response.set_cookie('ssid',token,httponly=True,secure=config.COOKIE_SECURE,samesite='strict',max_age=config.SESSION_HOURS*3600,path='/')
    return response

@app.get('/api/auth/me')
def me(auth=Depends(authenticated)):
    return {'username':auth['user'].username,'csrf':auth['csrf']}

@app.post('/api/auth/logout')
def logout(auth=Depends(authenticated),db:Session=Depends(get_db)):
    db.delete(auth['session']);db.commit()
    from fastapi.responses import JSONResponse
    response=JSONResponse({'ok':True})
    response.delete_cookie('ssid',path='/')
    return response

@app.get('/api/stats')
def stats(auth=Depends(authenticated),db:Session=Depends(get_db)):
    order_status=dict(db.query(Order.status,func.count(Order.id)).group_by(Order.status).all())
    review=dict(db.query(Order.review_status,func.count(Order.id)).group_by(Order.review_status).all())
    return {'total':sum(order_status.values()),'queued':order_status.get('queued',0),
            'processing':order_status.get('processing',0),'completed':order_status.get('completed',0)+order_status.get('manual',0),
            'failed':order_status.get('failed',0),'reviewed':review.get('reviewed',0),
            'needs_review':review.get('needs_review',0)+review.get('unreviewed',0)}

class BatchCreate(BaseModel):
    name:str=PField(min_length=1,max_length=120)

@app.post('/api/batches')
def create_batch(data:BatchCreate,auth=Depends(authenticated),db:Session=Depends(get_db)):
    batch=Batch(name=data.name.strip());db.add(batch);db.commit();return {'id':batch.id,'name':batch.name}

@app.get('/api/batches')
def batches(auth=Depends(authenticated),db:Session=Depends(get_db)):
    counts=dict(db.query(Order.batch_id,func.count(Order.id)).group_by(Order.batch_id).all())
    return [{'id':b.id,'name':b.name,'created_at':b.created_at.isoformat(),'count':counts.get(b.id,0)} for b in db.query(Batch).order_by(Batch.id.desc()).limit(200)]

async def store_image(upload:UploadFile):
    name=Path(upload.filename or 'upload.jpg').name[:240]
    if Path(name).suffix.lower() not in ('.jpg','.jpeg','.png','.webp'):
        raise HTTPException(400,'Only JPG, PNG and WebP photographs are supported')
    tmp=config.DATA_DIR/'tmp'/(uuid.uuid4().hex+'.upload')
    size=0;digest=hashlib.sha256()
    try:
        with tmp.open('wb') as out:
            while True:
                chunk=await upload.read(1024*1024)
                if not chunk:break
                size+=len(chunk)
                if size>config.MAX_UPLOAD_MB*1024*1024:
                    raise HTTPException(413,f'Maximum file size is {config.MAX_UPLOAD_MB} MB')
                digest.update(chunk);out.write(chunk)
        if not size: raise HTTPException(400,'Empty file')
        Image.MAX_IMAGE_PIXELS=config.MAX_IMAGE_PIXELS
        try:
            with Image.open(tmp) as img:
                if img.format not in ('JPEG','PNG','WEBP'):
                    raise HTTPException(400,'File contents are not a supported image format')
                accepted={'JPEG':('.jpg','.jpeg'),'PNG':('.png',),'WEBP':('.webp',)}
                if Path(name).suffix.lower() not in accepted[img.format]:
                    raise HTTPException(400,'Filename extension does not match image contents')
                if img.width*img.height>config.MAX_IMAGE_PIXELS:
                    raise HTTPException(413,'Image dimensions are too large')
                img.verify()
        except (UnidentifiedImageError,Image.DecompressionBombError,OSError) as exc:
            raise HTTPException(400,'File does not contain a valid image') from exc
        return tmp,name,digest.hexdigest()
    except Exception:
        tmp.unlink(missing_ok=True)
        raise
    finally:
        await upload.close()

@app.post('/api/batches/{batch_id}/files')
async def upload_file(batch_id:int,file:UploadFile=File(...),auth=Depends(authenticated),db:Session=Depends(get_db)):
    if not db.get(Batch,batch_id):raise HTTPException(404,'Batch not found')
    tmp,name,digest=await store_image(file)
    template=db.query(Template).order_by(Template.id.desc()).first()
    if not template or not template.calibrated or not template.reference_path or not Path(template.reference_path).is_file():
        tmp.unlink(missing_ok=True)
        raise HTTPException(409, 'First upload a reference form and save its calibrated field regions under Form template.')
    prior=db.query(Order).filter(Order.sha256==digest).first()
    if prior:
        tmp.unlink(missing_ok=True)
        return {'status':'duplicate','order_id':prior.id,'filename':name}
    destination=config.DATA_DIR/'uploads'/(uuid.uuid4().hex+Path(name).suffix.lower())
    try:
        tmp.replace(destination)
        order=Order(batch_id=batch_id,template_id=template.id,filename=name,path=str(destination),sha256=digest)
        db.add(order);db.flush();db.add(Job(order_id=order.id));db.commit()
        return {'status':'queued','order_id':order.id,'filename':name}
    except IntegrityError:
        db.rollback();destination.unlink(missing_ok=True)
        raise HTTPException(409,'Duplicate upload processed concurrently')
    except Exception:
        db.rollback();destination.unlink(missing_ok=True)
        raise


def order_dict(order,fields=None):
    result={'id':order.id,'batch_id':order.batch_id,'filename':order.filename,
            'status':order.status,'review_status':order.review_status,'error':order.error,
            'alignment_note':order.alignment_note,'created_at':order.created_at.isoformat() if order.created_at else ''}
    if fields is not None:
        result['fields']={f.key:{'value':f.value,'raw_text':f.raw_text,'confidence':f.confidence,'warning':f.warning,'reviewed':f.reviewed} for f in fields}
    return result

@app.get('/api/orders')
def orders(batch_id:int|None=None,status:str|None=None,review_status:str|None=None,q:str='',
           limit:int=Query(default=100,le=500,ge=1),offset:int=Query(default=0,ge=0),
           auth=Depends(authenticated),db:Session=Depends(get_db)):
    query=db.query(Order)
    if batch_id is not None:query=query.filter(Order.batch_id==batch_id)
    if status:query=query.filter(Order.status==status)
    if review_status:query=query.filter(Order.review_status==review_status)
    if q:
        pattern='%'+q[:100].replace('%','\\%').replace('_','\\_')+'%'
        matched=db.query(Field.order_id).filter(Field.value.ilike(pattern,escape='\\')).subquery()
        query=query.filter((Order.filename.ilike(pattern,escape='\\'))|Order.id.in_(matched))
    count=query.count()
    found=query.order_by(Order.id.desc()).offset(offset).limit(limit).all()
    return {'total':count,'orders':[order_dict(o) for o in found]}

@app.get('/api/orders/{order_id}')
def get_order(order_id:int,auth=Depends(authenticated),db:Session=Depends(get_db)):
    order=db.get(Order,order_id)
    if not order:raise HTTPException(404,'Order not found')
    return order_dict(order,db.query(Field).filter(Field.order_id==order_id).all())

class FieldPatch(BaseModel):
    value:str=PField(max_length=5000)
    reviewed:bool=False

class OrderPatch(BaseModel):
    fields:dict[str,FieldPatch]
    mark_reviewed:bool=False

@app.put('/api/orders/{order_id}')
def edit_order(order_id:int,patch:OrderPatch,auth=Depends(authenticated),db:Session=Depends(get_db)):
    order=db.get(Order,order_id)
    if not order:raise HTTPException(404,'Order not found')
    if order.status not in ('completed','failed','manual'):raise HTTPException(409,'Wait for OCR to finish before editing')
    if any(k not in FIELD_LABELS for k in patch.fields):raise HTTPException(400,'Unknown field key')
    current={f.key:f for f in db.query(Field).filter(Field.order_id==order_id)}
    for key,item in patch.fields.items():
        f=current.get(key)
        if not f:
            f=Field(order_id=order_id,key=key,raw_text='')
            db.add(f);current[key]=f
        if f.value != item.value:
            db.add(FieldRevision(order_id=order_id, user_id=auth['user'].id, key=key,
                                 previous_value=f.value or '', new_value=item.value))
        f.value=item.value
        f.reviewed=item.reviewed
    if patch.mark_reviewed:
        if len(current)!=len(FIELD_LABELS) or not all(f.reviewed for f in current.values()):
            raise HTTPException(400,'Review all fields before marking order reviewed')
        order.review_status='reviewed'
    else:
        order.review_status='reviewed' if len(current)==len(FIELD_LABELS) and all(f.reviewed for f in current.values()) else 'needs_review'
    if order.status=='failed':
        order.status='manual'
    db.commit()
    return {'ok':True,'review_status':order.review_status}


@app.get('/api/orders/{order_id}/history')
def order_history(order_id:int, auth=Depends(authenticated), db:Session=Depends(get_db)):
    if not db.get(Order, order_id):
        raise HTTPException(404, 'Order not found')
    edits=db.query(FieldRevision).filter(FieldRevision.order_id==order_id).order_by(FieldRevision.id.desc()).limit(500).all()
    return [{'field':e.key,'previous':e.previous_value,'new':e.new_value,'changed_at':e.changed_at.isoformat(),'user_id':e.user_id} for e in edits]

@app.post('/api/orders/{order_id}/retry')
def retry_order(order_id:int,auth=Depends(authenticated),db:Session=Depends(get_db)):
    order=db.get(Order,order_id)
    if not order: raise HTTPException(404,'Order not found')
    if order.status not in ('failed','manual'): raise HTTPException(409,'Only failed or manually entered orders can be retried')
    job=db.query(Job).filter(Job.order_id==order_id).first()
    if not job: raise HTTPException(404,'Processing job missing')
    job.state='queued';job.tries=0;job.started_at=None;job.finished_at=None;job.error=None
    order.status='queued';order.error=None;order.review_status='needs_review'
    db.commit()
    return {'ok':True,'status':'queued'}

@app.get('/api/orders/{order_id}/image')
def order_image(order_id:int,auth=Depends(authenticated),db:Session=Depends(get_db)):
    order=db.get(Order,order_id)
    if not order:raise HTTPException(404,'Order not found')
    path=Path(order.path)
    if not path.is_file():raise HTTPException(404,'Original image unavailable')
    return FileResponse(path,media_type={'jpg':'image/jpeg','jpeg':'image/jpeg','png':'image/png','webp':'image/webp'}.get(path.suffix.lower().lstrip('.'),'application/octet-stream'))

@app.get('/api/orders/{order_id}/crop/{field_key}')
def order_crop(order_id:int,field_key:str,auth=Depends(authenticated),db:Session=Depends(get_db)):
    if not db.get(Order,order_id) or field_key not in FIELD_LABELS:raise HTTPException(404,'Not found')
    path=config.DATA_DIR/'crops'/str(order_id)/(field_key+'.jpg')
    if not path.is_file():raise HTTPException(404,'Crop not available')
    return FileResponse(path,media_type='image/jpeg')

@app.get('/api/template')
def get_template(auth=Depends(authenticated),db:Session=Depends(get_db)):
    t=db.query(Template).order_by(Template.id.desc()).first()
    return {'id':t.id,'name':t.name,'regions':json.loads(t.regions_json),'has_reference':bool(t.reference_path),'calibrated':t.calibrated,'labels':FIELD_LABELS}

class TemplatePatch(BaseModel):
    regions:dict[str,list[float]]

@app.put('/api/template')
def update_template(data:TemplatePatch,auth=Depends(authenticated),db:Session=Depends(get_db)):
    try: validate_regions(data.regions)
    except ValueError as exc:raise HTTPException(400,str(exc)) from exc
    old=db.query(Template).order_by(Template.id.desc()).first()
    if not old.reference_path or not Path(old.reference_path).is_file():
        raise HTTPException(409,'Upload a reference photo before calibrating field regions')
    newer=Template(name='Surprise Signs calibrated form',regions_json=json.dumps(data.regions),reference_path=old.reference_path,calibrated=True)
    db.add(newer);db.commit()
    return {'id':newer.id,'ok':True,'note':'New uploads use this template. Already queued uploads retain their original template version.'}

@app.post('/api/template/reference')
async def upload_reference(file:UploadFile=File(...),auth=Depends(authenticated),db:Session=Depends(get_db)):
    tmp,name,digest=await store_image(file)
    path=config.DATA_DIR/'templates'/(digest+Path(name).suffix.lower())
    tmp.replace(path)
    old=db.query(Template).order_by(Template.id.desc()).first()
    newer=Template(name='Surprise Signs reference photo — calibration required',regions_json=old.regions_json,reference_path=str(path),calibrated=False)
    db.add(newer);db.commit()
    return {'ok':True,'id':newer.id,'has_reference':True}

@app.post('/api/template/preflight')
async def preflight_alignment(file:UploadFile=File(...),auth=Depends(authenticated),db:Session=Depends(get_db)):
    """Test geometry on a sample photo; do not store this photo as an order."""
    template=db.query(Template).order_by(Template.id.desc()).first()
    if not template or not template.calibrated or not template.reference_path or not Path(template.reference_path).is_file():
        raise HTTPException(409,'Save a calibrated reference first')
    tmp,_,_=await store_image(file)
    try:
        candidate=load_rgb(tmp)
        reference=load_rgb(template.reference_path)
        aligned,error=register_image(candidate,reference)
        return {'aligned':error is None,'message':error or 'Alignment found. Verify field crops on an actual processed order before bulk import.',
                'reference_width':reference.shape[1],'reference_height':reference.shape[0]}
    finally:
        tmp.unlink(missing_ok=True)

@app.get('/api/template/reference')
def reference_image(auth=Depends(authenticated),db:Session=Depends(get_db)):
    t=db.query(Template).order_by(Template.id.desc()).first()
    if not t.reference_path or not Path(t.reference_path).is_file():raise HTTPException(404,'Upload a reference photograph first')
    path=Path(t.reference_path)
    return FileResponse(path,media_type={'jpg':'image/jpeg','jpeg':'image/jpeg','png':'image/png','webp':'image/webp'}.get(path.suffix.lower().lstrip('.'),'application/octet-stream'))

@app.get('/api/export')
def export_orders(batch_id:int|None=None,reviewed_only:bool=False,ids:str|None=None,
                  auth=Depends(authenticated),db:Session=Depends(get_db)):
    query=db.query(Order)
    if batch_id is not None: query=query.filter(Order.batch_id==batch_id)
    if reviewed_only:query=query.filter(Order.review_status=='reviewed')
    if ids:
        try:
            selected=[int(s) for s in ids.split(',') if s.strip()]
            if len(selected)>5000:raise ValueError()
        except ValueError:raise HTTPException(400,'Invalid order IDs')
        query=query.filter(Order.id.in_(selected))
    chosen=query.order_by(Order.id).limit(10000).all()
    if not chosen:raise HTTPException(404,'No orders match this export')
    field_rows=db.query(Field).filter(Field.order_id.in_([o.id for o in chosen])).all()
    by_order={}
    for field in field_rows: by_order.setdefault(field.order_id,{})[field.key]=field
    stream=build_workbook(chosen,by_order)
    filename='surprise_signs_orders_'+now().strftime('%Y%m%d_%H%M%S')+'.xlsx'
    return StreamingResponse(stream,media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',headers={'Content-Disposition':f'attachment; filename="{filename}"'})
