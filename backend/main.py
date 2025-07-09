from fastapi import FastAPI, Request, Depends
from fastapi.responses import RedirectResponse, JSONResponse
import uvicorn
import requests
import urllib.parse
from config import config
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

app = FastAPI()

# 使用已驗證有效的方法
def create_oauth_url(scopes: list):
    """建立 OAuth URL"""
    base_url = "https://accounts.google.com/o/oauth2/auth"
    
    # 將 scopes 轉換為空格分隔的字串
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
    """將授權碼交換為 access token"""
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
        "message": "🎉 Interview Assistant - Gmail OAuth 應用",
        "status": "ready",
        "available_endpoints": [
            "/login - 完整 Gmail 權限登入",
            "/login-readonly - 只讀權限登入", 
            "/test-gmail - 測試 Gmail API 呼叫",
            "/user-info - 取得用戶資訊"
        ]
    }

@app.get("/login")
async def login():
    """完整的 Gmail 權限登入"""
    
    # 使用兩個 Gmail 權限
    scopes = [
        "https://www.googleapis.com/auth/gmail.readonly",
        "https://www.googleapis.com/auth/gmail.send",
        "https://www.googleapis.com/auth/userinfo.email",
        "https://www.googleapis.com/auth/userinfo.profile"
    ]
    
    auth_url = create_oauth_url(scopes)
    return RedirectResponse(url=auth_url)

@app.get("/login-readonly")
async def login_readonly():
    """只讀權限登入"""
    
    scopes = [
        "https://www.googleapis.com/auth/gmail.readonly",
        "https://www.googleapis.com/auth/userinfo.email"
    ]
    
    auth_url = create_oauth_url(scopes)
    return RedirectResponse(url=auth_url)

@app.get("/auth/callback")
async def auth_callback(request: Request):
    """處理 OAuth 回調"""
    
    params = dict(request.query_params)
    
    # 檢查錯誤
    if 'error' in params:
        return JSONResponse({
            "success": False,
            "error": params.get('error'),
            "error_description": params.get('error_description'),
            "full_params": params
        }, status_code=400)
    
    # 檢查授權碼
    code = params.get('code')
    if not code:
        return JSONResponse({
            "success": False,
            "error": "missing_code",
            "message": "沒有收到授權碼"
        }, status_code=400)
    
    # 交換 token
    try:
        token_data = exchange_code_for_token(code)
        
        # 儲存到 session 或資料庫（這裡先返回給前端）
        return {
            "success": True,
            "message": "🎉 Gmail OAuth 認證成功！",
            "token_info": {
                "has_access_token": "access_token" in token_data,
                "has_refresh_token": "refresh_token" in token_data,
                "expires_in": token_data.get("expires_in"),
                "granted_scopes": token_data.get("scope"),
                "token_type": token_data.get("token_type")
            },
            "next_steps": [
                "✅ 認證完成",
                "📧 可以存取 Gmail API",
                "🔧 嘗試 /test-gmail 來測試 API 呼叫"
            ],
            # 實際應用中不應該返回 token，這裡只是測試用
            "access_token": token_data.get("access_token"),
            "refresh_token": token_data.get("refresh_token")
        }
        
    except Exception as e:
        return JSONResponse({
            "success": False,
            "error": "token_exchange_failed",
            "message": f"Token 交換失敗: {str(e)}"
        }, status_code=500)

@app.get("/test-gmail")
async def test_gmail(access_token: str = None):
    """測試 Gmail API 呼叫"""
    
    if not access_token:
        return {
            "error": "需要 access_token 參數",
            "message": "請先完成 OAuth 認證，然後提供 access_token",
            "example": "/test-gmail?access_token=your_token_here"
        }
    
    try:
        # 建立 credentials
        credentials = Credentials(token=access_token)
        
        # 建立 Gmail 服務
        service = build('gmail', 'v1', credentials=credentials)
        
        # 測試取得用戶資料
        profile = service.users().getProfile(userId='me').execute()
        
        # 測試取得信件列表（最多 5 封）
        messages = service.users().messages().list(userId='me', maxResults=5).execute()
        
        return {
            "success": True,
            "message": "✅ Gmail API 測試成功！",
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
            "message": f"Gmail API 呼叫失敗: {str(e)}"
        }, status_code=500)

@app.get("/show-last-token")
async def show_last_token():
    """顯示最後一次認證的 token - 僅用於測試"""
    return {
        "message": "請重新進行 OAuth 認證以獲取新的 token",
        "auth_url": "/login"
    }

@app.get("/user-info")
async def get_user_info(access_token: str = None):
    """取得用戶基本資訊"""
    
    if not access_token:
        return {
            "error": "需要 access_token 參數",
            "example": "/user-info?access_token=your_token_here"
        }
    
    try:
        # 使用 Google userinfo API
        response = requests.get(
            "https://www.googleapis.com/oauth2/v2/userinfo",
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=10
        )
        
        if response.status_code == 200:
            user_data = response.json()
            return {
                "success": True,
                "user": {
                    "id": user_data.get('id'),
                    "email": user_data.get('email'),
                    "name": user_data.get('name'),
                    "picture": user_data.get('picture'),
                    "verified_email": user_data.get('verified_email')
                }
            }
        else:
            return JSONResponse({
                "success": False,
                "error": "userinfo_failed",
                "status_code": response.status_code
            }, status_code=500)
            
    except Exception as e:
        return JSONResponse({
            "success": False,
            "error": "userinfo_exception",
            "message": str(e)
        }, status_code=500)

if __name__ == "__main__":
    print("🚀 啟動完整的 Gmail OAuth 應用...")
    print("🔗 測試網址:")
    print("  - 首頁: http://localhost:8000")
    print("  - 🔐 完整登入: http://localhost:8000/login")
    print("  - 📖 只讀登入: http://localhost:8000/login-readonly")
    print("  - 📧 測試 Gmail API: http://localhost:8000/test-gmail?access_token=YOUR_TOKEN")
    print("  - 👤 用戶資訊: http://localhost:8000/user-info?access_token=YOUR_TOKEN")
    
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)