"""Single-process durable job worker. No queue broker required."""
import json, logging, os, signal, time
from pathlib import Path
from datetime import timedelta
from sqlalchemy import update, select
from . import config
from .db import initialize, SessionLocal, Job, Order, Field, Template, now
from .template import validate_regions
from .image_processing import process_document

logging.basicConfig(level=logging.INFO,format='%(asctime)s %(levelname)s %(message)s')
log=logging.getLogger('worker')
stop=False

def signal_stop(*args):
    global stop
    stop=True

def recover_stale():
    with SessionLocal.begin() as db:
        # This deployment runs ONE worker. On restart, every in-flight job was interrupted.
        old=db.query(Job).filter(Job.state=='processing').all()
        for job in old:
            job.state='queued'
            order=db.get(Order,job.order_id)
            if order: order.status='queued'
        if old: log.warning('Recovered %d stale jobs',len(old))

def acquire_job():
    with SessionLocal.begin() as db:
        job=db.query(Job).filter(Job.state=='queued').order_by(Job.id).first()
        if not job: return None
        if job.tries>=3:
            job.state='failed';job.error='Maximum retry limit reached'
            db.get(Order,job.order_id).status='failed'
            return None
        job.state='processing';job.tries+=1;job.started_at=now()
        db.get(Order,job.order_id).status='processing'
        return job.id

def perform(job_id,ocr):
    with SessionLocal() as db:
        job=db.get(Job,job_id)
        order=db.get(Order,job.order_id)
        template=db.get(Template,order.template_id)
        order_id=order.id
        path=order.path
        reference=template.reference_path
        if not template.calibrated or not template.reference_path:
            raise ValueError('This order was uploaded before template calibration; cannot safely process')
        regions=validate_regions(json.loads(template.regions_json))
    crops_dir=config.DATA_DIR/'crops'/str(order_id)
    values,alignment_note=process_document(path,reference,regions,crops_dir,ocr)
    with SessionLocal.begin() as db:
        order=db.get(Order,order_id)
        # Avoid overwriting fields previously corrected by humans during retry.
        current={f.key:f for f in db.query(Field).filter(Field.order_id==order_id)}
        for key,extracted in values.items():
            field=current.get(key)
            if field and field.reviewed: continue
            if not field:
                field=Field(order_id=order_id,key=key)
                db.add(field)
            for attr,value in extracted.items(): setattr(field,attr,value)
        order.status='completed';order.alignment_note=alignment_note;order.error=None
        job=db.get(Job,job_id)
        job.state='succeeded';job.error=None;job.finished_at=now()

def run():
    initialize();recover_stale()
    log.info('Local OCR worker starting; no hosted AI service is used')
    ocr=None
    while not stop:
        job_id=acquire_job()
        if job_id is None:
            time.sleep(config.WORKER_POLL_SECONDS);continue
        try:
            if ocr is None:
                from .ocr import LocalOCR
                ocr=LocalOCR()
            perform(job_id,ocr)
            log.info('Processed order %s',job_id)
        except Exception as exc:
            log.exception('Job %s failed',job_id)
            with SessionLocal.begin() as db:
                job=db.get(Job,job_id)
                if job:
                    job.error=str(exc)[:1200]
                    job.state='failed'
                    job.finished_at=now()
                    order=db.get(Order,job.order_id)
                    order.error=str(exc)[:1200];order.status='failed'
    log.info('Worker stopped')

if __name__=='__main__':
    signal.signal(signal.SIGTERM,signal_stop)
    signal.signal(signal.SIGINT,signal_stop)
    run()
