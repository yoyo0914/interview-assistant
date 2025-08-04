from fastapi import FastAPI, Request, Depends, HTTPException
from fastapi.responses import RedirectResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
import uvicorn
import requests
import urllib.parse
from datetime import datetime, timedelta, timezone
from config import config
from models import User, Email, InterviewInvitation, DraftReply
from database import create_tables, get_db
from gmail_service import get_gmail_service
from openai_service import get_openai_service
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
import logging
import os

logger = logging.getLogger(__name__)

app = FastAPI()

# CORS 設定
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Cloud Run 需要更寬鬆的設定
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 服務前端靜態檔案
frontend_path = "/app/frontend"
if os.path.exists(frontend_path):
    app.mount("/static", StaticFiles(directory=frontend_path), name="static")

# 初始化資料庫
create_tables()


def create_oauth_url(scopes: list):
    base_url = "https://accounts.google.com/o/oauth2/auth"
    params = {
        "client_id": config.GOOGLE_CLIENT_ID,
        "redirect_uri": config.GOOGLE_REDIRECT_URI,
        "scope": " ".join(scopes),
        "response_type": "code",
        "access_type": "offline",
        "prompt": "consent",
        "include_granted_scopes": "true",
    }
    return f"{base_url}?{urllib.parse.urlencode(params)}"


def exchange_code_for_token(code: str):
    response = requests.post(
        "https://oauth2.googleapis.com/token",
        data={
            "client_id": config.GOOGLE_CLIENT_ID,
            "client_secret": config.GOOGLE_CLIENT_SECRET,
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": config.GOOGLE_REDIRECT_URI,
        },
        timeout=10,
    )

    if response.status_code == 200:
        return response.json()
    raise Exception(f"Token exchange failed: {response.status_code}")


@app.get("/")
async def root():
    return {"message": "Interview Assistant API", "status": "ready"}


# 重定向根路徑到前端
@app.get("/login")
async def login():
    scopes = [
        "https://www.googleapis.com/auth/gmail.readonly",
        "https://www.googleapis.com/auth/gmail.send",
        "https://www.googleapis.com/auth/userinfo.email",
        "https://www.googleapis.com/auth/userinfo.profile",
    ]
    return RedirectResponse(url=create_oauth_url(scopes))


@app.get("/auth/callback")
async def auth_callback(request: Request, db: Session = Depends(get_db)):
    params = dict(request.query_params)

    if "error" in params:
        return RedirectResponse(f"/static/login.html?error={params.get('error')}")

    code = params.get("code")
    if not code:
        return RedirectResponse("/static/login.html?error=missing_code")

    token_data = exchange_code_for_token(code)
    user_response = requests.get(
        "https://www.googleapis.com/oauth2/v2/userinfo",
        headers={"Authorization": f"Bearer {token_data['access_token']}"},
        timeout=10,
    )
    user_info = user_response.json()

    user = db.query(User).filter(User.google_id == user_info["id"]).first()

    if user:
        user.access_token = token_data["access_token"]
        user.refresh_token = token_data.get("refresh_token")
        user.token_expires_at = datetime.now(timezone.utc) + timedelta(
            seconds=token_data.get("expires_in", 3600)
        )
        user.updated_at = datetime.now(timezone.utc)
    else:
        user = User(
            google_id=user_info["id"],
            email=user_info["email"],
            name=user_info.get("name"),
            access_token=token_data["access_token"],
            refresh_token=token_data.get("refresh_token"),
            token_expires_at=datetime.now(timezone.utc)
            + timedelta(seconds=token_data.get("expires_in", 3600)),
        )
        db.add(user)

    db.commit()
    return RedirectResponse(f"/static/dashboard.html?success=true&user_id={user.id}")


@app.get("/test-db")
async def test_database(db: Session = Depends(get_db)):
    user_count = db.query(User).count()
    email_count = db.query(Email).count()
    return {"success": True, "stats": {"users": user_count, "emails": email_count}}


@app.get("/users")
async def get_users(db: Session = Depends(get_db)):
    users = db.query(User).all()
    return {
        "success": True,
        "users": [{"id": u.id, "email": u.email, "name": u.name} for u in users],
    }


