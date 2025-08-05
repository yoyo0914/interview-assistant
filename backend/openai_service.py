import os
import json
from openai import OpenAI
from typing import Dict, Optional, Tuple
import logging
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)


class OpenAIService:
    def __init__(self, api_key: str = None):
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            raise ValueError("OpenAI API key not found")

        self.client = OpenAI(api_key=self.api_key)
        self.model = "gpt-4o-mini"

    def detect_language(self, subject: str, body: str) -> str:
        """檢測郵件主要語言"""
        try:
            prompt = f"""
Analyze the following email and determine its primary language.

Subject: {subject}
Content: {body[:500]}

Respond with only one word: "chinese" or "english"
"""

            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": "You are a language detection expert.",
                    },
                    {"role": "user", "content": prompt},
                ],
                temperature=0.1,
            )

            result = response.choices[0].message.content.strip().lower()
            return "chinese" if "chinese" in result else "english"

        except Exception as e:
            logger.error(f"Failed to detect language: {e}")
            return "english"  # 預設英文

    def is_interview_email(self, subject: str, body: str) -> Tuple[bool, float]:
        """判斷郵件是否為面試邀請"""
        try:
            prompt = f"""
Analyze if the following email is an interview invitation.

Subject: {subject}
Content: {body[:1500]}

You must respond with EXACTLY this JSON format (no extra text):
{{
    "is_interview": true or false,
    "confidence": number between 0-100,
    "reason": "brief explanation"
}}

Criteria:
- Contains interview-related keywords (interview, 面試, meeting, 會談, etc.)
- Mentions time scheduling
- From company HR or recruiter
- Job position related content
"""

            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": "You are a professional email analysis expert. Always respond with valid JSON only.",
                    },
                    {"role": "user", "content": prompt},
                ],
                temperature=0.1,
            )

            content = response.choices[0].message.content.strip()
            logger.info(f"OpenAI raw response: {content}")

            # 嘗試解析 JSON
            try:
                result = json.loads(content)
                return result["is_interview"], result["confidence"]
            except json.JSONDecodeError:
                # 如果 JSON 解析失敗，嘗試提取關鍵字
                logger.warning(f"JSON parse failed, using fallback: {content}")

                # 簡單的關鍵字檢測作為備用
                text_to_check = (subject + " " + body).lower()
                interview_keywords = [
                    "interview",
                    "面試",
                    "面談",
                    "會面",
                    "meeting",
                    "討論",
                    "chat",
                    "talk",
                ]

                found_keywords = [
                    kw for kw in interview_keywords if kw in text_to_check
                ]
                if found_keywords:
                    return True, 70.0
                else:
                    return False, 30.0

        except Exception as e:
            logger.error(f"Failed to analyze email: {e}")
            text_to_check = (subject + " " + body).lower()
            interview_keywords = ["interview", "面試", "面談", "會面"]
            if any(kw in text_to_check for kw in interview_keywords):
                return True, 60.0
            return False, 0

    def extract_interview_info(self, subject: str, body: str) -> Optional[Dict]:
        """從面試邀請中提取詳細資訊"""
        try:
            prompt = f"""
Extract detailed information from the following interview invitation email.

Subject: {subject}
Content: {body}

You must respond with EXACTLY this JSON format (no extra text):
{{
    "company_name": "company name or null",
    "position": "job position or null", 
    "interview_date": "interview date in YYYY-MM-DD format or null",
    "interview_time": "interview time or null",
    "interview_location": "interview location or null",
    "interview_type": "online or onsite or phone or null",
    "interviewer_name": "interviewer name or null",
    "interviewer_email": "interviewer email or null",
    "additional_info": "other important information or null",
    "confidence_score": number between 0-100
}}

Important: Use null (not "null" string) for missing information.
"""

            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": "You are a professional information extraction expert. Always respond with valid JSON only.",
                    },
                    {"role": "user", "content": prompt},
                ],
                temperature=0.1,
            )

            content = response.choices[0].message.content.strip()
            logger.info(f"OpenAI extract response: {content}")

            try:
                result = json.loads(content)
                return result
            except json.JSONDecodeError:
                logger.warning(f"JSON parse failed for extraction: {content}")
                # 返回基本結構
                return {
                    "company_name": None,
                    "position": None,
                    "interview_date": None,
                    "interview_time": None,
                    "interview_location": None,
                    "interview_type": None,
                    "interviewer_name": None,
                    "interviewer_email": None,
                    "additional_info": None,
                    "confidence_score": 50,
                }

        except Exception as e:
            logger.error(f"Failed to extract interview info: {e}")
            return None

    def generate_reply(
        self, interview_info: Dict, tone: str = "professional", language: str = None
    ) -> Optional[str]:
        """生成回信草稿"""
        try:
            # 如果沒指定語言，根據公司名稱判斷
            if not language:
                company_name = interview_info.get("company_name", "")
                language = self.detect_language(company_name, str(interview_info))

            if language == "chinese":
                return self._generate_chinese_reply(interview_info, tone)
            else:
                return self._generate_english_reply(interview_info, tone)

        except Exception as e:
            logger.error(f"Failed to generate reply: {e}")
            return None

    def _generate_chinese_reply(self, interview_info: Dict, tone: str) -> Optional[str]:
        """生成中文回信"""
        tone_instructions = {
            "professional": "專業且有禮貌",
            "friendly": "友善且熱忱",
            "formal": "正式且謹慎",
        }

        tone_desc = tone_instructions.get(tone, "專業且有禮貌")

        prompt = f"""
請根據以下面試資訊生成一封{tone_desc}的回信草稿。

面試資訊：
- 公司: {interview_info.get('company_name', '未知')}
- 職位: {interview_info.get('position', '未知')}
- 面試日期: {interview_info.get('interview_date', '未知')}
- 面試時間: {interview_info.get('interview_time', '未知')}
- 面試地點: {interview_info.get('interview_location', '未知')}
- 面試類型: {interview_info.get('interview_type', '未知')}
- 面試官: {interview_info.get('interviewer_name', '未知')}

回信內容要求：
1. 感謝面試機會
2. 確認參加面試
3. 確認面試時間和地點
4. 表達期待
5. 語調要{tone_desc}
6. 使用繁體中文
7. 格式要適合 email

請直接回傳郵件內容，不需要額外說明。
"""

        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": "你是專業的商務郵件撰寫專家，擅長撰寫各種語調的回信。"},
                {"role": "user", "content": prompt},
            ],
            temperature=0.3,
        )

        return response.choices[0].message.content.strip()

    def _generate_english_reply(self, interview_info: Dict, tone: str) -> Optional[str]:
        """生成英文回信"""
        tone_instructions = {
            "professional": "professional and polite",
            "friendly": "friendly and enthusiastic",
            "formal": "formal and courteous",
        }

        tone_desc = tone_instructions.get(tone, "professional and polite")

        prompt = f"""
Generate a {tone_desc} reply email based on the following interview information.

Interview Information:
- Company: {interview_info.get('company_name', 'Unknown')}
- Position: {interview_info.get('position', 'Unknown')}
- Interview Date: {interview_info.get('interview_date', 'Unknown')}
- Interview Time: {interview_info.get('interview_time', 'Unknown')}
- Interview Location: {interview_info.get('interview_location', 'Unknown')}
- Interview Type: {interview_info.get('interview_type', 'Unknown')}
- Interviewer: {interview_info.get('interviewer_name', 'Unknown')}

Reply requirements:
1. Thank for the interview opportunity
2. Confirm attendance
3. Confirm interview time and location
4. Express enthusiasm
5. Use {tone_desc} tone
6. Proper email format
7. Professional business English

Return only the email content without additional explanations.
"""

        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {
                    "role": "system",
                    "content": "You are a professional business email writing expert skilled in crafting replies with various tones.",
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.3,
        )

        return response.choices[0].message.content.strip()

    def generate_reply_subject(
        self, original_subject: str, language: str = None
    ) -> str:
        """生成回信主旨（支援中英文）"""
        try:
            if not language:
                language = self.detect_language(original_subject, "")

            if language == "chinese":
                prompt = f"""
請為以下面試邀請郵件生成適當的回信主旨。

原主旨: {original_subject}

回信主旨要求：
1. 表明這是回信 (Re:)
2. 保持簡潔專業
3. 繁體中文

請直接回傳主旨，不需要額外說明。
"""
                system_content = "你是專業的郵件主旨專家。"
            else:
                prompt = f"""
Generate an appropriate reply subject for the following interview invitation email.

Original Subject: {original_subject}

Reply subject requirements:
1. Indicate this is a reply (Re:)
2. Keep it concise and professional
3. Use English

Return only the subject line without additional explanations.
"""
                system_content = "You are a professional email subject line expert."

            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_content},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.1,
            )

            return response.choices[0].message.content.strip()

        except Exception as e:
            logger.error(f"Failed to generate subject: {e}")
            return f"Re: {original_subject}"


def get_openai_service() -> OpenAIService:
    """取得 OpenAI 服務實例"""
    return OpenAIService()
