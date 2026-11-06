import os
import random
import logging
from datetime import datetime, timedelta

import jwt
from fastapi import FastAPI, Query, Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime
from sqlalchemy.orm import sessionmaker, declarative_base
from faker import Faker
from prometheus_fastapi_instrumentator import Instrumentator

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(name)s: %(message)s')
logger = logging.getLogger('auth')

DATABASE_URL = os.environ['DATABASE_URL']

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()
fake = Faker()

SERVICES = ['auth-service', 'orders-service', 'payments-service', 'inventory-service']
ENDPOINTS = ['/login', '/orders', '/orders/{id}', '/pay', '/stock', '/health']
METHODS = ['GET', 'POST', 'PUT', 'DELETE']

# --- JWT-аутентификация (учебный пример, секрет и пароль намеренно упрощены) ---
JWT_SECRET = os.environ['JWT_SECRET']
JWT_ALGORITHM = 'HS256'
JWT_EXPIRE_MINUTES = 5

FAKE_USERS = {os.environ['DEMO_USERNAME']: os.environ['DEMO_PASSWORD']}

security = HTTPBearer()

class LoginRequest(BaseModel):
    username: str
    password: str

def create_access_token(username: str) -> str:
    payload = {
        'sub': username,
        'iat': datetime.utcnow(),
        'exp': datetime.utcnow() + timedelta(minutes=JWT_EXPIRE_MINUTES),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)

def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)) -> str:
    token = credentials.credentials
    logger.info('Проверка токена (первые 25 симв.): %s...', token[:25])
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        logger.warning('Токен просрочен')
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='Token expired')
    except jwt.InvalidTokenError as e:
        logger.warning('Токен недействителен: %s', e)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='Invalid token')
    username = payload.get('sub')
    logger.info('Токен валиден, claims=%s', payload)
    return username

class RequestEvent(Base):
    __tablename__ = 'request_events'
    id = Column(Integer, primary_key=True, index=True)
    service_name = Column(String, index=True)
    endpoint = Column(String)
    method = Column(String)
    status_code = Column(Integer)
    response_time_ms = Column(Float)
    user_id = Column(Integer)
    timestamp = Column(DateTime, index=True)

Base.metadata.create_all(bind=engine)

app = FastAPI(title='Microservice Data API')

Instrumentator().instrument(app).expose(app)

@app.get('/health')
def health():
    return {'status': 'ok'}

@app.post('/login')
def login(req: LoginRequest):
    logger.info('Попытка логина: username=%s', req.username)
    expected = FAKE_USERS.get(req.username)
    if expected is None or expected != req.password:
        logger.warning('Неверные учётные данные для username=%s', req.username)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='Invalid credentials')
    token = create_access_token(req.username)
    logger.info('Логин успешен, выдан токен для username=%s', req.username)
    return {'access_token': token, 'token_type': 'bearer', 'expires_in_minutes': JWT_EXPIRE_MINUTES}

@app.post('/seed')
def seed(count: int = Query(1000, ge=1, le=50000), user: str = Depends(get_current_user)):
    db = SessionLocal()
    now = datetime.utcnow()
    events = []
    for _ in range(count):
        ts = now - timedelta(hours=random.uniform(0, 48))
        is_anomaly_window = ts.hour == 14
        status_code = random.choices([200, 201, 400, 404, 500], weights=[80, 10, 4, 3, 3])[0]
        base_latency = random.uniform(20, 150)
        if is_anomaly_window:
            base_latency *= random.uniform(3, 8)
            status_code = random.choices([200, 500, 503], weights=[40, 35, 25])[0]
        events.append(RequestEvent(
            service_name=random.choice(SERVICES),
            endpoint=random.choice(ENDPOINTS),
            method=random.choice(METHODS),
            status_code=status_code,
            response_time_ms=round(base_latency, 2),
            user_id=random.randint(1, 500),
            timestamp=ts,
        ))
    db.bulk_save_objects(events)
    db.commit()
    db.close()
    return {'inserted': count}

@app.get('/events')
def list_events(limit: int = Query(100, le=1000), offset: int = 0, user: str = Depends(get_current_user)):
    db = SessionLocal()
    rows = db.query(RequestEvent).order_by(RequestEvent.timestamp.desc()).offset(offset).limit(limit).all()
    db.close()
    return [
        {
            'id': r.id, 'service_name': r.service_name, 'endpoint': r.endpoint,
            'method': r.method, 'status_code': r.status_code,
            'response_time_ms': r.response_time_ms, 'user_id': r.user_id,
            'timestamp': r.timestamp.isoformat(),
        }
        for r in rows
    ]

@app.get('/events/export')
def export_events(user: str = Depends(get_current_user)):
    db = SessionLocal()
    rows = db.query(RequestEvent).all()
    db.close()
    return [
        {
            'id': r.id, 'service_name': r.service_name, 'endpoint': r.endpoint,
            'method': r.method, 'status_code': r.status_code,
            'response_time_ms': r.response_time_ms, 'user_id': r.user_id,
            'timestamp': r.timestamp.isoformat(),
        }
        for r in rows
    ]

@app.get('/stats')
def stats(user: str = Depends(get_current_user)):
    db = SessionLocal()
    total = db.query(RequestEvent).count()
    db.close()
    return {'total_events': total}
