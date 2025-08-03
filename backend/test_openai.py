
from dotenv import load_dotenv
load_dotenv()

from openai_service import get_openai_service

try:
    print("正在測試 OpenAI 服務...")
    service = get_openai_service()
    
    # 測試簡單的面試邀請識別
    subject = "面試邀請 - 軟體工程師職位"
    body = "您好，我們想邀請您來參加軟體工程師的面試，時間是明天下午2點。"
    
    print("測試郵件分析...")
    is_interview, confidence = service.is_interview_email(subject, body)
    print(f"分析結果: 是面試邀請={is_interview}, 信心度={confidence}")
    
    if is_interview:
        print("測試面試資訊提取...")
        interview_info = service.extract_interview_info(subject, body)
        print(f"提取結果: {interview_info}")
        
        print("測試回信生成...")
        reply = service.generate_reply(interview_info, "professional")
        print(f"回信內容: {reply}")
    
    print("OpenAI 測試完成！")
    
except Exception as e:
    print(f"OpenAI 測試失敗: {e}")
    import traceback
    traceback.print_exc()

