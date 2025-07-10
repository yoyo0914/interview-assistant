from fastapi import FastAPI, Request, Depends, HTTPException
from fastapi.responses import RedirectResponse, JSONResponse
from sqlalchemy.orm import Session
import uvicorn
import requests
import urllib.parse
from datetime import datetime, timedelta
from config import config
from models import User, Email, InterviewInvitation, DraftReply
from database import create_tables, get_db
from gmail_service import get_gmail_service
from openai_service import get_openai_service
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

app = FastAPI()

# Initialize database
create_tables()

def create_oauth_url(scopes: list):
    base_url = "https://accounts.google.com/o/oauth2/auth"
    scope_string = " ".join(scopes)
    
    params = {
        "client_id": config.GOOGLE_CLIENT_ID,
        "redirect_uri": config.GOOGLE_REDIRECT_URI,
        "scope": scope_string,
        "response_type": "code",
        "access_type": "offline",
        "prompt": "consent",
        "include_granted_scopes": "true"
    }
    
    query_string = urllib.parse.urlencode(params)
    return f"{base_url}?{query_string}"

def exchange_code_for_token(code: str):
    token_url = "https://oauth2.googleapis.com/token"
    data = {
        "client_id": config.GOOGLE_CLIENT_ID,
        "client_secret": config.GOOGLE_CLIENT_SECRET,
        "code": code,
        "grant_type": "authorization_code",
        "redirect_uri": config.GOOGLE_REDIRECT_URI
    }
    
    response = requests.post(token_url, data=data, timeout=10)
    
    if response.status_code == 200:
        return response.json()
    else:
        raise Exception(f"Token exchange failed: {response.status_code} - {response.text}")

@app.get("/")
async def root():
    return {
        "message": "Interview Assistant API",
        "status": "ready",
        "endpoints": {
            "auth": ["/login", "/auth/callback"],
            "gmail": ["/test-gmail", "/sync-emails/{user_id}", "/emails/{user_id}", "/gmail-status/{user_id}"],
            "ai": ["/analyze-email/{email_id}", "/extract-info/{email_id}", "/generate-reply/{email_id}"],
            "database": ["/test-db", "/test-user", "/users"]
        }
    }

@app.get("/login")
async def login():
    scopes = [
        "https://www.googleapis.com/auth/gmail.readonly",
        "https://www.googleapis.com/auth/gmail.send",
        "https://www.googleapis.com/auth/userinfo.email",
        "https://www.googleapis.com/auth/userinfo.profile"
    ]
    
    auth_url = create_oauth_url(scopes)
    
    # 直接重定向到 Google OAuth
    return RedirectResponse(url=auth_url)

@app.get("/auth/callback")
async def auth_callback(request: Request, db: Session = Depends(get_db)):
    params = dict(request.query_params)
    
    if 'error' in params:
        # 錯誤時重定向到登入頁面
        error_msg = params.get('error_description', params.get('error'))
        return RedirectResponse(
            url=f"http://localhost:8080/login.html?error={error_msg}",
            status_code=302
        )
    
    code = params.get('code')
    if not code:
        return RedirectResponse(
            url="http://localhost:8080/login.html?error=missing_code",
            status_code=302
        )
    
    try:
        token_data = exchange_code_for_token(code)
        
        # Get user info
        user_response = requests.get(
            "https://www.googleapis.com/oauth2/v2/userinfo",
            headers={"Authorization": f"Bearer {token_data['access_token']}"},
            timeout=10
        )
        
        if user_response.status_code != 200:
            raise Exception("Failed to get user info")
        
        user_info = user_response.json()
        
        # Save or update user in database
        user = db.query(User).filter(User.google_id == user_info['id']).first()
        
        if user:
            # Update existing user
            user.access_token = token_data['access_token']
            user.refresh_token = token_data.get('refresh_token')
            user.token_expires_at = datetime.utcnow() + timedelta(seconds=token_data.get('expires_in', 3600))
            user.updated_at = datetime.utcnow()
        else:
            # Create new user
            user = User(
                google_id=user_info['id'],
                email=user_info['email'],
                name=user_info.get('name'),
                access_token=token_data['access_token'],
                refresh_token=token_data.get('refresh_token'),
                token_expires_at=datetime.utcnow() + timedelta(seconds=token_data.get('expires_in', 3600))
            )
            db.add(user)
        
        db.commit()
        
        # 成功後重定向到前端 dashboard
        return RedirectResponse(
            url=f"http://localhost:8080/dashboard.html?success=true&user_id={user.id}",
            status_code=302
        )
        
    except Exception as e:
        return RedirectResponse(
            url=f"http://localhost:8080/login.html?error=authentication_failed",
            status_code=302
        )

