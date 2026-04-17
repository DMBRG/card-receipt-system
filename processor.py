import pandas as pd
import holidays
from datetime import datetime, timedelta

# 1. 한국 공휴일 정보 가져오기
kr_holidays = holidays.KR()

def get_settlement_date(base_date, working_days):
    """
    주말과 공휴일을 제외한 영업일 기준 입금 예정일을 계산합니다.
    """
    current_date = base_date
    added_days = 0
    while added_days < working_days:
        current_date += timedelta(days=1)
        # 토요일(5), 일요일(6) 및 공휴일 제외
        if current_date.weekday() < 5 and current_date not in kr_holidays:
            added_days += 1
    return current_date

def calculate_card_fees(ocr_merchant, ocr_card_name, total_amount, excel_path='rules.xlsx'):
    """
    엑셀 파일을 읽어 OCR 결과와 매칭하고 최종 정산 금액을 계산합니다.
    """
    try:
        # 엑셀 파일 읽기 (Sheet1 기준)
        df = pd.read_excel(excel_path)
        
        # 1. 매입사 필터링
        merchant_df = df[df['매입사'] == ocr_merchant]
        
        if merchant_df.empty:
            return f"오류: '{ocr_merchant}'는 엑셀에 등록되지 않은 매입사입니다."

        # 2. 키워드 매칭 (분류 컬럼 확인)
        # 기본값으로 '전체' 행을 찾아둠
        default_row = merchant_df[merchant_df['분류(키워드)'] == '전체']
        matched_row = default_row.iloc[0] if not default_row.empty else merchant_df.iloc[0]

        # '전체'가 아닌 특정 키워드(예: 우리, 농협)가 카드명에 포함되어 있는지 확인
        for _, row in merchant_df.iterrows():
            keyword = str(row['분류(키워드)'])
            if keyword != '전체' and keyword in ocr_card_name:
                matched_row = row
                break
        
        # 3. 데이터 추출 및 계산
        fee_rate = matched_row['수수료']
        settle_days = int(matched_row['정산주기(영업일)'])
        
        fee_amount = int(total_amount * fee_rate)
        net_amount = total_amount - fee_amount
        
        # 4. 입금일 계산 (오늘 기준)
        today = datetime.now()
        est_date = get_settlement_date(today, settle_days)
        
        return {
            "매입사": ocr_merchant,
            "인식된카드": ocr_card_name,
            "적용수수료율": f"{fee_rate * 100:.2f}%",
            "수수료금액": f"{fee_amount:,}원",
            "수금예정액": f"{net_amount:,}원",
            "입금예정일": est_date.strftime('%Y-%m-%d (%a)')
        }

    except Exception as e:
        return f"파일 처리 중 오류 발생: {e}"

# --- 사용 예시 (테스트용) ---
if __name__ == "__main__":
    # 테스트 데이터: 매입사는 'BC카드', 영수증에 찍힌 카드사는 '우리체크'라고 가정
    test_result = calculate_card_fees("BC카드", "우리체크", 125000)
    
    print("=== 카드 매출 정산 결과 ===")
    if isinstance(test_result, dict):
        for key, value in test_result.items():
            print(f"{key}: {value}")
    else:
        print(test_result)