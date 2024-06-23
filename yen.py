import os
from datetime import datetime, timedelta
import yfinance as yf
import pytz
import numpy as np
import streamlit as st
from google.oauth2 import service_account
from googleapiclient.discovery import build
import pandas as pd
import requests
from lxml import etree

tab1, tab2 = st.tabs(["엔", "차트분석"])

with tab1:
    st.title('원엔환율 적정환율 데이터')

    def fetch_data(url, xpath_queries):
        response = requests.get(url)
        response.raise_for_status()  # HTTP 에러가 발생하면 예외를 일으킴
        html = response.content
        tree = etree.HTML(html)
        data = []
        for query in xpath_queries:
            data.extend(tree.xpath(query))
        return data

    url = "https://kr.investing.com/currencies/jpy-krw"
    xpath_queries = [
        "//*[@id='__next']/div[2]/div[2]/div[2]/div[1]/div[1]/div[3]/div[1]/div[1]/div[1]//text()",  # 특정 요소 쿼리
    ]
    data = fetch_data(url, xpath_queries)

    # 각 요소의 텍스트 내용과 갯수 출력
    element_count = 0
    non_empty_data = []

    for element in data:
        if element.strip():  # 공백이 아닌 텍스트만 포함
            non_empty_data.append(element.strip())
            element_count += 1

    jpy_price = "\n".join(str(element) for element in non_empty_data)

    st.write(f"인베스팅닷컴기준 : {jpy_price}")

    def download_data(period_weeks, period_hours):
        """
        지정된 기간 동안의 Nikkei 225와 KRW/JPY 환율 데이터를 다운로드하는 함수
        :param period_weeks: int, 데이터를 다운로드할 기간(주)
        :param period_hours: int, 데이터를 다운로드할 기간(시간)
        :return: tuple, Nikkei 225 데이터프레임과 KRW/JPY 데이터프레임
        """
        start = datetime.today() - timedelta(weeks=period_weeks)  # 시작 날짜
        end = datetime.today()  # 종료 날짜

        # 데이터 다운로드 시도
        try:
            nikkei_data = yf.download('^N225', start=start, end=end)  # Nikkei 225 데이터 다운로드
        except Exception as e:
            st.error(f"Nikkei 225 데이터를 다운로드하는 도중 오류가 발생했습니다: {e}")
            return None, None, None

        try:
            krw_jpy_data = yf.download('KRWJPY=X', start=start, end=end, interval='1h')  # KRW/JPY 환율 데이터 다운로드 (1시간 간격)
        except Exception as e:
            st.error(f"KRW/JPY 데이터를 다운로드하는 도중 오류가 발생했습니다: {e}")
            return nikkei_data, None, None
        
        # 인덱스의 타임존을 UTC로 설정
        nikkei_data.index = nikkei_data.index.tz_localize('UTC')
        krw_jpy_data.index = krw_jpy_data.index.tz_convert('UTC')
        
        # 최근 24시간 동안의 데이터 필터링
        now = datetime.now(pytz.utc)  # 타임존 정보 추가
        last_24_hours_data = krw_jpy_data[krw_jpy_data.index >= (now - timedelta(hours=period_hours))]
        
        return nikkei_data, krw_jpy_data, last_24_hours_data

    def calculate_indicators(nikkei_data, krw_jpy_data):
        """
        다양한 금융 지표를 계산하는 함수
        :param nikkei_data: DataFrame, Nikkei 225 데이터
        :param krw_jpy_data: DataFrame, KRW/JPY 환율 데이터
        :return: dict, 계산된 지표들을 포함하는 딕셔너리
        """
        today_nikkei = round(nikkei_data['Close'].iloc[-1], 2)  # 현재 Nikkei 225 지수
        today_krw_jpy = round(krw_jpy_data['Close'].iloc[-1], 4)  # 현재 KRW/JPY 환율 (소수점 4자리까지)
        today_jpy_krw = round(1 / today_krw_jpy, 4)  # 현재 JPY/KRW 환율 (소수점 4자리까지)
        nikkei_median = round(nikkei_data['Close'].median(), 2)  # Nikkei 225 중앙값
        krw_jpy_median = round(krw_jpy_data['Close'].median(), 4)  # KRW/JPY 환율 중앙값
        jpy_krw_median = round(1 / krw_jpy_median, 4)  # JPY/KRW 환율 중앙값
        nikkei_gap_ratio = round((today_nikkei / nikkei_median) * 100, 2)  # Nikkei 격차 비율
        avg_nikkei_gap_ratio = round((nikkei_data['Close'] / (1 / krw_jpy_data['Close'])).mean() * 100, 2)  # 평균 Nikkei 갭 비율
        avg_nikkei = round(nikkei_data['Close'].mean(), 2)  # 평균 Nikkei 225 지수
        avg_krw_jpy = round(krw_jpy_data['Close'].mean(), 4)  # 평균 KRW/JPY 환율
        avg_jpy_krw = round(1 / avg_krw_jpy, 4)  # 평균 JPY/KRW 환율
        jpy_krw_estimate = round((today_nikkei / avg_nikkei_gap_ratio) * 100, 4)  # 적정 JPY/KRW 환율
        nikkei_gap_percentage = round(((today_nikkei - nikkei_median) / nikkei_median) * 100, 1)  # Nikkei 격차 퍼센트
        nikkei_gap_ratio_new = round((today_nikkei / jpy_krw_median) * 100, 2)  # 새로운 Nikkei 격차 비율
        return {
            'today_nikkei': today_nikkei,
            'today_jpy_krw': today_jpy_krw,
            'previous_jpy_krw': round(1 / krw_jpy_data['Close'].iloc[-2], 4),
            'nikkei_median': nikkei_median,
            'jpy_krw_median': jpy_krw_median,
            'nikkei_gap_ratio': nikkei_gap_ratio,
            'avg_nikkei_gap_ratio': avg_nikkei_gap_ratio,
            'avg_nikkei': avg_nikkei,
            'avg_jpy_krw': avg_krw_jpy,
            'jpy_krw_estimate': jpy_krw_estimate,
            'nikkei_gap_percentage': nikkei_gap_percentage,
            'nikkei_gap_ratio_new': nikkei_gap_ratio_new
        }

    def check_conditions(indicators):
        """
        투자 적합성 조건을 확인하는 함수
        :param indicators: dict, 계산된 지표들을 포함하는 딕셔너리
        :return: tuple, 각 조건의 만족 여부를 나타내는 불리언 값들의 튜플
        """
        condition1 = indicators['today_jpy_krw'] < indicators['avg_jpy_krw']  # 조건 1: 현재 JPY/KRW 환율이 평균 JPY/KRW 환율보다 낮은가
        condition2 = indicators['today_nikkei'] < indicators['avg_nikkei']  # 조건 2: 현재 Nikkei 225 지수가 평균 Nikkei 225 지수보다 낮은가
        condition3 = indicators['nikkei_gap_ratio_new'] > indicators['avg_nikkei_gap_ratio']  # 조건 3: 새로운 Nikkei 격차 비율이 평균 Nikkei 격차 비율보다 높은가
        condition4 = indicators['today_jpy_krw'] < indicators['jpy_krw_estimate']  # 조건 4: 현재 JPY/KRW 환율이 적정 JPY/KRW 환율보다 낮은가
        return condition1, condition2, condition3, condition4

    def calculate_exchange_rate(period_weeks, period_hours=24):
        """
        주요 로직을 실행하는 함수
        :param period_weeks: int, 데이터를 분석할 기간(주)
        :param period_hours: int, 최근 시간 단위로 분석할 시간 (기본 24시간)
        """
        # 데이터 다운로드
        nikkei_data, krw_jpy_data, last_24_hours_data = download_data(period_weeks, period_hours)
        
        if nikkei_data is None or krw_jpy_data is None:
            return  # 데이터 다운로드 오류 시 함수 종료

        # 지표 계산
        indicators = calculate_indicators(nikkei_data, krw_jpy_data)
        
        # 조건 확인
        conditions = check_conditions(indicators)
        suitable_conditions = sum(conditions)
        
        # Streamlit 인터페이스 구성
        today_jpy_krw = indicators['today_jpy_krw']
        previous_jpy_krw = indicators['previous_jpy_krw']
        jpy_krw_estimate = indicators['jpy_krw_estimate']
        delta = round(today_jpy_krw - previous_jpy_krw, 4)
        is_fair_value = today_jpy_krw < jpy_krw_estimate
        
        emoji = "☀️" if is_fair_value else "🌧️"
        status_text = "적정환율" if is_fair_value else "과대평가"
        
        st.metric(label=f"야후파이낸스기준 (전일종가: {previous_jpy_krw}원 현재: {today_jpy_krw} 원)", value=f"{emoji}", delta=f"{delta} 원")
        st.write(f"현재 JPY/KRW 환율은 {jpy_krw_estimate} 원의 적정환율과 비교하여 {status_text}되어 있습니다.")
        
        # 조건 표시
        condition_labels = [
            '조건1 (현재 JPY/KRW 환율 < 4주 평균 환율)',
            '조건2 (현재 Nikkei 225 지수 < 4주 평균 Nikkei 225 지수)',
            '조건3 (현재 Nikkei 갭 비율 > 4주 평균 Nikkei 갭 비율)',
            '조건4 (현재 JPY/KRW 환율 < 적정 JPY/KRW 환율)'
        ]
        
        for label, condition in zip(condition_labels, conditions):
            condition_status = "✅" if condition else "❌"
            st.write(f"{label}: {condition_status}")

    # 4주 기준으로 데이터 계산
    calculate_exchange_rate(4)

    # 사용자 입력을 받아 데이터프레임 행 수 조정
    num_rows = st.number_input("표시할 데이터프레임 행 수 입력 (최대 200개):", min_value=1, max_value=200, value=40, step=1)

    # 스프레드시트 데이터 가져오기
    # 서비스 계정 JSON 파일 경로
    SERVICE_ACCOUNT_FILE = 'dollainvestingtool-1a7b13d623dd.json'

    # 스프레드시트 ID와 범위 설정
    SPREADSHEET_ID = '1iw-NdSsOOg63Q3dOQWVdY6FzW1fOuYGkIuX1Wx-wy0Q'
    RANGE_NAME = '엔_4주!A2:F'  # 필요한 데이터 범위 설정

    # 스프레드시트 ID와 범위 설정
    RANGE_NAME_a = '엔_4주_환율만!A2:F'  # 필요한 데이터 범위 설정

    # API 범위 지정
    SCOPES = ['https://www.googleapis.com/auth/spreadsheets.readonly']

    # 인증 객체 생성
    creds = service_account.Credentials.from_service_account_file(
        SERVICE_ACCOUNT_FILE, scopes=SCOPES)

    # Sheets API 클라이언트 생성
    service = build('sheets', 'v4', credentials=creds)

    # 새 스프레드 시트에 적정원엔환율과 현재원엔환율 데이터만 쌓고 불러오기(값만 복사해서 테스트해보기)
    # 스프레드시트 데이터 가져오기
    result_a = service.spreadsheets().values().get(spreadsheetId=SPREADSHEET_ID, range=RANGE_NAME_a).execute()
    rows_a = result_a.get('values', [])

    df_a = pd.DataFrame(rows_a, columns=['현재날짜', '적정원엔환율', '현재원엔환율'])
    df_a = df_a[['현재날짜', '적정원엔환율', '현재원엔환율']]

    df_a['현재날짜'] = pd.to_datetime(df_a['현재날짜']).dt.strftime('%d일 %H 시')

    # 데이터프레임을 역순으로 정렬하고 입력된 행 수만큼 선택
    df_a = df_a.iloc[::-1].head(num_rows).reset_index(drop=True)

    # Streamlit 앱
    st.write(f"{num_rows}시간 추세")

    # x축에 현재날짜, y축에 적정원엔환율과 현재원엔환율을 표시하는 산포도 차트
    st.scatter_chart(df_a.set_index('현재날짜')[['적정원엔환율', '현재원엔환율']])

    # st.table(df_a)

    # 스프레드시트 데이터 가져오기
    result = service.spreadsheets().values().get(spreadsheetId=SPREADSHEET_ID, range=RANGE_NAME).execute()
    rows = result.get('values', [])

    # 필요한 열만 데이터프레임으로 생성
    df = pd.DataFrame(rows, columns=['현재날짜', '기간', '적정원엔환율', None, None, '현재원엔환율'])
    df = df[['현재날짜', '적정원엔환율', '현재원엔환율']]


    # 날짜 형식 변경 (년-월-일 시:분)
    df['현재날짜'] = pd.to_datetime(df['현재날짜']).dt.strftime('%m/%d %H 시')

    # 데이터프레임을 역순으로 정렬하고 마지막 24개 행 선택
    df = df.iloc[::-1].head(num_rows).reset_index(drop=True)

    # Streamlit 앱

    # st.scatter_chart(df)
    st.table(df)

