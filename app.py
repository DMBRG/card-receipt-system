import streamlit as st
import os
import re
from google.cloud import vision
from processor import calculate_card_fees
from datetime import datetime

# --- 페이지 설정 ---
st.set_page_config(page_title="카드 매출 정산 시스템", layout="centered")

# --- 구글 OCR 함수 ---
def get_ocr_text(image_content):
    """구글 Vision API를 사용하여 이미지의 텍스트를 추출합니다."""
    client = vision.ImageAnnotatorClient()
    image = vision.Image(content=image_content)
    response = client.text_detection(image=image)
    texts = response.text_annotations
    
    if response.error.message:
        raise Exception(f"API 오류: {response.error.message}")
        
    return texts[0].description if texts else ""

# --- 텍스트 분석 및 정보 추출 로직 ---
def extract_info_from_text(full_text):
    """인식된 전체 텍스트에서 매입사명과 금액을 찾아냅니다."""
    
    # 1. 매입사 찾기 (예시: 영수증에 '비씨', '신한', '삼성' 등이 포함되었는지 확인)
    # 실제 영수증에 찍히는 매입사 명칭 패턴을 추가하세요.
    if "비씨" in full_text or "BC" in full_text:
        merchant = "BC카드"
    elif "신한" in full_text:
        merchant = "신한카드"
    elif "국민" in full_text or "KB" in full_text:
        merchant = "국민카드"
    else:
        merchant = "기타"

    # 2. 카드사 키워드 (우리, 농협 등 분류를 위한 키워드 추출)
    card_keyword = "전체"
    keywords = ["우리", "농협", "하나", "기업", "국민"]
    for k in keywords:
        if k in full_text:
            card_keyword = k
            break

    # 3. 금액 추출 (정규표현식: 콤마 포함된 숫자 또는 연속된 숫자 찾기)
    # 영수증에서 가장 큰 숫자를 합계 금액으로 가정하는 로직을 많이 씁니다.
    amount_pattern = re.findall(r'\d{1,3}(?:,\d{3})+|\d{4,}', full_text)
    if amount_pattern:
        # 콤마 제거 후 숫자로 변환하여 가장 큰 값 선택
        amounts = [int(a.replace(',', '')) for a in amount_pattern]
        total_amount = max(amounts)
    else:
        total_amount = 0

    return merchant, card_keyword, total_amount

# --- UI 화면 구성 ---
st.title("📸 카드 매출 자동 계산기")
st.write(f"오늘 날짜: {datetime.now().strftime('%Y-%m-%d (%a)')}")
st.write("---")

# 모바일 카메라 호출
uploaded_file = st.camera_input("영수증 사진을 촬영해 주세요")

if uploaded_file is not None:
    image_bytes = uploaded_file.getvalue()
    
    try:
        with st.spinner('구글 AI가 영수증을 분석하고 있습니다...'):
            # 1. 구글 OCR 실행
            full_text = get_ocr_text(image_bytes)
            
            # 2. 정보 추출
            merchant, keyword, amount = extract_info_from_text(full_text)
            
            # 3. 엑셀 연동 및 수수료 계산 (processor.py 호출)
            # 엑셀 파일 이름이 'rules.xlsx'인지 꼭 확인하세요!
            result = calculate_card_fees(merchant, keyword, amount, excel_path='rules.xlsx')

        # 4. 결과 표시
        if isinstance(result, dict):
            st.success("✅ 분석 성공!")
            
            # 결과 요약 카드
            st.markdown(f"### 💰 수금 예정 금액: `{result['수금예정액']}`")
            
            col1, col2 = st.columns(2)
            with col1:
                st.info(f"**매입사**: {result['매입사']}\n\n**카드사**: {result['인식된카드']}")
            with col2:
                st.warning(f"**입금 예정일**\n\n{result['입금예정일']}")
            
            with st.expander("상세 정보 보기"):
                st.write(f"- 원금: {amount:,}원")
                st.write(f"- 수수료율: {result['적용수수료율']}")
                st.write(f"- 수수료 금액: {result['수수료금액']}")
                st.write("---")
                st.caption("인식된 전체 텍스트:")
                st.text(full_text)
        else:
            # 에러 메시지 출력 (매입사 미등록 등)
            st.error(result)
            st.info("영수증 텍스트 인식 결과:")
            st.text(full_text)

    except Exception as e:
        st.error(f"오류가 발생했습니다: {e}")
        st.info("gcloud 로그인이 완료되었는지, Vision API가 켜져 있는지 확인해 주세요.")