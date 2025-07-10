from fastapi import FastAPI, Request, Depends, HTTPException
from fastapi.responses import RedirectResponse, JSONResponse
from sqlalchemy.orm import Session
import uvicorn
import requests
import urllib.parse
from datetime import datetime, timedelta
from config import config
from models import create_tables, get_db, User, Email, InterviewInvitation, DraftReply
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
            "gmail": ["/test-gmail", "/user-info"],
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
    return RedirectResponse(url=auth_url)

@app.get("/auth/callback")
async def auth_callback(request: Request, db: Session = Depends(get_db)):
    params = dict(request.query_params)
    
    if 'error' in params:
        return JSONResponse({
            "success": False,
            "error": params.get('error'),
            "error_description": params.get('error_description')
        }, status_code=400)
    
    code = params.get('code')
    if not code:
        return JSONResponse({
            "success": False,
            "error": "missing_code",
            "message": "No authorization code received"
        }, status_code=400)
    
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
        
        return {
            "success": True,
            "message": "Authentication successful",
            "user": {
                "id": user.id,
                "email": user.email,
                "name": user.name
            },
            "token_info": {
                "expires_in": token_data.get("expires_in"),
                "granted_scopes": token_data.get("scope")
            }
        }
        
    except Exception as e:
        return JSONResponse({
            "success": False,
            "error": "authentication_failed",
            "message": str(e)
        }, status_code=500)

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

if __name__ == "__main__":
    print("Starting Interview Assistant API...")
    print("Test URLs:")
    print("  - Home: http://localhost:8000")
    print("  - Login: http://localhost:8000/login")
    print("  - Test DB: http://localhost:8000/test-db")
    print("  - Create Test User: http://localhost:8000/test-user")
    print("  - List Users: http://localhost:8000/users")
    
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)