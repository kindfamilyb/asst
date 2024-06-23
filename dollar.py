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

tab1, tab2 = st.tabs(["달러", "차트분석"])


with tab1:
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

    SCOPES = ['https://www.googleapis.com/auth/spreadsheets.readonly']

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