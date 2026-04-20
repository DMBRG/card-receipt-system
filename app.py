import streamlit as st
import requests
import uuid
import time
import json
import re
import pandas as pd
import math
from datetime import datetime, timedelta
import holidays

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

# --- 영업일 및 특수 입금일 계산 함수 ---
def calculate_custom_settle_date(base_dt, row, full_text):
    kr_holidays = holidays.KR()
    m_name = str(row['매입사명'])
    k1 = str(row.get('키워드1(카드사명)', '')).strip()
    k2 = str(row.get('키워드2(유형)', '')).strip()
    
    days_str = str(row['입금 요일(주말 및 공휴일 제외)'])
    days_to_add = int(re.search(r'\d+', days_str).group()) if re.search(r'\d+', days_str) else 3
    
    weekday = base_dt.weekday() 

    if "삼성" in m_name or "삼성" in k1:
        if weekday == 4: 
            days_to_add = 2
        elif weekday == 3: 
            tomorrow = base_dt + timedelta(days=1)
            if tomorrow in kr_holidays:
                days_to_add = 2
    elif ("하나" in m_name or "하나" in k1) and "체크" not in k2:
        if weekday in [2, 3]: 
            days_to_add = 2
        else: 
            days_to_add = 3

    current_date = base_dt
    added_days = 0
    while added_days < days_to_add:
        current_date += timedelta(days=1)
        if current_date.weekday() < 5 and current_date not in kr_holidays:
            added_days += 1
    return current_date

# --- 메인 UI ---
st.set_page_config(page_title="동명베어링 카드 정산기", layout="wide")
st.title("📸 카드 매출 자동 정산기")

uploaded_file = st.camera_input("영수증을 촬영하세요")

if uploaded_file:
    full_text = get_naver_ocr_text(uploaded_file.getvalue())
    
    if full_text:
        st.subheader("🔍 분석 결과")
        
        # 1. 금액 추출 로직 (수정됨: '합계'를 최우선으로 찾음)
        # '합계', '합 계', 'Total'을 먼저 찾고, 없으면 '판매금액', '금액'을 찾습니다.
        amount = 0
        # 순서가 중요합니다: 합계 계열 키워드를 먼저 배치
        priority_keywords = [r'합\s*계', r'Total', r'승인금액', r'판매금액', r'금액']
        
        for keyword in priority_keywords:
            match = re.search(f'{keyword}\s*[:]*\s*([\d,]+)', full_text, re.IGNORECASE)
            if match:
                amount = int(match.group(1).replace(',', ''))
                break # 합계를 찾으면 바로 멈춤 (판매금액까지 안 내려감)

        # 2. 날짜 추출
        date_match = re.search(r'(\d{2,4}[-/.]\d{2}[-/.]\d{2})', full_text)
        if date_match:
            raw_date = date_match.group(1).replace('.','-').replace('/','-')
            try:
                if len(raw_date.split('-')[0]) == 2:
                    base_dt = datetime.strptime("20" + raw_date, "%Y-%m-%d")
                else:
                    base_dt = datetime.strptime(raw_date, "%Y-%m-%d")
            except:
                base_dt = datetime.now()
        else:
            base_dt = datetime.now()

        try:
            # 엑셀 로드 (파일명 확인 필요: rules.xlsx)
            try: rules = pd.read_excel("rules.xlsx")
            except: rules = pd.read_csv("rules.xlsx")

            final_match = None
            for _, row in rules.iterrows():
                m_name = str(row['매입사명']).strip()
                k1_val = str(row.get('키워드1(카드사명)', '')).strip() if pd.notna(row.get('키워드1(카드사명)', '')) else ""
                k2_val = str(row.get('키워드2(유형)', '')).strip() if pd.notna(row.get('키워드2(유형)', '')) else ""

                if m_name in full_text:
                    k1_list = [item.strip() for item in k1_val.split(',')] if k1_val else [""]
                    k1_match = any(item in full_text for item in k1_list) if k1_val else True
                    k2_match = (k2_val == "" or k2_val in full_text)
                    
                    if k1_match and k2_match:
                        final_match = row
                        break
            
            if final_match is not None:
                fee_text = str(final_match['카드수수료'])
                fee_rate_match = re.search(r"(\d+\.\d+)", fee_text)
                
                if fee_rate_match:
                    fee_rate = float(fee_rate_match.group(1))
                    
                    # 요청하신 계산 방식 적용
                    fee_amount = math.floor(amount * fee_rate) # 수수료: 원단위 절사(내림)
                    settle_amount = math.ceil(amount - (amount * fee_rate)) # 수금금액: 무조건 올림
                    
                    settle_date = calculate_custom_settle_date(base_dt, final_match, full_text)

                    c1, c2, c3 = st.columns(3)
                    with c1:
                        st.info(f"🏦 **매입/카드사**\n\n{final_match['매입사명']} / {k1_val}")
                        st.write(f"거래일: {base_dt.strftime('%Y-%m-%d (%a)')}")
                    with c2:
                        st.success(f"💰 **최종 합계 금액**\n\n{amount:,}원")
                        st.write(f"수수료율: {fee_rate*100:.2f}%")
                    with c3:
                        st.warning(f"📩 **수금 예정액**\n\n{settle_amount:,}원")
                        st.write(f"수수료: -{fee_amount:,}원 (절사)")

                    st.divider()
                    st.write(f"📅 **입금 예정일:** {settle_date.strftime('%Y년 %m월 %d일 (%a)')} 입금 예정")
                else:
                    st.error("수수료 요율을 찾을 수 없습니다.")
            else:
                st.warning("일치하는 카드사 규칙을 찾을 수 없습니다.")
                
        except Exception as e:
            st.error(f"데이터 처리 중 오류 발생: {e}")