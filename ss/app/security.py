import hashlib, hmac, secrets
from datetime import timedelta
from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session as DBSession
from .db import User, Session as LoginSession, SessionLocal, now
from .config import SESSION_HOURS

def password_hash(password: str) -> str:
    if len(password) < 12: raise ValueError('Password must contain at least 12 characters')
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1)
    return 'scrypt$' + salt.hex() + '$' + digest.hex()

def password_check(password: str, stored: str) -> bool:
    try:
        kind,salt,digest = stored.split('$')
        if kind != 'scrypt': return False
        computed=hashlib.scrypt(password.encode(),salt=bytes.fromhex(salt),n=2**14,r=8,p=1)
        return hmac.compare_digest(computed,bytes.fromhex(digest))
    except (ValueError, TypeError):
        return False

def digest_token(token):
    return hashlib.sha256(token.encode()).hexdigest()

def make_session(db: DBSession, user: User):
    token=secrets.token_urlsafe(40)
    csrf=secrets.token_urlsafe(32)
    db.add(LoginSession(user_id=user.id,token_hash=digest_token(token),csrf_token=csrf,expires_at=now()+timedelta(hours=SESSION_HOURS)))
    return token,csrf

def get_db():
    with SessionLocal() as db: yield db

def authenticated(request: Request, db:DBSession=Depends(get_db)):
    token=request.cookies.get('ssid','')
    if not token: raise HTTPException(401,'Please log in')
    login=db.query(LoginSession).filter(LoginSession.token_hash==digest_token(token),LoginSession.expires_at>now()).first()
    if not login: raise HTTPException(401,'Session expired')
    if request.method in ('POST','PUT','PATCH','DELETE'):
        supplied=request.headers.get('X-CSRF-Token','')
        if not supplied or not hmac.compare_digest(supplied,login.csrf_token):
            raise HTTPException(403,'Invalid CSRF token')
    user=db.get(User,login.user_id)
    if not user: raise HTTPException(401,'User no longer exists')
    return {'user':user,'session':login,'csrf':login.csrf_token}