@app.get("/users/{user_id}")
async def get_user(user_id: int, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    return {
        "success": True,
        "user": {
            "id": user.id,
            "email": user.email,
            "name": user.name,
            "created_at": user.created_at,
            "email_count": len(user.emails),
        },
    }


@app.post("/sync-emails/{user_id}")
async def sync_emails(
    user_id: int, max_results: int = 50, db: Session = Depends(get_db)
):
    # 檢查用戶是否存在
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    gmail_service = get_gmail_service(user_id)
    synced_count = gmail_service.sync_recent_emails(max_results)

    # 更新同步資訊
    sync_type = "首次同步" if not user.last_sync_at else "增量同步"

    return {
        "success": True,
        "synced_count": synced_count,
        "sync_type": sync_type,
        "message": f"{sync_type}完成，新增 {synced_count} 封郵件",
    }


@app.get("/emails/{user_id}")
async def get_user_emails(user_id: int, limit: int = 10, db: Session = Depends(get_db)):
    emails = (
        db.query(Email)
        .filter(Email.user_id == user_id)
        .order_by(Email.received_at.desc())
        .limit(limit)
        .all()
    )

    return {
        "success": True,
        "emails": [
            {
                "id": email.id,
                "subject": email.subject,
                "sender": email.sender,
                "received_at": email.received_at,
                "is_interview_related": email.is_interview_related,
                "body_preview": email.body_text[:200] + "..."
                if email.body_text and len(email.body_text) > 200
                else email.body_text,
            }
            for email in emails
        ],
    }


@app.get("/gmail-status/{user_id}")
async def gmail_status(user_id: int, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    has_token = bool(user.access_token)
    token_expired = False

    if user.token_expires_at:
        # 修復時間比較問題
        if user.token_expires_at.tzinfo is None:
            token_expires_utc = user.token_expires_at.replace(tzinfo=timezone.utc)
        else:
            token_expires_utc = user.token_expires_at
        token_expired = datetime.now(timezone.utc) > token_expires_utc

    email_count = db.query(Email).filter(Email.user_id == user_id).count()
    interview_count = (
        db.query(Email)
        .filter(Email.user_id == user_id, Email.is_interview_related == True)
        .count()
    )

    # 新增同步資訊
    sync_info = {
        "last_sync_at": user.last_sync_at.isoformat() if user.last_sync_at else None,
        "need_initial_sync": user.last_sync_at is None,
        "current_email_count": email_count,
    }

    return {
        "success": True,
        "user_id": user_id,
        "email": user.email,
        "gmail_connected": has_token and not token_expired,
        "token_expired": token_expired,
        "stats": {"total_emails": email_count, "interview_emails": interview_count},
        "sync_info": sync_info,
    }


@app.post("/analyze-email/{email_id}")
async def analyze_email(email_id: int, db: Session = Depends(get_db)):
    email = db.query(Email).filter(Email.id == email_id).first()
    if not email:
        raise HTTPException(status_code=404, detail="Email not found")

    openai_service = get_openai_service()
    is_interview, confidence = openai_service.is_interview_email(
        email.subject or "", email.body_text or ""
    )

    email.is_interview_related = is_interview
    db.commit()

    return {
        "success": True,
        "email_id": email_id,
        "subject": email.subject,
        "is_interview": is_interview,
        "confidence": confidence,
    }


@app.post("/extract-info/{email_id}")
async def extract_interview_info(email_id: int, db: Session = Depends(get_db)):
    email = db.query(Email).filter(Email.id == email_id).first()
    if not email:
        raise HTTPException(status_code=404, detail="Email not found")

    openai_service = get_openai_service()
    interview_info = openai_service.extract_interview_info(
        email.subject or "", email.body_text or ""
    )

    if not interview_info:
        return JSONResponse(
            {"success": False, "error": "extraction_failed"}, status_code=400
        )

    existing_invitation = (
        db.query(InterviewInvitation)
        .filter(InterviewInvitation.email_id == email_id)
        .first()
    )

    if existing_invitation:
        for key, value in interview_info.items():
            if key != "confidence_score" and value is not None:
                setattr(existing_invitation, key, value)
        existing_invitation.confidence_score = interview_info.get("confidence_score", 0)
        invitation = existing_invitation
    else:
        invitation = InterviewInvitation(
            email_id=email_id,
            company_name=interview_info.get("company_name"),
            position=interview_info.get("position"),
            interview_time=interview_info.get("interview_time"),
            interview_location=interview_info.get("interview_location"),
            interview_type=interview_info.get("interview_type"),
            interviewer_name=interview_info.get("interviewer_name"),
            interviewer_email=interview_info.get("interviewer_email"),
            additional_info=interview_info.get("additional_info"),
            confidence_score=interview_info.get("confidence_score", 0),
        )
        db.add(invitation)

    db.commit()
    return {"success": True, "email_id": email_id, "extracted_info": interview_info}


@app.post("/generate-reply/{email_id}")
async def generate_reply(
    email_id: int, tone: str = "professional", db: Session = Depends(get_db)
):
    email = db.query(Email).filter(Email.id == email_id).first()
    if not email:
        raise HTTPException(status_code=404, detail="Email not found")

    # 智能檢查：如果還沒有面試資訊，自動提取
    invitation = (
        db.query(InterviewInvitation)
        .filter(InterviewInvitation.email_id == email_id)
        .first()
    )

    if not invitation:
        # 先分析是否為面試邀請
        openai_service = get_openai_service()
        is_interview, confidence = openai_service.is_interview_email(
            email.subject or "", email.body_text or ""
        )

        if not is_interview:
            return JSONResponse(
                {
                    "success": False,
                    "error": "not_interview",
                    "message": "這不是面試邀請郵件，無法生成回信",
                },
                status_code=400,
            )

        # 更新郵件狀態
        email.is_interview_related = True

        # 自動提取面試資訊
        interview_info = openai_service.extract_interview_info(
            email.subject or "", email.body_text or ""
        )

        if not interview_info:
            return JSONResponse(
                {
                    "success": False,
                    "error": "extraction_failed",
                    "message": "無法提取面試資訊，請手動分析郵件",
                },
                status_code=400,
            )

        # 建立面試邀請記錄
        invitation = InterviewInvitation(
            email_id=email_id,
            company_name=interview_info.get("company_name"),
            position=interview_info.get("position"),
            interview_time=interview_info.get("interview_time"),
            interview_location=interview_info.get("interview_location"),
            interview_type=interview_info.get("interview_type"),
            interviewer_name=interview_info.get("interviewer_name"),
            interviewer_email=interview_info.get("interviewer_email"),
            additional_info=interview_info.get("additional_info"),
            confidence_score=interview_info.get("confidence_score", 0),
        )
        db.add(invitation)
        db.commit()
        db.refresh(invitation)

    # 準備面試資訊
    interview_info = {
        "company_name": invitation.company_name,
        "position": invitation.position,
        "interview_date": str(invitation.interview_date)
        if invitation.interview_date
        else None,
        "interview_time": invitation.interview_time,
        "interview_location": invitation.interview_location,
        "interview_type": invitation.interview_type,
        "interviewer_name": invitation.interviewer_name,
    }

    # 生成回信
    openai_service = get_openai_service()
    reply_body = openai_service.generate_reply(interview_info, tone)
    reply_subject = openai_service.generate_reply_subject(email.subject or "")

    if not reply_body:
        return JSONResponse(
            {"success": False, "error": "generation_failed", "message": "無法生成回信內容"},
            status_code=400,
        )

    # 儲存草稿
    draft = DraftReply(
        interview_invitation_id=invitation.id,
        subject=reply_subject,
        body=reply_body,
        tone=tone,
    )

    db.add(draft)
    db.commit()

    return {
        "success": True,
        "email_id": email_id,
        "subject": reply_subject,
        "body": reply_body,
        "tone": tone,
        "auto_extracted": not invitation
        or invitation.created_at == invitation.created_at,
    }


if __name__ == "__main__":
    print("Starting Interview Assistant API...")
    print("前端: /static/login.html")
    print("後端: /")
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
