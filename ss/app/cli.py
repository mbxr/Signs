"""Run: python -m app.cli init-db | create-admin <username> | reset-password <username>."""
import getpass,sys
from .db import initialize,SessionLocal,User
from .security import password_hash

def main():
    cmd=sys.argv[1] if len(sys.argv)>1 else ''
    if cmd=='init-db':
        initialize();print('Database initialized.');return
    if cmd in ('create-admin','reset-password'):
        if len(sys.argv)<3: raise SystemExit('Supply a username')
        name=sys.argv[2].strip()
        if not (3<=len(name)<=80): raise SystemExit('Username must be 3–80 characters')
        password=getpass.getpass('New administrator password (12+ chars): ')
        confirm=getpass.getpass('Confirm password: ')
        if password!=confirm: raise SystemExit('Passwords do not match')
        try: hashed=password_hash(password)
        except ValueError as exc: raise SystemExit(str(exc))
        initialize()
        with SessionLocal.begin() as db:
            user=db.query(User).filter(User.username==name).first()
            if cmd=='create-admin' and user: raise SystemExit('User already exists')
            if cmd=='reset-password' and not user: raise SystemExit('User does not exist')
            if user: user.password_hash=hashed
            else:db.add(User(username=name,password_hash=hashed))
        print('Administrator account saved.');return
    raise SystemExit('Usage: python -m app.cli init-db | create-admin USER | reset-password USER')
if __name__=='__main__':main()
