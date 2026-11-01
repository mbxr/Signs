"""Verify that a database from the first ZIP can be read by the revised release."""
import os
import sqlite3
import subprocess
import sys
from pathlib import Path


def test_v1_template_schema_additive_upgrade(tmp_path):
    db_path=tmp_path/'old_version.sqlite3'
    with sqlite3.connect(db_path) as db:
        db.execute('''CREATE TABLE templates (
            id INTEGER PRIMARY KEY, name VARCHAR(120) NOT NULL,
            regions_json TEXT NOT NULL, reference_path VARCHAR(400),
            created_at DATETIME)''')
        db.execute("INSERT INTO templates (id,name,regions_json) VALUES (1,'v1 template','{}')")
    env=os.environ.copy()
    env['DATA_DIR']=str(tmp_path)
    env['DATABASE_URL']='sqlite:///'+str(db_path)
    code='''from app.db import initialize,SessionLocal,Template
initialize()
with SessionLocal() as db:
    old=db.get(Template,1)
    assert old.calibrated is False
    assert old.name=='v1 template'
'''
    result=subprocess.run([sys.executable,'-c',code],env=env,check=False,capture_output=True,text=True,timeout=20)
    assert result.returncode==0,result.stderr
    with sqlite3.connect(db_path) as db:
        names={row[1] for row in db.execute('PRAGMA table_info(templates)')}
        assert 'calibrated' in names
