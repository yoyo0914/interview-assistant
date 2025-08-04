from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from sqlalchemy.orm import Session
from models import User, Email
from database import get_db_session
import base64
import email
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


class GmailService:
    def __init__(self, user_id: int):
        self.user_id = user_id
        self.service = None
        self._setup_service()

    def _setup_service(self):
        """設置 Gmail 服務"""
        # 🔧 修復：確保資料庫連線正確關閉
        db = get_db_session()
        try:
            user = db.query(User).filter(User.id == self.user_id).first()
            if not user or not user.access_token:
                raise ValueError(f"User {self.user_id} not found or no access token")

            from config import config

            credentials = Credentials(
                token=user.access_token,
                refresh_token=user.refresh_token,
                token_uri="https://oauth2.googleapis.com/token",
                client_id=config.GOOGLE_CLIENT_ID,
                client_secret=config.GOOGLE_CLIENT_SECRET,
            )

            self.service = build("gmail", "v1", credentials=credentials)
            logger.info(f"Gmail service setup for user {self.user_id}")

        except Exception as e:
            logger.error(f"Failed to setup Gmail service: {e}")
            raise
        finally:
            # 🔧 修復：確保連線關閉
            db.close()

    def get_messages(self, query: str = "", max_results: int = 10):
        """取得郵件列表"""
        try:
            results = (
                self.service.users()
                .messages()
                .list(userId="me", q=query, maxResults=max_results)
                .execute()
            )

            messages = results.get("messages", [])
            return messages

        except HttpError as e:
            logger.error(f"Failed to get messages: {e}")
            return []

    def get_message_details(self, message_id: str):
        """取得郵件詳細內容"""
        try:
            message = (
                self.service.users()
                .messages()
                .get(userId="me", id=message_id, format="full")
                .execute()
            )

            return self._parse_message(message)

        except HttpError as e:
            logger.error(f"Failed to get message {message_id}: {e}")
            return None

    def _parse_message(self, message):
        """解析郵件內容"""
        try:
            headers = message["payload"].get("headers", [])

            # 提取基本資訊
            subject = next((h["value"] for h in headers if h["name"] == "Subject"), "")
            sender = next((h["value"] for h in headers if h["name"] == "From"), "")
            recipient = next((h["value"] for h in headers if h["name"] == "To"), "")
            date_str = next((h["value"] for h in headers if h["name"] == "Date"), "")

            # 提取郵件內容
            body_text, body_html = self._extract_body(message["payload"])

            # 解析日期
            received_at = self._parse_date(date_str)

            return {
                "gmail_id": message["id"],
                "thread_id": message["threadId"],
                "subject": subject,
                "sender": sender,
                "recipient": recipient,
                "body_text": body_text,
                "body_html": body_html,
                "received_at": received_at,
            }

        except Exception as e:
            logger.error(f"Failed to parse message: {e}")
            return None

    def _extract_body(self, payload):
        """提取郵件內容"""
        body_text = ""
        body_html = ""

        try:
            # 處理 multipart 郵件
            if "parts" in payload:
                for part in payload["parts"]:
                    if part["mimeType"] == "text/plain" and "data" in part["body"]:
                        try:
                            body_text = base64.urlsafe_b64decode(
                                part["body"]["data"]
                            ).decode("utf-8", errors="ignore")
                        except:
                            body_text = base64.urlsafe_b64decode(
                                part["body"]["data"]
                            ).decode("latin-1", errors="ignore")
                    elif part["mimeType"] == "text/html" and "data" in part["body"]:
                        try:
                            body_html = base64.urlsafe_b64decode(
                                part["body"]["data"]
                            ).decode("utf-8", errors="ignore")
                        except:
                            body_html = base64.urlsafe_b64decode(
                                part["body"]["data"]
                            ).decode("latin-1", errors="ignore")
                    # 處理嵌套的 multipart
                    elif "parts" in part:
                        nested_text, nested_html = self._extract_body(part)
                        if nested_text:
                            body_text = nested_text
                        if nested_html:
                            body_html = nested_html

            # 處理單一 part 郵件
            elif payload["mimeType"] == "text/plain" and "data" in payload["body"]:
                try:
                    body_text = base64.urlsafe_b64decode(
                        payload["body"]["data"]
                    ).decode("utf-8", errors="ignore")
                except:
                    body_text = base64.urlsafe_b64decode(
                        payload["body"]["data"]
                    ).decode("latin-1", errors="ignore")
            elif payload["mimeType"] == "text/html" and "data" in payload["body"]:
                try:
                    body_html = base64.urlsafe_b64decode(
                        payload["body"]["data"]
                    ).decode("utf-8", errors="ignore")
                except:
                    body_html = base64.urlsafe_b64decode(
                        payload["body"]["data"]
                    ).decode("latin-1", errors="ignore")

        except Exception as e:
            logger.error(f"Failed to extract body: {e}")

        return body_text, body_html

    def _parse_date(self, date_str):
        """解析郵件日期"""
        try:
            # 使用 email 模組解析日期
            parsed_date = email.utils.parsedate_tz(date_str)
            if parsed_date:
                timestamp = email.utils.mktime_tz(parsed_date)
                return datetime.fromtimestamp(timestamp)
        except Exception as e:
            logger.error(f"Failed to parse date {date_str}: {e}")

        return datetime.utcnow()

    def save_message_to_db(self, message_data):
        """將郵件儲存到資料庫"""
        # 🔧 修復：確保資料庫連線正確關閉
        db = get_db_session()
        try:
            # 檢查是否已存在
            existing = (
                db.query(Email)
                .filter(Email.gmail_id == message_data["gmail_id"])
                .first()
            )

            if existing:
                logger.info(f"Message {message_data['gmail_id']} already exists")
                return existing

            # 建立新郵件記錄
            email_record = Email(
                user_id=self.user_id,
                gmail_id=message_data["gmail_id"],
                thread_id=message_data["thread_id"],
                subject=message_data["subject"],
                sender=message_data["sender"],
                recipient=message_data["recipient"],
                body_text=message_data["body_text"],
                body_html=message_data["body_html"],
                received_at=message_data["received_at"],
            )

            db.add(email_record)
            db.commit()
            db.refresh(email_record)

            logger.info(f"Saved message {message_data['gmail_id']} to database")
            return email_record

        except Exception as e:
            # 🔧 修復：發生錯誤時回滾
            db.rollback()
            logger.error(f"Failed to save message: {e}")
            return None
        finally:
            # 🔧 修復：確保連線關閉
            db.close()

    def sync_recent_emails(self, max_results: int = 50):
        """增量同步郵件到資料庫"""
        # 🔧 修復：確保資料庫連線正確關閉
        db = get_db_session()
        try:
            # 取得用戶最後同步時間
            user = db.query(User).filter(User.id == self.user_id).first()
            if not user:
                raise ValueError(f"User {self.user_id} not found")

            # 建構查詢條件
            if user.last_sync_at:
                # 增量同步：只取上次同步後的郵件
                after_date = user.last_sync_at.strftime("%Y/%m/%d")
                query = f"after:{after_date}"
                logger.info(f"增量同步：查詢 {after_date} 之後的郵件")
            else:
                # 首次同步：只取最近7天
                query = "newer_than:7d"
                logger.info("首次同步：查詢最近7天的郵件")

            # 取得郵件列表
            messages = self.get_messages(query=query, max_results=max_results)
            saved_count = 0

            if not messages:
                logger.info("沒有新郵件需要同步")
                # 更新同步時間即使沒有新郵件
                user.last_sync_at = datetime.utcnow()
                db.commit()
                return 0

            # 🔧 修復：暫時釋放連線，在處理郵件時重新獲取
            user.last_sync_at = datetime.utcnow()
            db.commit()
            db.close()

            # 處理郵件（每個郵件會獨立管理連線）
            for msg in messages:
                message_details = self.get_message_details(msg["id"])
                if message_details:
                    saved_email = self.save_message_to_db(message_details)
                    if saved_email:
                        saved_count += 1

            logger.info(f"增量同步完成：新增 {saved_count}/{len(messages)} 封郵件")
            return saved_count

        except Exception as e:
            logger.error(f"Failed to sync emails: {e}")
            # 🔧 修復：發生錯誤時回滾
            try:
                db.rollback()
            except:
                pass  # 如果連線已關閉，忽略回滾錯誤
            return 0
        finally:
            # 🔧 修復：確保連線關閉
            try:
                db.close()
            except:
                pass  # 如果連線已關閉，忽略關閉錯誤

    def send_email(self, to: str, subject: str, body: str):
        """發送郵件"""
        try:
            message = {
                "raw": base64.urlsafe_b64encode(
                    f"To: {to}\r\nSubject: {subject}\r\n\r\n{body}".encode()
                ).decode()
            }

            result = (
                self.service.users()
                .messages()
                .send(userId="me", body=message)
                .execute()
            )

            logger.info(f"Email sent successfully: {result['id']}")
            return result

        except HttpError as e:
            logger.error(f"Failed to send email: {e}")
            return None


def get_gmail_service(user_id: int) -> GmailService:
    """取得 Gmail 服務實例"""
    return GmailService(user_id)