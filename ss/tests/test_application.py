import io
from PIL import Image, ImageDraw
from openpyxl import load_workbook
from app.db import SessionLocal, Order, Job, Field, Template, FieldRevision
from app.worker import perform, recover_stale, acquire_job
from app.template import FIELD_LABELS
from app.validation import validate
from app.export import build_workbook
from app.image_processing import process_document, AlignmentError


def sample_jpg():
    """Synthetic structured form, no actual customer data."""
    out=io.BytesIO()
    img=Image.new('RGB',(900,1100),'white')
    d=ImageDraw.Draw(img)
    for y in range(80,1080,54):
        d.line([(45,y),(850,y)],fill='gray',width=2)
        d.text((57,y-16),f'Printed field {y} / 2026',fill='black')
    for x in range(80,860,125):
        d.rectangle((x,100,x+22,120),outline='black',width=2)
        d.text((x,1050),str(x),fill='black')
    img.save(out,format='JPEG',quality=92)
    return out.getvalue()


def calibrate(client, reference=None):
    """Real endpoints: reference upload followed by explicit calibration confirmation."""
    reference=reference or sample_jpg()
    resp=client.post('/api/template/reference',files={'file':('synthetic-reference.jpg',reference,'image/jpeg')})
    assert resp.status_code==200,resp.text
    t=client.get('/api/template').json()
    assert not t['calibrated']
    resp=client.put('/api/template',json={'regions':t['regions']})
    assert resp.status_code==200,resp.text
    assert client.get('/api/template').json()['calibrated']


def test_login_and_protected_routes(client):
    assert client.get('/api/stats').status_code==401
    assert client.post('/api/auth/login',json={'username':'testadmin','password':'wrong'}).status_code==401
    login=client.post('/api/auth/login',json={'username':'testadmin','password':'a-long-test-password!'})
    assert login.status_code==200
    assert client.post('/api/batches',json={'name':'No CSRF token'}).status_code==403
    assert client.get('/api/auth/me').json()['username']=='testadmin'


def test_batch_duplicate_worker_review_excel(logged_in):
    c=logged_in
    calibrate(c)
    batch=c.post('/api/batches',json={'name':'Integration test batch'})
    assert batch.status_code==200
    batch_id=batch.json()['id']
    jpg=sample_jpg()
    result=c.post(f'/api/batches/{batch_id}/files',files={'file':('synthetic_test.jpg',jpg,'image/jpeg')})
    assert result.status_code==200,result.text
    assert result.json()['status']=='queued'
    oid=result.json()['order_id']
    duplicate=c.post(f'/api/batches/{batch_id}/files',files={'file':('another-name.jpg',jpg,'image/jpeg')})
    assert duplicate.json()['status']=='duplicate'
    assert c.get(f'/api/orders/{oid}/image').status_code==200
    assert c.put(f'/api/orders/{oid}',json={'fields':{},'mark_reviewed':True}).status_code==409

    # Test real crop, database, review and Excel wiring with a controlled fake
    # recognition result. NOT a test of the real PaddleOCR engine.
    class StubLocalEngine:
        def recognize(self,rgb):return 'Sample handwriting',0.90
    with SessionLocal() as db:
        job=db.query(Job).filter_by(order_id=oid).first()
        jid=job.id
    perform(jid,StubLocalEngine())
    doc=c.get(f'/api/orders/{oid}')
    assert doc.status_code==200,doc.text
    assert doc.json()['status']=='completed'
    assert len(doc.json()['fields'])==len(FIELD_LABELS)
    assert c.get(f'/api/orders/{oid}/crop/name').status_code==200
    patch={key:{'value':f'Checked {key}','reviewed':True} for key in FIELD_LABELS}
    patch['name']['value']='=SUM(1,2)'  # Must remain literal in Excel.
    review=c.put(f'/api/orders/{oid}',json={'fields':patch,'mark_reviewed':True})
    assert review.status_code==200,review.text
    assert review.json()['review_status']=='reviewed'
    export=c.get(f'/api/export?ids={oid}')
    assert export.status_code==200
    wb=load_workbook(io.BytesIO(export.content))
    sheet=wb['Orders']
    assert sheet.max_row==2
    assert sheet['F2'].value=='=SUM(1,2)'
    assert sheet['F2'].data_type=='s'
    assert sheet['E2'].value=='reviewed'
    assert wb['Read me']['A2'].value.startswith('One row')


def test_template_region_validation(logged_in):
    c=logged_in
    template=c.get('/api/template').json()
    assert len(template['regions'])==13
    bad=dict(template['regions']);bad['name']=[0.9,0.2,0.2,0.5]
    assert c.put('/api/template',json={'regions':bad}).status_code==400
    calibrate(c)
    assert c.put('/api/template',json={'regions':template['regions']}).status_code==200


def test_upload_validation(logged_in):
    c=logged_in
    bid=c.post('/api/batches',json={'name':'Validation test'}).json()['id']
    wrong=c.post(f'/api/batches/{bid}/files',files={'file':('evil.jpg',b'not an image','image/jpeg')})
    assert wrong.status_code==400
    ext=c.post(f'/api/batches/{bid}/files',files={'file':('evil.svg',b'<svg/>','image/svg+xml')})
    assert ext.status_code==400


def test_field_validators():
    assert validate('telephone','(519) 831-7873')[0]=='519-831-7873'
    assert validate('email','bad-address')[1]
    assert validate('date_required','September 10')[0]=='September 10'
    assert validate('return_date','Overnight')[1] is None


