import streamlit as st
import requests
import uuid
import time
import json
import re
import pandas as pd
from datetime import datetime, timedelta
import holidays # 공휴일 계산을 위해 필요 (requirements.txt에 추가 확인)

# --- 네이버 OCR 함수 ---
def get_naver_ocr_text(image_bytes):
    invoke_url = st.secrets["NAVER_OCR_URL"]
    secret_key = st.secrets["NAVER_OCR_SECRET"]
    request_json = {
        'images': [{'format': 'jpg', 'name': 'receipt'}],
        'requestId': str(uuid.uuid4()),
        'version': 'V2',
        'timestamp': int(round(time.time() * 1000))
    }
    payload = {'message': json.dumps(request_json).encode('UTF-8')}
    files = [('file', image_bytes)]
    headers = {'X-OCR-SECRET': secret_key}
    res = requests.post(invoke_url, headers=headers, data=payload, files=files)
    if res.status_code == 200:
        return " ".join([f['inferText'] for f in res.json()['images'][0]['fields']])
    return None

# --- 영업일 계산 함수 (주말/공휴일 제외) ---
def calculate_settle_date(base_date, days_to_add):
    kr_holidays = holidays.KR()
    current_date = base_date
    added_days = 0
    while added_days < days_to_add:
        current_date += timedelta(days=1)
        # 토요일(5), 일요일(6) 및 공휴일 제외
        if current_date.weekday() < 5 and current_date not in kr_holidays:
            added_days += 1
    return current_date

# --- UI 세팅 ---
st.set_page_config(page_title="동명베어링 카드 정산기", layout="wide")
st.title("📸 카드 매출 자동 정산기")

uploaded_file = st.camera_input("영수증을 촬영하세요")

if uploaded_file:
    full_text = get_naver_ocr_text(uploaded_file.getvalue())
    
    if full_text:
        st.subheader("🔍 영수증 분석 결과")
        
        # 1. 금액 추출 (합계/판매금액 등 키워드 기반)
        amount_match = re.search(r'(?:합계|금액|판매금액|Total)\s*[:]*\s*([\d,]+)', full_text, re.IGNORECASE)
        amount = int(amount_match.group(1).replace(',', '')) if amount_match else 0
        
        # 2. 거래일시 추출
        date_match = re.search(r'(\d{2,4}[-/.]\d{2}[-/.]\d{2})', full_text)
        tran_date_str = date_match.group(1) if date_match else datetime.now().strftime("%Y-%m-%d")
        
        # 3. 엑셀 규칙 매칭
        try:
            # CSV 혹은 Excel 로드 (파일명 확인 필요)
            rules = pd.read_csv("rules.xlsx") if "csv" in "rules.xlsx" else pd.read_excel("rules.xlsx")
            final_match = None
            
            for _, row in rules.iterrows():
                m_name = str(row['매입사명']).strip()
                k1 = str(row.get('키워드1(카드사명)', '')).strip() if pd.notna(row.get('키워드1(카드사명)', '')) else ""
                k2 = str(row.get('키워드2(유형)', '')).strip() if pd.notna(row.get('키워드2(유형)', '')) else ""

                if m_name in full_text:
                    # 키워드1과 키워드2가 영수증에 모두 있는지 확인 (빈칸이면 무시)
                    k1_match = (k1 == "" or k1 in full_text)
                    k2_match = (k2 == "" or k2 in full_text)
                    
                    if k1_match and k2_match:
                        final_match = row
                        break
            
            if final_match is not None:
                # 계산 로직
                fee_rate = float(final_match['카드수수료'])
                fee_amount = int(amount * fee_rate)
                settle_amount = amount - fee_amount
                
                # 입금일 계산
                days_to_add = int(final_match['입금 요일(주말 및 공휴일 제외)'])
                try:
                    base_dt = datetime.strptime(tran_date_str.replace('.','-').replace('/','-'), "%Y-%m-%d")
                except:
                    base_dt = datetime.now()
                settle_date = calculate_settle_date(base_dt, days_to_add)

                # 화면 출력
                c1, c2, c3 = st.columns(3)
                with c1:
                    st.metric("추출 매입사", final_match['매입사명'])
                    st.write(f"💳 카드사: {final_match.get('키워드1(카드사명)', '기타')}")
                with c2:
                    st.metric("판매 합계", f"{amount:,}원")
                    st.write(f"📉 수수료: {fee_rate*100:.1f}% (-{fee_amount:,}원)")
                with c3:
                    st.metric("수금 예정금액", f"{settle_amount:,}원")
                    st.write(f"📅 입금 예정일: {settle_date.strftime('%Y-%m-%d (%a)')}")
                
            else:
                st.warning("⚠️ 일치하는 카드사 규칙을 찾을 수 없습니다.")
                st.text(f"인식된 텍스트 일부: {full_text[:200]}...")
                
        except Exception as e:
            st.error(f"데이터 처리 오류: {e}")