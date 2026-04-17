import streamlit as st
import requests
import uuid
import time
import json
from processor import calculate_card_fees

# 네이버 OCR 함수
def get_naver_ocr_text(image_bytes):
    invoke_url = st.secrets["NAVER_OCR_URL"]
    secret_key = st.secrets["NAVER_OCR_SECRET"]

    request_json = {
        'images': [{'format': 'jpg', 'name': 'demo'}],
        'requestId': str(uuid.uuid4()),
        'version': 'V2',
        'timestamp': int(round(time.time() * 1000))
    }

    payload = {'message': json.dumps(request_json).encode('UTF-8')}
    files = [('file', image_bytes)]
    headers = {'X-OCR-SECRET': secret_key}

    response = requests.post(invoke_url, headers=headers, data=payload, files=files)
    
    if response.status_code == 200:
        res = response.json()
        full_text = " ".join([field['inferText'] for field in res['images'][0]['fields']])
        return full_text
    else:
        return f"연결 오류: {response.status_code}"

# --- 화면 UI ---
st.title("📸 카드 매출 자동 정산기")

uploaded_file = st.camera_input("영수증을 찍어주세요")

if uploaded_file is not None:
    image_bytes = uploaded_file.getvalue()
    
    with st.spinner('네이버 AI가 영수증을 분석하고 있습니다...'):
        full_text = get_naver_ocr_text(image_bytes)
        
        # 텍스트에서 정보 추출 (임시 로직 - 영수증 패턴에 따라 수정 가능)
        merchant = "BC카드" if "비씨" in full_text or "BC" in full_text else "신한카드"
        
        # 금액 추출 (숫자만 골라내기 테스트용)
        st.subheader("🔍 인식된 텍스트")
        st.text(full_text)
        
        # 실제 계산기 호출 (금액은 일단 10000원으로 테스트)
        result = calculate_card_fees(merchant, "전체", 10000)
        st.write(result)