def test_failed_job_retry(logged_in):
    c=logged_in
    calibrate(c)
    bid=c.post('/api/batches',json={'name':'Retry test'}).json()['id']
    # Different pixel content avoids duplicate-hash conflicts.
    photo=io.BytesIO()
    Image.new('RGB',(350,550),'ivory').save(photo,format='JPEG')
    result=c.post(f'/api/batches/{bid}/files',files={'file':('retry-photo.jpg',photo.getvalue(),'image/jpeg')})
    oid=result.json()['order_id']
    with SessionLocal.begin() as db:
        doc=db.get(Order,oid);doc.status='failed';doc.error='Temporary model failure'
        job=db.query(Job).filter_by(order_id=oid).first();job.state='failed';job.error='Temporary model failure'
    response=c.post(f'/api/orders/{oid}/retry')
    assert response.status_code==200
    assert c.get(f'/api/orders/{oid}').json()['status']=='queued'
    with SessionLocal() as db:
        assert db.query(Job).filter_by(order_id=oid).first().state=='queued'


def test_reject_upload_until_template_is_calibrated(logged_in):
    c=logged_in
    ref=c.post('/api/template/reference',files={'file':('another-reference.jpg',sample_jpg(),'image/jpeg')})
    assert ref.status_code==200
    assert c.get('/api/template').json()['calibrated'] is False
    bid=c.post('/api/batches',json={'name':'Uncalibrated'}).json()['id']
    res=c.post(f'/api/batches/{bid}/files',files={'file':('uncalibrated.jpg',sample_jpg(),'image/jpeg')})
    assert res.status_code==409
    assert 'calibrated' in res.json()['detail']


def test_alignment_failure_refuses_to_mislabel_fields(tmp_path):
    path=tmp_path/'blank.jpg'
    ref=tmp_path/'ref.jpg'
    Image.new('RGB',(400,500),'white').save(path)
    Image.new('RGB',(400,500),'white').save(ref)
    from app.template import DEFAULT_REGIONS
    class CannotBeCalled:
        def recognize(self,image):
            raise AssertionError('Do not run OCR if alignment failed')
    import pytest
    with pytest.raises(AlignmentError,match='OCR was intentionally skipped'):
        process_document(path,ref,DEFAULT_REGIONS,tmp_path/'crops',CannotBeCalled())


def test_failed_order_can_be_entered_manually_and_edits_are_audited(logged_in):
    c=logged_in
    calibrate(c)
    bid=c.post('/api/batches',json={'name':'Manual recovery'}).json()['id']
    img=io.BytesIO()
    Image.new('RGB',(451,601),'lightblue').save(img,format='JPEG')
    res=c.post(f'/api/batches/{bid}/files',files={'file':('manual.jpg',img.getvalue(),'image/jpeg')})
    assert res.status_code==200,res.text
    order_id=res.json()['order_id']
    with SessionLocal.begin() as db:
        db.get(Order,order_id).status='failed'
        db.query(Job).filter_by(order_id=order_id).first().state='failed'
    patch={key:{'value':'Verified '+key,'reviewed':True} for key in FIELD_LABELS}
    r=c.put(f'/api/orders/{order_id}',json={'fields':patch,'mark_reviewed':True})
    assert r.status_code==200,r.text
    record=c.get(f'/api/orders/{order_id}').json()
    assert record['status']=='manual' and record['review_status']=='reviewed'
    audit=c.get(f'/api/orders/{order_id}/history')
    assert audit.status_code==200
    assert len(audit.json())==len(FIELD_LABELS)
    assert any(e['field']=='name' and e['new']=='Verified name' for e in audit.json())
    xlsx=c.get(f'/api/export?ids={order_id}')
    wb=load_workbook(io.BytesIO(xlsx.content))
    assert wb['Orders']['F2'].value=='Verified name'


def test_alignment_preflight_with_synthetic_matching_photo(logged_in):
    c=logged_in
    ref=sample_jpg()
    calibrate(c,ref)
    r=c.post('/api/template/preflight',files={'file':('test.jpg',ref,'image/jpeg')})
    assert r.status_code==200,r.text
    assert r.json()['aligned'] is True,r.text


def test_renamed_file_must_match_actual_format(logged_in):
    c=logged_in
    calibrate(c)
    bid=c.post('/api/batches',json={'name':'File contents'}).json()['id']
    r=c.post(f'/api/batches/{bid}/files',files={'file':('wrong.png',sample_jpg(),'image/png')})
    assert r.status_code==400
    assert 'extension' in r.json()['detail']


def test_ground_truth_benchmark_aggregates_only():
    from app.benchmark import measure, distance
    assert distance('kitten','sitting')==3
    report=measure([{'order_id':'1','name':'Jane Doe','telephone':'519-123-4567'},
                    {'order_id':'2','name':'Bob Smith','telephone':'519-999-0000'}],
                   {1:{'name':'Jane Doe','telephone':'519-123-4567'},
                    2:{'name':'Bob Smth','telephone':'519-999-0000'}})
    assert report['fields']['name']['exact_match_rate']==0.5
    assert report['fields']['telephone']['exact_match_rate']==1
    assert report['complete_order_exact_match_rate']==0.5
    assert 'Jane Doe' not in str(report)
    assert '519-123-4567' not in str(report)
