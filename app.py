import streamlit as st
import requests
import uuid
import time
import json
import re
from processor import calculate_card_fees

# --- 네이버 OCR 함수 ---
def get_naver_ocr_text(image_bytes):
    if "NAVER_OCR_URL" not in st.secrets or "NAVER_OCR_SECRET" not in st.secrets:
        st.error("Secrets 설정이 되어 있지 않습니다.")
        return None

    invoke_url = st.secrets["NAVER_OCR_URL"]
    secret_key = st.secrets["NAVER_OCR_SECRET"]

    request_json = {
        'images': [{'format': 'jpg', 'name': 'receipt_scan'}],
        'requestId': str(uuid.uuid4()),
        'version': 'V2',
        'timestamp': int(round(time.time() * 1000))
    }

    payload = {'message': json.dumps(request_json).encode('UTF-8')}
    files = [('file', image_bytes)]
    headers = {'X-OCR-SECRET': secret_key}

    try:
        response = requests.post(invoke_url, headers=headers, data=payload, files=files)
        if response.status_code == 200:
            res = response.json()
            full_text = " ".join([field['inferText'] for field in res['images'][0]['fields']])
            return full_text
        return None
    except Exception:
        return None

# --- UI 화면 ---
st.set_page_config(page_title="동명베어링 정산기")
st.title("📸 카드 매출 자동 정산기")

uploaded_file = st.camera_input("영수증을 찍어주세요")

if uploaded_file is not None:
    image_bytes = uploaded_file.getvalue()
    
    with st.spinner('분석 중...'):
        full_text = get_naver_ocr_text(image_bytes)
        
        if full_text:
            st.subheader("🔍 인식된 텍스트")
            st.write(full_text)
            
            # 1. 매입사 찾기 (엑셀의 '매입사명'과 일치하도록 설정)
            merchant = "기타"
            if "국민" in full_text: merchant = "국민카드"
            elif "비씨" in full_text or "BC" in full_text: merchant = "비씨카드"
            elif "농협" in full_text or "NH" in full_text: merchant = "농협카드"
            elif "신한" in full_text: merchant = "신한카드"
            elif "삼성" in full_text: merchant = "삼성카드"
            elif "현대" in full_text: merchant = "현대카드"
            elif "롯데" in full_text: merchant = "롯데카드"
            elif "하나" in full_text: merchant = "하나카드"
            
            # 2. 금액 찾기
            numbers = re.findall(r'\d{1,3}(?:,\d{3})+|\d{4,}', full_text)
            clean_numbers = [int(n.replace(',', '')) for n in numbers]
            amount = max(clean_numbers) if clean_numbers else 0
            
            st.divider()
            
            # 결과 표시
            st.metric("추출된 매입사", merchant)
            st.metric("추출된 금액", f"{amount:,}원")

            if amount > 0:
                try:
                    # ★ 여기서 '매입사' 대신 '매입사명'을 사용하도록 processor가 설계되어야 함
                    # 만약 processor.py 내부에서 '매입사'를 찾고 있다면 에러가 날 수 있으니 
                    # merchant 변수값을 엑셀과 똑같이 전달합니다.
                    result = calculate_card_fees(merchant, "전체", amount)
                    st.success("✅ 정산 완료!")
                    st.table(result)
                except Exception as e:
                    st.error(f"오류: {e}")
                    st.info("💡 엑셀 파일의 첫 줄 제목이 '매입사명'이 맞는지 다시 확인해 주세요.")