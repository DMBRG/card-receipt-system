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
from PIL import Image, ImageEnhance  # 이미지 보정용 라이브러리
import io

# --- 이미지 전처리 함수 (흐린 사진 보정) ---
def preprocess_image(image_bytes):
    image = Image.open(io.BytesIO(image_bytes))
    
    # 1. 선명도 향상 (2.0은 원래보다 2배 선명하게)
    enhancer = ImageEnhance.Sharpness(image)
    image = enhancer.enhance(2.0)
    
    # 2. 대비 향상 (글자와 배경을 더 뚜렷하게 분리)
    enhancer = ImageEnhance.Contrast(image)
    image = enhancer.enhance(1.5)
    
    # 보정된 이미지를 다시 바이트로 변환
    img_byte_arr = io.BytesIO()
    image.save(img_byte_arr, format='JPEG', quality=95)
    return img_byte_arr.getvalue()

# --- 네이버 OCR 함수 ---
def get_naver_ocr_text(image_bytes):
    # 전처리 적용
    processed_bytes = preprocess_image(image_bytes)
    
    invoke_url = st.secrets["NAVER_OCR_URL"]
    secret_key = st.secrets["NAVER_OCR_SECRET"]
    request_json = {
        'images': [{'format': 'jpg', 'name': 'receipt'}],
        'requestId': str(uuid.uuid4()),
        'version': 'V2',
        'timestamp': int(round(time.time() * 1000))
    }
    payload = {'message': json.dumps(request_json).encode('UTF-8')}
    files = [('file', processed_bytes)] # 보정된 이미지 전송
    headers = {'X-OCR-SECRET': secret_key}
    res = requests.post(invoke_url, headers=headers, data=payload, files=files)
    if res.status_code == 200:
        return " ".join([f['inferText'] for f in res.json()['images'][0]['fields']])
    return None

# --- 영업일 및 특수 입금일 계산 함수 (이전 로직 동일) ---
def calculate_custom_settle_date(base_dt, row, full_text):
    kr_holidays = holidays.KR()
    m_name = str(row['매입사명'])
    k1 = str(row.get('키워드1(카드사명)', '')).strip()
    k2 = str(row.get('키워드2(유형)', '')).strip()
    
    days_str = str(row['입금 요일(주말 및 공휴일 제외)'])
    days_to_add = int(re.search(r'\d+', days_str).group()) if re.search(r'\d+', days_str) else 3
    
    weekday = base_dt.weekday() 

    if "삼성" in m_name or "삼성" in k1:
        if weekday == 4: days_to_add = 2
        elif weekday == 3: 
            tomorrow = base_dt + timedelta(days=1)
            if tomorrow in kr_holidays: days_to_add = 2
    elif ("하나" in m_name or "하나" in k1) and "체크" not in k2:
        if weekday in [2, 3]: days_to_add = 2
        else: days_to_add = 3

    current_date = base_dt
    added_days = 0
    while added_days < days_to_add:
        current_date += timedelta(days=1)
        if current_date.weekday() < 5 and current_date not in kr_holidays:
            added_days += 1
    return current_date

# --- UI 메인 ---
st.set_page_config(page_title="동명베어링 카드 정산기", layout="wide")

# 사이드바에 촬영 가이드 배치 (공간 효율성)
with st.sidebar:
    st.header("📸 촬영 가이드")
    st.success("✅ **이렇게 찍으세요**\n- 수평을 맞춰서 똑바로\n- 밝은 곳에서 그림자 없이\n- 글자가 화면에 꽉 차게")
    st.error("❌ **피해주세요**\n- 영수증이 구겨진 상태\n- 어두운 곳에서 플래시 사용\n- 너무 멀리서 촬영")
    st.info("💡 **Tip**\n초점이 안 잡히면 영수증을 살짝 멀리했다가 다시 가까이 가져와 보세요.")

st.title("📸 카드 매출 자동 정산기")

uploaded_file = st.camera_input("영수증을 촬영하세요")

if uploaded_file:
    with st.spinner('이미지 보정 및 분석 중...'):
        full_text = get_naver_ocr_text(uploaded_file.getvalue())
    
    if full_text:
        st.subheader("🔍 분석 결과")
        
        # 금액 추출 (합계 우선)
        amount = 0
        priority_keywords = [r'합\s*계', r'Total', r'승인금액', r'판매금액', r'금액']
        for keyword in priority_keywords:
            match = re.search(f'{keyword}\s*[:]*\s*([\d,]+)', full_text, re.IGNORECASE)
            if match:
                amount = int(match.group(1).replace(',', ''))
                break

        # 날짜 추출
        date_match = re.search(r'(\d{2,4}[-/.]\d{2}[-/.]\d{2})', full_text)
        if date_match:
            raw_date = date_match.group(1).replace('.','-').replace('/','-')
            try:
                if len(raw_date.split('-')[0]) == 2: base_dt = datetime.strptime("20" + raw_date, "%Y-%m-%d")
                else: base_dt = datetime.strptime(raw_date, "%Y-%m-%d")
            except: base_dt = datetime.now()
        else: base_dt = datetime.now()

        # 엑셀 매칭 및 정산 (이전 로직 동일)
        try:
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
                fee_rate_match = re.search(r"(\d+\.\d+)", str(final_match['카드수수료']))
                if fee_rate_match:
                    fee_rate = float(fee_rate_match.group(1))
                    fee_amount = math.floor(amount * fee_rate)
                    settle_amount = math.ceil(amount - (amount * fee_rate))
                    settle_date = calculate_custom_settle_date(base_dt, final_match, full_text)

                    c1, c2, c3 = st.columns(3)
                    with c1:
                        st.info(f"🏦 **매입/카드사**\n\n{final_match['매입사명']} / {k1_val}")
                    with c2:
                        st.success(f"💰 **최종 합계 금액**\n\n{amount:,}원")
                    with c3:
                        st.warning(f"📩 **수금 예정액**\n\n{settle_amount:,}원")

                    st.divider()
                    st.write(f"📅 **입금 예정일:** {settle_date.strftime('%Y년 %m월 %d일 (%a)')}")
        except Exception as e:
            st.error(f"오류 발생: {e}")