@app.get("/test-gmail")
async def test_gmail(access_token: str = None):
    if not access_token:
        return {
            "error": "access_token parameter required",
            "example": "/test-gmail?access_token=your_token_here"
        }
    
    try:
        credentials = Credentials(token=access_token)
        service = build('gmail', 'v1', credentials=credentials)
        
        profile = service.users().getProfile(userId='me').execute()
        messages = service.users().messages().list(userId='me', maxResults=5).execute()
        
        return {
            "success": True,
            "profile": {
                "email": profile.get('emailAddress'),
                "total_messages": profile.get('messagesTotal'),
                "total_threads": profile.get('threadsTotal')
            },
            "recent_messages": {
                "count": len(messages.get('messages', [])),
                "message_ids": [msg['id'] for msg in messages.get('messages', [])[:3]]
            }
        }
        
    except Exception as e:
        return JSONResponse({
            "success": False,
            "error": "gmail_api_failed",
            "message": str(e)
        }, status_code=500)

@app.get("/test-db")
async def test_database(db: Session = Depends(get_db)):
    try:
        # Test database connection
        user_count = db.query(User).count()
        email_count = db.query(Email).count()
        
        return {
            "success": True,
            "database": "connected",
            "stats": {
                "users": user_count,
                "emails": email_count
            }
        }
    except Exception as e:
        return JSONResponse({
            "success": False,
            "error": "database_error",
            "message": str(e)
        }, status_code=500)

@app.post("/test-user")
async def create_test_user(db: Session = Depends(get_db)):
    try:
        test_user = User(
            google_id="test_123",
            email="test@example.com",
            name="Test User",
            access_token="test_token",
            refresh_token="test_refresh"
        )
        
        db.add(test_user)
        db.commit()
        db.refresh(test_user)
        
        return {
            "success": True,
            "user": {
                "id": test_user.id,
                "email": test_user.email,
                "name": test_user.name,
                "created_at": test_user.created_at
            }
        }
    except Exception as e:
        return JSONResponse({
            "success": False,
            "error": "user_creation_failed",
            "message": str(e)
        }, status_code=500)

@app.get("/users")
async def get_users(db: Session = Depends(get_db)):
    try:
        users = db.query(User).all()
        return {
            "success": True,
            "users": [
                {
                    "id": user.id,
                    "email": user.email,
                    "name": user.name,
                    "created_at": user.created_at
                }
                for user in users
            ]
        }
    except Exception as e:
        return JSONResponse({
            "success": False,
            "error": "users_fetch_failed",
            "message": str(e)
        }, status_code=500)

@app.get("/users/{user_id}")
async def get_user(user_id: int, db: Session = Depends(get_db)):
    try:
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
                "email_count": len(user.emails)
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        return JSONResponse({
            "success": False,
            "error": "user_fetch_failed",
            "message": str(e)
        }, status_code=500)

@app.post("/sync-emails/{user_id}")
async def sync_emails(user_id: int, max_results: int = 20):
    try:
        gmail_service = get_gmail_service(user_id)
        synced_count = gmail_service.sync_recent_emails(max_results)
        
        return {
            "success": True,
            "message": f"Synced {synced_count} emails",
            "synced_count": synced_count
        }
    except Exception as e:
        return JSONResponse({
            "success": False,
            "error": "sync_failed",
            "message": str(e)
        }, status_code=500)

@app.get("/emails/{user_id}")
async def get_user_emails(user_id: int, limit: int = 10, db: Session = Depends(get_db)):
    try:
        emails = db.query(Email).filter(
            Email.user_id == user_id
        ).order_by(Email.received_at.desc()).limit(limit).all()
        
        return {
            "success": True,
            "emails": [
                {
                    "id": email.id,
                    "subject": email.subject,
                    "sender": email.sender,
                    "received_at": email.received_at,
                    "is_interview_related": email.is_interview_related,
                    "body_preview": email.body_text[:200] + "..." if email.body_text and len(email.body_text) > 200 else email.body_text
                }
                for email in emails
            ]
        }
    except Exception as e:
        return JSONResponse({
            "success": False,
            "error": "emails_fetch_failed",
            "message": str(e)
        }, status_code=500)

