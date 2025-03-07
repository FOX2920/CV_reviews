import streamlit as st
import pandas as pd
import requests
from bs4 import BeautifulSoup
import datetime
import os

st.set_page_config(page_title="Công cụ thu thập đánh giá ứng viên", layout="wide")

st.title("Công cụ thu thập đánh giá ứng viên")
st.markdown("Thu thập và phân tích đánh giá ứng viên từ Base API")

api_key = os.getenv("BASE_API_KEY")

def get_base_openings(api_key):
    url = "https://hiring.base.vn/publicapi/v2/opening/list"
    payload = {'access_token': api_key}
    response = requests.post(url, data=payload)
    if response.status_code == 200:
        data = response.json()
        openings = data.get('openings', [])
        filtered_openings = [
            {"id": opening['id'], "name": opening['name']}
            for opening in openings if opening.get('status') == '10'
        ]
        return pd.DataFrame(filtered_openings)
    else:
        st.error(f"Lỗi: {response.status_code} - {response.text}")
        return pd.DataFrame()

def extract_message(evaluations):
    if isinstance(evaluations, list) and len(evaluations) > 0:
        raw_html = evaluations[0].get('content', '')
        soup = BeautifulSoup(raw_html, "html.parser")
        return " ".join(soup.stripped_strings)
    return None

def get_candidates_for_opening(opening_id, api_key, start_date, end_date):
    url = "https://hiring.base.vn/publicapi/v2/candidate/list"
    payload = {
        'access_token': api_key,
        'opening_id': opening_id,
        'start_date': start_date.strftime('%Y-%m-%d'),
        'end_date': end_date.strftime('%Y-%m-%d') if end_date else ''
    }
    response = requests.post(url, data=payload)
    if response.status_code == 200:
        data = response.json()
        df = pd.DataFrame(data.get('candidates', []))
        df['opening_id'] = opening_id
        df['review'] = df['evaluations'].apply(extract_message)
        return df
    else:
        st.error(f"Lỗi cho vị trí ID {opening_id}: {response.status_code}, {response.text}")
        return pd.DataFrame()

col1, col2 = st.columns(2)
with col1:
    start_date = st.date_input("Ngày bắt đầu", datetime.date.today() - datetime.timedelta(days=30))
with col2:
    end_date = st.date_input("Ngày kết thúc", datetime.date.today())

if start_date > end_date:
    st.error("Lỗi: Ngày kết thúc phải sau ngày bắt đầu")
    st.stop()

with st.spinner("Đang tải vị trí công việc..."):
    openings_df = get_base_openings(api_key)

if not openings_df.empty:
    job_options = ["Tất cả"] + openings_df['name'].tolist()
    selected_job = st.selectbox("Chọn vị trí công việc", job_options)
    review_filter = st.radio("Lọc ứng viên theo review:", ["Có review", "Không có review", "Cả hai"], index=2)
    
    if st.button("Thu thập dữ liệu"):
        all_candidates = []
        with st.spinner("Đang thu thập dữ liệu ứng viên..."):
            if selected_job == "Tất cả":
                for _, row in openings_df.iterrows():
                    df = get_candidates_for_opening(row['id'], api_key, start_date, end_date)
                    if not df.empty:
                        df['job'] = row['name']
                        all_candidates.append(df)
            else:
                opening_id = openings_df[openings_df['name'] == selected_job].iloc[0]['id']
                df = get_candidates_for_opening(opening_id, api_key, start_date, end_date)
                if not df.empty:
                    df['job'] = selected_job
                    all_candidates.append(df)
        
        if all_candidates:
            final_df = pd.concat(all_candidates, ignore_index=True)
            if review_filter == "Có review":
                final_df = final_df[final_df['review'].notna()]
            elif review_filter == "Không có review":
                final_df = final_df[final_df['review'].isna()]
            
            if not final_df.empty:
                st.subheader("Dữ liệu ứng viên")
                st.dataframe(final_df)
                csv = final_df.to_csv(index=False, encoding="utf-8-sig")
                st.download_button("Tải dữ liệu CSV", csv, "ung_vien.csv", "text/csv")
            else:
                st.warning("Không tìm thấy ứng viên theo tiêu chí lọc.")
        else:
            st.warning("Không có dữ liệu ứng viên nào.")
else:
    st.error("Không thể tải vị trí công việc.")
