import streamlit as st
import pandas as pd
import requests
from bs4 import BeautifulSoup
import datetime
import os

st.set_page_config(page_title="Candidate Review Collector", layout="wide")

st.title("Candidate Review Collection Tool")
st.markdown("Collect and analyze candidate reviews from Base API")

# API Key input or use default
api_key = os.getenv("BASE_API_KEY")

def get_base_openings(api_key):
    """Retrieve active job openings from Base API"""
    url = "https://hiring.base.vn/publicapi/v2/opening/list"

    payload = {
        'access_token': api_key,
    }

    response = requests.post(url, data=payload)

    if response.status_code == 200:
        data = response.json()
        openings = data.get('openings', [])

        # Filter openings with status '10' (active)
        filtered_openings = [
            {"id": opening['id'], "name": opening['name']}
            for opening in openings
            if opening.get('status') == '10'
        ]

        # Create DataFrame
        df = pd.DataFrame(filtered_openings)
        return df
    else:
        st.error(f"Error: {response.status_code} - {response.text}")
        return pd.DataFrame()

def extract_message(evaluations):
    """Extract text content from HTML evaluations"""
    if isinstance(evaluations, list) and len(evaluations) > 0:
        raw_html = evaluations[0].get('content', '')  # Get raw HTML from content
        soup = BeautifulSoup(raw_html, "html.parser")  # Parse HTML
        text = " ".join(soup.stripped_strings)  # Get all text content
        return text
    return None  # Return None if no data

def get_candidates_for_opening(opening_id, api_key, start_date, end_date):
    """Retrieve candidates for a specific job opening within date range"""
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

            # Add opening_id as a column for reference
            df['opening_id'] = opening_id

            # Extract review content
            df['review'] = df['evaluations'].apply(extract_message)

            return df
        else:
            st.info(f"No candidates found for opening ID: {opening_id}")
            return pd.DataFrame({'opening_id': [opening_id]})
    else:
        st.error(f"Error for opening ID {opening_id}: {response.status_code}, {response.text}")
        return pd.DataFrame()

def process_form_data(df):
    """Process form data to flatten the structure"""
    if df.empty or 'form' not in df.columns:
        return df
    
    # Extract form data
    form_data_list = df['form']
    
    # Convert each row in 'form' column to a dictionary
    form_df_list = []
    for form_data in form_data_list:
        if isinstance(form_data, list):
            data_dict = {item['id']: item['value'] for item in form_data}
            form_df_list.append(data_dict)
        else:
            form_df_list.append({})
    
    # Create a new DataFrame from the list of dictionaries
    form_df_transformed = pd.DataFrame(form_df_list)
    
    # Merge form_df_transformed with the original df horizontally
    df_merged = pd.concat([df.drop(columns=['form']), form_df_transformed], axis=1)
    
    return df_merged

def process_cvs_data(df):
    """Process CVs data to extract the first CV if available"""
    if df.empty or 'cvs' not in df.columns:
        return df
    
    df['cvs'] = df['cvs'].apply(lambda x: x[0] if isinstance(x, list) and len(x) > 0 else None)
    return df

# Date selection
col1, col2 = st.columns(2)
with col1:
    start_date = st.date_input("Start Date", datetime.date.today() - datetime.timedelta(days=30))
with col2:
    end_date = st.date_input("End Date", datetime.date.today())

# Make sure end_date is not before start_date
if start_date > end_date:
    st.error("Error: End date must be after start date")
    st.stop()

# Load job openings
with st.spinner("Loading job openings..."):
    openings_df = get_base_openings(api_key)

if not openings_df.empty:
    # Add "All" option at the beginning
    job_options = ["All"] + openings_df['name'].tolist()
    
    # Job selection
    selected_job = st.selectbox("Select Job", job_options)
    
    if st.button("Collect Data"):
        all_candidates = []
        
        with st.spinner("Collecting candidate data..."):
            if selected_job == "All":
                # Process all job openings
                progress_bar = st.progress(0)
                for idx, (index, row) in enumerate(openings_df.iterrows()):
                    opening_id = row['id']
                    opening_name = row['name']
                    
                    st.write(f"Retrieving candidates for: {opening_name}")
                    candidates_df = get_candidates_for_opening(opening_id, api_key, start_date, end_date)
                    
                    if not candidates_df.empty and 'id' in candidates_df.columns:
                        candidates_df['job'] = opening_name
                        all_candidates.append(candidates_df)
                    
                    # Update progress
                    progress_bar.progress((idx + 1) / len(openings_df))
            else:
                # Process only the selected job
                selected_opening = openings_df[openings_df['name'] == selected_job].iloc[0]
                opening_id = selected_opening['id']
                opening_name = selected_opening['name']
                
                st.write(f"Retrieving candidates for: {opening_name}")
                candidates_df = get_candidates_for_opening(opening_id, api_key, start_date, end_date)
                
                if not candidates_df.empty and 'id' in candidates_df.columns:
                    candidates_df['job'] = opening_name
                    all_candidates.append(candidates_df)
        
        # Combine all candidates into a single DataFrame
        if all_candidates:
            # Concatenate all candidate dataframes
            combined_df = pd.concat(all_candidates, ignore_index=True)
            
            # Process the form data and CVs
            processed_df = process_form_data(combined_df)
            processed_df = process_cvs_data(processed_df)
            
            # Filter candidates that have reviews
            final_df = processed_df[processed_df['review'].notna()]
            
            if not final_df.empty:
                # Show statistics
                st.subheader("Candidate Statistics")
                stats = final_df.groupby('job').size().reset_index(name='candidate_count')
                st.dataframe(stats)
                
                # Display main columns of interest
                st.subheader("Candidate Data")
                display_columns = ['id', 'name', 'gender', 'job', 'email', 'phone', 'review']
                display_columns = [col for col in display_columns if col in final_df.columns]
                st.dataframe(final_df[display_columns])
                
                # Download option
                csv = final_df.to_csv(index=False, encoding="utf-8-sig")
                st.download_button(
                    label="Download data as CSV",
                    data=csv,
                    file_name=f"candidate_reviews_{start_date}_{end_date}.csv",
                    mime="text/csv",
                )
            else:
                st.warning("No candidates with reviews found in the selected date range.")
        else:
            st.warning("No candidate data available for the selected criteria.")
else:
    st.error("Failed to load job openings. Please check your API key and try again.")

# Add some information in the sidebar
st.sidebar.title("About")
st.sidebar.info(
    "This application collects candidate review data from Base API. "
    "Select a date range and job position to retrieve candidates that have been reviewed by HR."
)
st.sidebar.markdown("---")
st.sidebar.markdown("© 2025 HR Analytics")