with tab2:
    st.title('원달러환율 적정환율 데이터')

    def download_data_usd(period_weeks, period_hours):
        start = datetime.today() - timedelta(weeks=period_weeks)
        end = datetime.today()

        try:
            usd_index_data = yf.download('DX-Y.NYB', start=start, end=end)
        except Exception as e:
            st.error(f"USD Index 데이터를 다운로드하는 도중 오류가 발생했습니다: {e}")
            return None, None, None

        try:
            usd_krw_data = yf.download('USDKRW=X', start=start, end=end, interval='1h')
        except Exception as e:
            st.error(f"USD/KRW 데이터를 다운로드하는 도중 오류가 발생했습니다: {e}")
            return usd_index_data, None, None

        usd_index_data.index = usd_index_data.index.tz_localize('UTC')
        usd_krw_data.index = usd_krw_data.index.tz_convert('UTC')

        now = datetime.now(pytz.utc)
        last_24_hours_data_usd = usd_krw_data[usd_krw_data.index >= (now - timedelta(hours=period_hours))]

        return usd_index_data, usd_krw_data, last_24_hours_data_usd

    def calculate_indicators_usd(usd_index_data, usd_krw_data):
        today_usd_index = round(float(usd_index_data['Close'].iloc[-1]), 2)
        today_usd_krw = round(float(usd_krw_data['Close'].iloc[-1]), 2)
        usd_index_median = round(float(usd_index_data['Close'].median()), 2)
        usd_krw_median = round(float(usd_krw_data['Close'].median()), 2)
        usd_gap_ratio = round((today_usd_index / usd_index_median) * 100, 2)
        avg_usd_gap_ratio = round((usd_index_data['Close'] / usd_krw_data['Close']).mean() * 100, 2)
        avg_usd_index = round(float(usd_index_data['Close'].mean()), 2)
        avg_usd_krw = round(float(usd_krw_data['Close'].mean()), 2)
        usd_krw_estimate = round((today_usd_index / avg_usd_gap_ratio) * 100, 2)
        usd_gap_percentage = round(((today_usd_index - usd_index_median) / usd_index_median) * 100, 1)
        usd_gap_ratio_new = round((today_usd_index / usd_krw_median) * 100, 2)

        return {
            'today_usd_index': today_usd_index,
            'today_usd_krw': today_usd_krw,
            'usd_index_median': usd_index_median,
            'usd_krw_median': usd_krw_median,
            'usd_gap_ratio': usd_gap_ratio,
            'avg_usd_gap_ratio': avg_usd_gap_ratio,
            'avg_usd_index': avg_usd_index,
            'avg_usd_krw': avg_usd_krw,
            'usd_krw_estimate': usd_krw_estimate,
            'usd_gap_percentage': usd_gap_percentage,
            'usd_gap_ratio_new': usd_gap_ratio_new
        }

    def check_conditions_usd(indicators):
        condition1 = indicators['today_usd_krw'] < indicators['avg_usd_krw']
        condition2 = indicators['today_usd_index'] < indicators['avg_usd_index']
        condition3 = indicators['usd_gap_ratio_new'] > indicators['avg_usd_gap_ratio']
        condition4 = indicators['today_usd_krw'] < indicators['usd_krw_estimate']
        return condition1, condition2, condition3, condition4

    def calculate_exchange_rate_usd(period_weeks, period_hours=24):
        usd_index_data, usd_krw_data, last_24_hours_data_usd = download_data_usd(period_weeks, period_hours)
        
        if usd_index_data is None or usd_krw_data is None:
            return

        indicators = calculate_indicators_usd(usd_index_data, usd_krw_data)
        
        conditions = check_conditions_usd(indicators)
        suitable_conditions = sum(conditions)
        
        today_usd_krw = indicators['today_usd_krw']
        usd_krw_estimate = indicators['usd_krw_estimate']
        delta_usd = round(today_usd_krw - usd_krw_estimate, 2)
        is_fair_value_usd = today_usd_krw < usd_krw_estimate
        
        emoji_usd = "☀️" if is_fair_value_usd else "🌧️"
        status_text_usd = "적정환율" if is_fair_value_usd else "과대평가"
        
        st.metric(label=f"야후파이낸스기준 현재: {today_usd_krw} 원", value=f"{emoji_usd}", delta=f"{delta_usd} 원")
        st.write(f"현재 USD/KRW 환율은 {usd_krw_estimate} 원의 적정환율과 비교하여 {status_text_usd}되어 있습니다.")
        
        condition_labels_usd = [
            '조건1 (현재 USD/KRW 환율 < 4주 평균 환율)',
            '조건2 (현재 USD 인덱스 < 4주 평균 USD 인덱스)',
            '조건3 (현재 USD 갭 비율 > 4주 평균 USD 갭 비율)',
            '조건4 (현재 USD/KRW 환율 < 적정 USD/KRW 환율)'
        ]
        
        for label, condition in zip(condition_labels_usd, conditions):
            condition_status = "✅" if condition else "❌"
            st.write(f"{label}: {condition_status}")

    calculate_exchange_rate_usd(4)

    # 추세 그래프 데이터 가져오기
    SERVICE_ACCOUNT_FILE = 'dollainvestingtool-1a7b13d623dd.json'

    SPREADSHEET_ID = '1iw-NdSsOOg63Q3dOQWVdY6FzW1fOuYGkIuX1Wx-wy0Q'
    RANGE_NAME_USD = '달러_4주!A2:F'

    RANGE_NAME_USD_a = '달러_4주_환율만!A2:F'

    creds = service_account.Credentials.from_service_account_file(
        SERVICE_ACCOUNT_FILE, scopes=SCOPES)

    service = build('sheets', 'v4', credentials=creds)

    result_usd_a = service.spreadsheets().values().get(spreadsheetId=SPREADSHEET_ID, range=RANGE_NAME_USD_a).execute()
    rows_usd_a = result_usd_a.get('values', [])

    df_usd_a = pd.DataFrame(rows_usd_a, columns=['적정원달러환율', '현재원달러환율'])
    df_usd_a = df_usd_a[['적정원달러환율', '현재원달러환율']]

    df_usd_a = df_usd_a.iloc[::-1].head(24).reset_index(drop=True)

    st.write('24시간추세')
    st.scatter_chart(df_usd_a)

    result_usd = service.spreadsheets().values().get(spreadsheetId=SPREADSHEET_ID, range=RANGE_NAME_USD).execute()
    rows_usd = result_usd.get('values', [])

    df_usd = pd.DataFrame(rows_usd, columns=['현재날짜', '기간', '적정원달러', None, None, '현재원달러환율'])
    df_usd = df_usd[['현재날짜', '적정원달러', '현재원달러환율']]

    # df_usd['현재날짜'] = pd.to_datetime(df_usd['현재날짜']).dt.strftime('%m/%d %H 시')

    df_usd = df_usd.iloc[::-1].head(24).reset_index(drop=True)

    st.table(df_usd)


    
# with tab3:
#     st.title('금시세 데이터')