@app.get("/gmail-status/{user_id}")
async def gmail_status(user_id: int, db: Session = Depends(get_db)):
    try:
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        # 檢查 token 是否存在
        has_token = bool(user.access_token)
        token_expired = False
        
        if user.token_expires_at:
            token_expired = datetime.utcnow() > user.token_expires_at
        
        # 統計郵件數量
        email_count = db.query(Email).filter(Email.user_id == user_id).count()
        interview_count = db.query(Email).filter(
            Email.user_id == user_id,
            Email.is_interview_related == True
        ).count()
        
        return {
            "success": True,
            "user_id": user_id,
            "email": user.email,
            "gmail_connected": has_token and not token_expired,
            "token_expired": token_expired,
            "stats": {
                "total_emails": email_count,
                "interview_emails": interview_count
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        return JSONResponse({
            "success": False,
            "error": "status_check_failed",
            "message": str(e)
        }, status_code=500)

@app.post("/analyze-email/{email_id}")
async def analyze_email(email_id: int, db: Session = Depends(get_db)):
    try:
        email = db.query(Email).filter(Email.id == email_id).first()
        if not email:
            raise HTTPException(status_code=404, detail="Email not found")
        
        openai_service = get_openai_service()
        is_interview, confidence = openai_service.is_interview_email(
            email.subject or "", 
            email.body_text or ""
        )
        
        # 更新資料庫
        email.is_interview_related = is_interview
        db.commit()
        
        return {
            "success": True,
            "email_id": email_id,
            "subject": email.subject,
            "is_interview": is_interview,
            "confidence": confidence,
            "message": "分析完成並已更新資料庫"
        }
    except HTTPException:
        raise
    except Exception as e:
        return JSONResponse({
            "success": False,
            "error": "analysis_failed",
            "message": str(e)
        }, status_code=500)

@app.post("/extract-info/{email_id}")
async def extract_interview_info(email_id: int, db: Session = Depends(get_db)):
    try:
        email = db.query(Email).filter(Email.id == email_id).first()
        if not email:
            raise HTTPException(status_code=404, detail="Email not found")
        
        openai_service = get_openai_service()
        interview_info = openai_service.extract_interview_info(
            email.subject or "",
            email.body_text or ""
        )
        
        if not interview_info:
            return JSONResponse({
                "success": False,
                "error": "extraction_failed",
                "message": "無法提取面試資訊"
            }, status_code=400)
        
        # 儲存到資料庫
        existing_invitation = db.query(InterviewInvitation).filter(
            InterviewInvitation.email_id == email_id
        ).first()
        
        if existing_invitation:
            # 更新現有記錄
            for key, value in interview_info.items():
                if key != "confidence_score" and value is not None:
                    setattr(existing_invitation, key, value)
            existing_invitation.confidence_score = interview_info.get("confidence_score", 0)
            invitation = existing_invitation
        else:
            # 建立新記錄
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
                confidence_score=interview_info.get("confidence_score", 0)
            )
            db.add(invitation)
        
        db.commit()
        db.refresh(invitation)
        
        return {
            "success": True,
            "email_id": email_id,
            "invitation_id": invitation.id,
            "extracted_info": interview_info
        }
    except HTTPException:
        raise
    except Exception as e:
        return JSONResponse({
            "success": False,
            "error": "extraction_failed",
            "message": str(e)
        }, status_code=500)

@app.post("/generate-reply/{email_id}")
async def generate_reply(email_id: int, tone: str = "professional", db: Session = Depends(get_db)):
    try:
        # 取得郵件和面試資訊
        email = db.query(Email).filter(Email.id == email_id).first()
        if not email:
            raise HTTPException(status_code=404, detail="Email not found")
        
        invitation = db.query(InterviewInvitation).filter(
            InterviewInvitation.email_id == email_id
        ).first()
        
        if not invitation:
            return JSONResponse({
                "success": False,
                "error": "no_interview_info",
                "message": "請先提取面試資訊"
            }, status_code=400)
        
        # 準備面試資訊
        interview_info = {
            "company_name": invitation.company_name,
            "position": invitation.position,
            "interview_date": str(invitation.interview_date) if invitation.interview_date else None,
            "interview_time": invitation.interview_time,
            "interview_location": invitation.interview_location,
            "interview_type": invitation.interview_type,
            "interviewer_name": invitation.interviewer_name
        }
        
        # 生成回信
        openai_service = get_openai_service()
        reply_body = openai_service.generate_reply(interview_info, tone)
        reply_subject = openai_service.generate_reply_subject(email.subject or "")
        
        if not reply_body:
            return JSONResponse({
                "success": False,
                "error": "generation_failed",
                "message": "無法生成回信"
            }, status_code=400)
        
        # 儲存草稿
        draft = DraftReply(
            interview_invitation_id=invitation.id,
            subject=reply_subject,
            body=reply_body,
            tone=tone
        )
        
        db.add(draft)
        db.commit()
        db.refresh(draft)
        
        return {
            "success": True,
            "email_id": email_id,
            "draft_id": draft.id,
            "subject": reply_subject,
            "body": reply_body,
            "tone": tone
        }
    except HTTPException:
        raise
    except Exception as e:
        return JSONResponse({
            "success": False,
            "error": "generation_failed",
            "message": str(e)
        }, status_code=500)

if __name__ == "__main__":
    print("Starting Interview Assistant API...")
    print("Test URLs:")
    print("  - Home: http://localhost:8000")
    print("  - Login: http://localhost:8000/login")
    print("  - Test DB: http://localhost:8000/test-db")
    print("  - Create Test User: http://localhost:8000/test-user")
    print("  - List Users: http://localhost:8000/users")
    print("Gmail endpoints (需要先認證):")
    print("  - Sync Emails: POST http://localhost:8000/sync-emails/1")
    print("  - View Emails: http://localhost:8000/emails/1")
    print("  - Gmail Status: http://localhost:8000/gmail-status/1")
    
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)