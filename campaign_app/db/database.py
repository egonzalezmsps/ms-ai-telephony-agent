import os
from contextlib import contextmanager
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv

load_dotenv()

_engine = None


def get_engine():
    global _engine
    if _engine is None:
        url = os.environ.get("DATABASE_URL", "")
        if not url:
            raise ValueError("DATABASE_URL not set in .env")
        _engine = create_engine(url, pool_pre_ping=True)
    return _engine


def init_db():
    from db.models import Base
    Base.metadata.create_all(get_engine())


@contextmanager
def get_db():
    Session = sessionmaker(bind=get_engine(), expire_on_commit=False)
    session = Session()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
