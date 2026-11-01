import os
from pathlib import Path

DATA_DIR = Path(os.getenv('DATA_DIR', '/data' if Path('/data').exists() else './data')).resolve()
DATABASE_URL = os.getenv('DATABASE_URL', f'sqlite:///{DATA_DIR / "orders.sqlite3"}')
COOKIE_SECURE = os.getenv('COOKIE_SECURE', 'false').lower() == 'true'
MAX_UPLOAD_MB = int(os.getenv('MAX_UPLOAD_MB', '20'))
MAX_IMAGE_PIXELS = int(os.getenv('MAX_IMAGE_PIXELS', '25000000'))
SESSION_HOURS = int(os.getenv('SESSION_HOURS', '24'))
ALLOWED_HOSTS = [s.strip() for s in os.getenv('ALLOWED_HOSTS', '*').split(',') if s.strip()]
OCR_MODEL = os.getenv('OCR_MODEL', 'PP-OCRv5')
OCR_LANGUAGE = os.getenv('OCR_LANGUAGE', 'en')
WORKER_POLL_SECONDS = float(os.getenv('WORKER_POLL_SECONDS', '2'))
PROCESSING_STALE_MINUTES = int(os.getenv('PROCESSING_STALE_MINUTES', '30'))


def ensure_dirs():
    for name in ('uploads', 'crops', 'templates', 'exports', 'tmp'):
        (DATA_DIR / name).mkdir(parents=True, exist_ok=True)
