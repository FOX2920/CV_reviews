import streamlit as st
import pandas as pd
import requests
from bs4 import BeautifulSoup
import datetime
import os

st.set_page_config(page_title="Công cụ thu thập đánh giá ứng viên", layout="wide")

st.title("Công cụ thu thập đánh giá ứng viên")
st.markdown("Thu thập và phân tích đánh giá ứng viên từ Base API")

# API Key input or use default
api_key = os.getenv("BASE_API_KEY")

def get_base_openings(api_key):
    """Truy xuất vị trí tuyển dụng đang hoạt động từ Base API"""
    url = "https://hiring.base.vn/publicapi/v2/opening/list"

    payload = {
        'access_token': api_key,
    }

    response = requests.post(url, data=payload)

    if response.status_code == 200:
        data = response.json()
        openings = data.get('openings', [])

        # Lọc vị trí với trạng thái '10' (đang hoạt động)
        filtered_openings = [
            {"id": opening['id'], "name": opening['name']}
            for opening in openings
            if opening.get('status') == '10'
        ]

        # Tạo DataFrame
        df = pd.DataFrame(filtered_openings)
        return df
    else:
        st.error(f"Lỗi: {response.status_code} - {response.text}")
        return pd.DataFrame()

def extract_message(evaluations):
    """Trích xuất nội dung văn bản từ đánh giá HTML"""
    if isinstance(evaluations, list) and len(evaluations) > 0:
        raw_html = evaluations[0].get('content', '')  # Lấy HTML thô từ nội dung
        soup = BeautifulSoup(raw_html, "html.parser")  # Phân tích HTML
        text = " ".join(soup.stripped_strings)  # Lấy tất cả nội dung văn bản
        return text
    return None  # Trả về None nếu không có dữ liệu

def get_candidates_for_opening(opening_id, api_key, start_date, end_date):
    """Truy xuất ứng viên cho một vị trí tuyển dụng cụ thể trong khoảng thời gian"""
    url = "https://hiring.base.vn/publicapi/v2/candidate/list"

    payload = {
        'access_token': api_key,
        'opening_id': opening_id,
        'start_date': start_date.strftime('%Y-%m-%d'),
        'end_date': end_date.strftime('%Y-%m-%d') if end_date else ''
    }
    headers = {
        'Content-Type': 'application/x-www-form-urlencoded'
    }

    response = requests.post(url, headers=headers, data=payload)

    if response.status_code == 200:
        data = response.json()
        if 'candidates' in data and data['candidates']:
            candidate_data = data['candidates']
            df = pd.DataFrame(candidate_data)

            # Thêm opening_id như một cột để tham chiếu
            df['opening_id'] = opening_id

            # Trích xuất nội dung đánh giá
            df['review'] = df['evaluations'].apply(extract_message)

            return df
        else:
            st.info(f"Không tìm thấy ứng viên nào cho vị trí ID: {opening_id}")
            return pd.DataFrame({'opening_id': [opening_id]})
    else:
        st.error(f"Lỗi cho vị trí ID {opening_id}: {response.status_code}, {response.text}")
        return pd.DataFrame()

def process_form_data(df):
    """Xử lý dữ liệu biểu mẫu để làm phẳng cấu trúc"""
    if df.empty or 'form' not in df.columns:
        return df
    
    # Trích xuất dữ liệu biểu mẫu
    form_data_list = df['form']
    df['CV'] = df['cvs'].apply(lambda x: x[0] if len(x) > 0 else None)
    # Chuyển đổi mỗi hàng trong cột 'form' thành một từ điển
    form_df_list = []
    for form_data in form_data_list:
        if isinstance(form_data, list):
            data_dict = {item['id']: item['value'] for item in form_data}
            form_df_list.append(data_dict)
        else:
            form_df_list.append({})
    
    # Tạo DataFrame mới từ danh sách các từ điển
    form_df_transformed = pd.DataFrame(form_df_list)
    display_columns = ['id', 'name', 'gender', 'job', 'CV', 'email', 'phone', 'review', 'form']
    display_columns = [col for col in display_columns if col in df.columns]
    df = df[display_columns]
    # Kết hợp form_df_transformed với df ban đầu theo chiều ngang
    df_merged = pd.concat([df.drop(columns=['form']), form_df_transformed], axis=1)
    
    return df_merged

