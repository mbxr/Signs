from datetime import datetime, timezone
from sqlalchemy import create_engine, String, Integer, Float, Boolean, ForeignKey, Text, DateTime, UniqueConstraint, event
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker
from . import config


def now():
    return datetime.now(timezone.utc).replace(tzinfo=None)

class Base(DeclarativeBase):
    pass

class User(Base):
    __tablename__ = 'users'
    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(300))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)

class Session(Base):
    __tablename__ = 'sessions'
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    csrf_token: Mapped[str] = mapped_column(String(100))
    expires_at: Mapped[datetime] = mapped_column(DateTime, index=True)

class Batch(Base):
    __tablename__ = 'batches'
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)

class Template(Base):
    __tablename__ = 'templates'
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), default='Surprise Signs standard form')
    regions_json: Mapped[str] = mapped_column(Text)
    reference_path: Mapped[str | None] = mapped_column(String(400), nullable=True)
    calibrated: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)

class Order(Base):
    __tablename__ = 'orders'
    id: Mapped[int] = mapped_column(primary_key=True)
    batch_id: Mapped[int] = mapped_column(ForeignKey('batches.id'), index=True)
    template_id: Mapped[int] = mapped_column(ForeignKey('templates.id'))
    filename: Mapped[str] = mapped_column(String(250))
    path: Mapped[str] = mapped_column(String(450))
    sha256: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    status: Mapped[str] = mapped_column(String(25), default='queued', index=True)
    review_status: Mapped[str] = mapped_column(String(25), default='unreviewed', index=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    alignment_note: Mapped[str | None] = mapped_column(String(300), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=now, onupdate=now)

class Field(Base):
    __tablename__ = 'fields'
    __table_args__ = (UniqueConstraint('order_id', 'key', name='unique_field_per_order'),)
    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey('orders.id'), index=True)
    key: Mapped[str] = mapped_column(String(80))
    raw_text: Mapped[str] = mapped_column(Text, default='')
    value: Mapped[str] = mapped_column(Text, default='')
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    warning: Mapped[str | None] = mapped_column(String(500), nullable=True)
    reviewed: Mapped[bool] = mapped_column(Boolean, default=False)

class FieldRevision(Base):
    """Audit trail for corrections made in the private review interface."""
    __tablename__ = 'field_revisions'
    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey('orders.id'), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'))
    key: Mapped[str] = mapped_column(String(80))
    previous_value: Mapped[str] = mapped_column(Text, default='')
    new_value: Mapped[str] = mapped_column(Text, default='')
    changed_at: Mapped[datetime] = mapped_column(DateTime, default=now)

class Job(Base):
    __tablename__ = 'jobs'
    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey('orders.id'), unique=True)
    state: Mapped[str] = mapped_column(String(25), default='queued', index=True)
    tries: Mapped[int] = mapped_column(Integer, default=0)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

engine = create_engine(config.DATABASE_URL, connect_args={'check_same_thread': False, 'timeout': 30} if config.DATABASE_URL.startswith('sqlite') else {}, pool_pre_ping=True)

@event.listens_for(engine, 'connect')
def configure_sqlite(dbapi_connection, connection_record):
    if config.DATABASE_URL.startswith('sqlite'):
        cur = dbapi_connection.cursor()
        cur.execute('PRAGMA journal_mode=WAL')
        cur.execute('PRAGMA foreign_keys=ON')
        cur.execute('PRAGMA busy_timeout=30000')
        cur.close()

SessionLocal = sessionmaker(engine, expire_on_commit=False)

def initialize():
    config.ensure_dirs()
    Base.metadata.create_all(engine)
    # Additive upgrade for databases created by v1 (before the calibrated flag).
    # This is intentionally narrowly scoped; back up the data directory first.
    if config.DATABASE_URL.startswith('sqlite'):
        with engine.begin() as connection:
            columns = {row[1] for row in connection.exec_driver_sql('PRAGMA table_info(templates)').all()}
            if 'calibrated' not in columns:
                connection.exec_driver_sql('ALTER TABLE templates ADD COLUMN calibrated BOOLEAN NOT NULL DEFAULT 0')
    from .template import DEFAULT_REGIONS
    import json
    with SessionLocal.begin() as db:
        if not db.query(Template).first():
            db.add(Template(name='Standard form — calibrate before bulk processing', regions_json=json.dumps(DEFAULT_REGIONS), calibrated=False))
