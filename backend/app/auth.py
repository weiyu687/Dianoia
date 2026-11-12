import hashlib
import os
import secrets
from collections import defaultdict, deque
from datetime import timedelta
from threading import Lock
from time import monotonic
from typing import Annotated, Literal

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from .db import database
from .models import Course, LoginSession, TeachingAssignment, User, now

router = APIRouter(prefix="/api/auth", tags=["authentication"])
DB = Annotated[Session, Depends(database)]
COOKIE = "dianoia_session"
SESSION_SECONDS = 8 * 60 * 60
SECURE_COOKIE = os.getenv("DIANOIA_SECURE_COOKIE", "false").lower() == "true"
passwords = PasswordHasher()
DUMMY_HASH = passwords.hash(secrets.token_urlsafe(24))
attempts: dict[str, deque] = defaultdict(deque)
attempt_lock = Lock()


def account_key(value):
    return value.strip().casefold()


def token_hash(value):
    return hashlib.sha256(value.encode()).hexdigest()


def throttle(key):
    current = monotonic()
    with attempt_lock:
        if len(attempts) >= 2048:
            for entry, history in list(attempts.items()):
                if not history or current - history[-1] >= 60:
                    del attempts[entry]
            if len(attempts) >= 2048 and key not in attempts:
                raise HTTPException(429, "请稍后重试")
        history = attempts[key]
        while history and current - history[0] >= 60:
            history.popleft()
        if len(history) >= 10:
            raise HTTPException(429, "登录尝试过多，请一分钟后再试")
        history.append(current)


def current_user(db: DB, session_token: Annotated[str | None, Cookie(alias=COOKIE)] = None):
    if not session_token:
        raise HTTPException(401, "请先登录")
    row = db.execute(
        select(User).join(LoginSession, LoginSession.user_id == User.id)
        .where(LoginSession.token_hash == token_hash(session_token), LoginSession.expires_at > now(), User.enabled)
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(401, "会话已过期，请重新登录")
    return row


CurrentUser = Annotated[User, Depends(current_user)]


def teacher(user: CurrentUser):
    if user.role != "teacher":
        raise HTTPException(403, "此操作仅对教师开放")
    return user


def administrator(user: CurrentUser):
    if user.role != "admin":
        raise HTTPException(403, "此操作仅对学校管理员开放")
    return user


Teacher = Annotated[User, Depends(teacher)]
Administrator = Annotated[User, Depends(administrator)]


def courses_for(db, user):
    return list(db.scalars(
        select(Course).join(TeachingAssignment, TeachingAssignment.course_id == Course.id)
        .where(TeachingAssignment.teacher_id == user.id).order_by(Course.name)
    ))


def course_access(db, user, course_id):
    if not db.get(TeachingAssignment, (user.id, course_id)):
        raise HTTPException(404, "课程不存在或未分配")


def profile(db, user):
    return {
        "id": user.id,
        "name": user.name,
        "role": user.role,
        "courses": [{"id": row.id, "name": row.name, "code": row.code} for row in courses_for(db, user)],
    }


class Credentials(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=256)
    role: Literal["teacher", "admin"]


@router.post("/login")
def login(data: Credentials, request: Request, response: Response, db: DB):
    throttle(request.client.host if request.client else "local")
    user = db.scalar(select(User).where(User.username == account_key(data.username)))
    try:
        passwords.verify(user.password_hash if user and user.enabled else DUMMY_HASH, data.password)
    except VerifyMismatchError:
        raise HTTPException(401, "账号、密码或登录入口有误") from None
    if not user or not user.enabled or user.role != data.role:
        raise HTTPException(401, "账号、密码或登录入口有误")

    if request.cookies.get(COOKIE):
        db.execute(delete(LoginSession).where(LoginSession.token_hash == token_hash(request.cookies[COOKIE])))
    db.execute(delete(LoginSession).where(LoginSession.expires_at <= now()))
    token = secrets.token_urlsafe(32)
    db.add(LoginSession(token_hash=token_hash(token), user_id=user.id, expires_at=now() + timedelta(seconds=SESSION_SECONDS)))
    db.commit()
    response.set_cookie(COOKIE, token, max_age=SESSION_SECONDS, httponly=True, secure=SECURE_COOKIE, samesite="lax", path="/api")
    return profile(db, user)


@router.get("/me")
def me(db: DB, user: CurrentUser):
    return profile(db, user)


@router.post("/logout", status_code=204)
def logout(request: Request, db: DB):
    if token := request.cookies.get(COOKIE):
        db.execute(delete(LoginSession).where(LoginSession.token_hash == token_hash(token)))
        db.commit()
    response = Response(status_code=204)
    response.delete_cookie(COOKIE, path="/api")
    return response
