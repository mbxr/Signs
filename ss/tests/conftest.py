import io, os, tempfile
from pathlib import Path
import pytest

TEST_DATA=Path(tempfile.mkdtemp(prefix='surprise_signs_tests_'))
os.environ['DATA_DIR']=str(TEST_DATA)
os.environ['DATABASE_URL']=f'sqlite:///{TEST_DATA / "test.sqlite3"}'
os.environ['COOKIE_SECURE']='false'

from fastapi.testclient import TestClient
from app.db import initialize, SessionLocal, User
from app.security import password_hash
from app.main import app

@pytest.fixture()
def client():
    with TestClient(app) as c:
        with SessionLocal.begin() as db:
            if not db.query(User).filter_by(username='testadmin').first():
                db.add(User(username='testadmin',password_hash=password_hash('a-long-test-password!')))
        yield c

@pytest.fixture()
def logged_in(client):
    response=client.post('/api/auth/login',json={'username':'testadmin','password':'a-long-test-password!'})
    assert response.status_code==200,response.text
    csrf=response.json()['csrf']
    client.headers.update({'X-CSRF-Token':csrf})
    return client
