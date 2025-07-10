import os
import json
from openai import OpenAI
from typing import Dict, Optional, Tuple
import logging
from dotenv import load_dotenv

# 確保載入環境變數
load_dotenv()

logger = logging.getLogger(__name__)

class OpenAIService:
    def __init__(self, api_key: str = None):
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            raise ValueError("OpenAI API key not found")
        
        self.client = OpenAI(api_key=self.api_key)
        self.model = "gpt-4o-mini"  # 使用較便宜的模型
    
    def is_interview_email(self, subject: str, body: str) -> Tuple[bool, float]:
        """
        判斷郵件是否為面試邀請
        返回: (是否為面試邀請, 信心分數 0-100)
        """
        try:
            prompt = f"""
請分析以下郵件是否為面試邀請。

主旨: {subject}

內容: {body[:1500]}

請以 JSON 格式回應：
{{
    "is_interview": true/false,
    "confidence": 0-100的信心分數,
    "reason": "判斷理由"
}}

判斷標準：
- 包含面試、interview、會談等詞彙
- 提到時間安排
- 來自公司 HR 或招聘人員
- 職位相關內容
"""

            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "你是專業的郵件分析專家，專門識別面試邀請。"},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.1
            )
            
            result = json.loads(response.choices[0].message.content)
            return result["is_interview"], result["confidence"]
            
        except Exception as e:
            logger.error(f"Failed to analyze email: {e}")
            return False, 0
    
    def extract_interview_info(self, subject: str, body: str) -> Optional[Dict]:
        """
        從面試邀請中提取詳細資訊
        """
        try:
            prompt = f"""
請從以下面試邀請郵件中提取詳細資訊。

主旨: {subject}

內容: {body}

請以 JSON 格式回應，提取以下資訊：
{{
    "company_name": "公司名稱",
    "position": "職位名稱", 
    "interview_date": "面試日期 (YYYY-MM-DD 格式，如果有的話)",
    "interview_time": "面試時間",
    "interview_location": "面試地點 (線上/實體地址)",
    "interview_type": "online/onsite/phone 其中一種",
    "interviewer_name": "面試官姓名",
    "interviewer_email": "面試官信箱",
    "additional_info": "其他重要資訊",
    "confidence_score": 0-100的提取信心分數
}}

如果某項資訊未提及，請填入 null。
"""

            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "你是專業的資訊提取專家，專門從面試邀請中提取結構化資訊。"},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.1
            )
            
            result = json.loads(response.choices[0].message.content)
            return result
            
        except Exception as e:
            logger.error(f"Failed to extract interview info: {e}")
            return None
    
    def generate_reply(self, interview_info: Dict, tone: str = "professional") -> Optional[str]:
        """
        生成面試回信草稿
        
        Args:
            interview_info: 面試資訊字典
            tone: 回信語調 professional/friendly/formal
        """
        try:
            tone_instructions = {
                "professional": "專業且有禮貌",
                "friendly": "友善且熱忱",
                "formal": "正式且謹慎"
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
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3
            )
            
            return response.choices[0].message.content.strip()
            
        except Exception as e:
            logger.error(f"Failed to generate reply: {e}")
            return None
    
    def generate_reply_subject(self, original_subject: str) -> str:
        """
        生成回信主旨
        """
        try:
            prompt = f"""
請為以下面試邀請郵件生成適當的回信主旨。

原主旨: {original_subject}

回信主旨要求：
1. 表明這是回信 (Re:)
2. 保持簡潔專業
3. 繁體中文

請直接回傳主旨，不需要額外說明。
"""

            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "你是專業的郵件主旨專家。"},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.1
            )
            
            return response.choices[0].message.content.strip()
            
        except Exception as e:
            logger.error(f"Failed to generate subject: {e}")
            return f"Re: {original_subject}"

# 便利函數
def get_openai_service() -> OpenAIService:
    """取得 OpenAI 服務實例"""
    return OpenAIService()