def process_cvs_data(df):
    """Xử lý dữ liệu CV để trích xuất CV đầu tiên nếu có"""
    if df.empty or 'cvs' not in df.columns:
        return df
    
    df['cvs'] = df['cvs'].apply(lambda x: x[0] if isinstance(x, list) and len(x) > 0 else None)
    return df

# Lựa chọn ngày
col1, col2 = st.columns(2)
with col1:
    start_date = st.date_input("Ngày bắt đầu", datetime.date.today() - datetime.timedelta(days=30))
with col2:
    end_date = st.date_input("Ngày kết thúc", datetime.date.today())

# Đảm bảo ngày kết thúc không trước ngày bắt đầu
if start_date > end_date:
    st.error("Lỗi: Ngày kết thúc phải sau ngày bắt đầu")
    st.stop()

# Tải vị trí công việc
with st.spinner("Đang tải vị trí công việc..."):
    openings_df = get_base_openings(api_key)

if not openings_df.empty:
    # Thêm tùy chọn "Tất cả" vào đầu
    job_options = ["Tất cả"] + openings_df['name'].tolist()
    
    # Lựa chọn công việc
    selected_job = st.selectbox("Chọn vị trí công việc", job_options)
    
    if st.button("Thu thập dữ liệu"):
        all_candidates = []
        
        with st.spinner("Đang thu thập dữ liệu ứng viên..."):
            if selected_job == "Tất cả":
                # Xử lý tất cả vị trí công việc
                progress_bar = st.progress(0)
                for idx, (index, row) in enumerate(openings_df.iterrows()):
                    opening_id = row['id']
                    opening_name = row['name']
                    
                    st.write(f"Đang truy xuất ứng viên cho: {opening_name}")
                    candidates_df = get_candidates_for_opening(opening_id, api_key, start_date, end_date)
                    
                    if not candidates_df.empty and 'id' in candidates_df.columns:
                        candidates_df['job'] = opening_name
                        all_candidates.append(candidates_df)
                    
                    # Cập nhật tiến trình
                    progress_bar.progress((idx + 1) / len(openings_df))
            else:
                # Chỉ xử lý công việc đã chọn
                selected_opening = openings_df[openings_df['name'] == selected_job].iloc[0]
                opening_id = selected_opening['id']
                opening_name = selected_opening['name']
                
                st.write(f"Đang truy xuất ứng viên cho: {opening_name}")
                candidates_df = get_candidates_for_opening(opening_id, api_key, start_date, end_date)
                
                if not candidates_df.empty and 'id' in candidates_df.columns:
                    candidates_df['job'] = opening_name
                    all_candidates.append(candidates_df)
        
        # Kết hợp tất cả ứng viên vào một DataFrame
        if all_candidates:
            # Nối tất cả dataframe ứng viên
            combined_df = pd.concat(all_candidates, ignore_index=True)
            
            # Xử lý dữ liệu biểu mẫu và CV
            processed_df = process_form_data(combined_df)
            processed_df = process_cvs_data(processed_df)
            
            # Lọc ứng viên có đánh giá
            final_df = processed_df[processed_df['review'].notna()]
            
            if not final_df.empty:
                # Hiển thị thống kê
                st.subheader("Thống kê ứng viên")
                stats = final_df.groupby('job').size().reset_index(name='số_lượng_ứng_viên')
                st.dataframe(stats)
                
                # Hiển thị các cột chính quan tâm
                st.subheader("Dữ liệu ứng viên")
                st.dataframe(final_df)
                
                # Tùy chọn tải xuống
                csv = final_df.to_csv(index=False, encoding="utf-8-sig")
                st.download_button(
                    label="Tải dữ liệu dưới dạng CSV",
                    data=csv,
                    file_name=f"danh_gia_ung_vien_{start_date}_{end_date}.csv",
                    mime="text/csv",
                )
            else:
                st.warning("Không tìm thấy ứng viên nào có đánh giá trong khoảng thời gian đã chọn.")
        else:
            st.warning("Không có dữ liệu ứng viên nào cho tiêu chí đã chọn.")
else:
    st.error("Không thể tải vị trí công việc. Vui lòng kiểm tra API key và thử lại.")

# Thêm thông tin trong thanh bên
st.sidebar.title("Giới thiệu")
st.sidebar.info(
    "Ứng dụng này thu thập dữ liệu đánh giá ứng viên từ Base API. "
    "Chọn khoảng thời gian và vị trí công việc để truy xuất các ứng viên đã được đánh giá bởi HR."
)
st.sidebar.markdown("---")
