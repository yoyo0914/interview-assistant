from dotenv import load_dotenv

load_dotenv()

import os
from openai import OpenAI

api_key = os.getenv("OPENAI_API_KEY")
print(f"API Key 前10字元: {api_key[:10]}...")

try:
    client = OpenAI(api_key=api_key)

    # 測試簡單的 API 呼叫
    print("測試 OpenAI API 連接...")
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "Hello, just say 'Hi' back."},
        ],
        temperature=0.1,
    )

    print("API 呼叫成功！")
    print(f"回應: {response.choices[0].message.content}")

except Exception as e:
    print(f"API 呼叫失敗: {e}")
    print(f"錯誤類型: {type(e)}")

    # 檢查具體錯誤
    if "authentication" in str(e).lower():
        print("❌ API key 認證失敗")
    elif "quota" in str(e).lower() or "billing" in str(e).lower():
        print("❌ API 額度不足或帳單問題")
    elif "rate" in str(e).lower():
        print("❌ API 呼叫頻率限制")
    else:
        print("❌ 其他 API 錯誤")
