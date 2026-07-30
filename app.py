import os
import sys
import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

# --- ATTEMPT LIBSQL IMPORT FOR TURSO CLOUD ---
try:
    import libsql_client
    HAS_TURSO = True
except ImportError:
    import sqlite3
    HAS_TURSO = False

# --- PATH & FILE HELPER ---
def get_resource_path(relative_path):
    """Get absolute path to resource, works for dev and PyInstaller / Streamlit Cloud."""
    base_path = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base_path, relative_path)

DB_FILE = get_resource_path("irish_tax_compliance.db")

# --- PAGE CONFIGURATION ---
st.set_page_config(
    page_title="Irish Tax Compliance Dashboard",
    page_icon="🍀",
    layout="wide"
)

# --- CSS STYLING FOR EQUAL KPI CARDS & UI ---
st.markdown("""
<style>
    div[data-testid="stMetric"] {
        background-color: #f8f9fa;
        border: 1px solid #e9ecef;
        padding: 15px 20px;
        border-radius: 10px;
        box-shadow: 0 2px 4px rgba(0,0,0,0.05);
        min-height: 110px;
        display: flex;
        flex-direction: column;
        justify-content: center;
    }
    div[data-testid="stMetricLabel"] {
        font-weight: 600;
        color: #495057;
    }
</style>
""", unsafe_allow_html=True)

# --- CUSTOM REACT PIE CHART COMPONENT ---
def render_custom_pie_chart(counts_dict, key=None):
    """Renders custom React Pie Chart component if built folder exists."""
    component_path = get_resource_path("pie_chart_component")
    build_path = os.path.join(component_path, "build")

    if os.path.exists(build_path):
        pie_chart_func = components.declare_component("pie_chart_component", path=build_path)
        return pie_chart_func(counts=counts_dict, key=key)
    else:
        st.info("Custom Pie Chart component build directory not found. Standard UI enabled.")
        return None

# --- DATABASE CONNECTION HELPERS ---
def query_turso(query_str, params=()):
    """Executes SELECT query on Turso Cloud using libsql-client."""
    turso_url = st.secrets.get("TURSO_DATABASE_URL")
    turso_token = st.secrets.get("TURSO_AUTH_TOKEN")
    
    if turso_url.startswith("libsql://"):
        turso_url = turso_url.replace("libsql://", "https://")
        
    with libsql_client.create_client_sync(turso_url, auth_token=turso_token) as client:
        rs = client.execute(query_str, params)
        columns = rs.columns
        rows = [dict(zip(columns, row)) for row in rs.rows]
        return pd.DataFrame(rows)

def execute_turso(query_str, params=()):
    """Executes UPDATE/INSERT statement on Turso Cloud."""
    turso_url = st.secrets.get("TURSO_DATABASE_URL")
    turso_token = st.secrets.get("TURSO_AUTH_TOKEN")
    
    if turso_url.startswith("libsql://"):
        turso_url = turso_url.replace("libsql://", "https://")

    with libsql_client.create_client_sync(turso_url, auth_token=turso_token) as client:
        client.execute(query_str, params)

# --- DATE FORMATTER ---
def format_dataframe_dates(df):
    """Formats date columns cleanly."""
    for col in df.columns:
        if 'date' in col.lower() or 'due' in col.lower() or 'period' in col.lower():
            try:
                df[col] = pd.to_datetime(df[col]).dt.strftime('%Y-%m-%d')
            except Exception:
                pass
    return df

# --- COMPLIANCE STATUS LOGIC ---
def assign_status_ct(row):
    filed = str(row.get('CTR Filled', '')).strip().lower()
    days = row.get('DAYS Remaining')
    if filed == 'yes': return 'Filed'
    if pd.isna(days): return 'Pending / No Data'
    if days < 0: return 'Late'
    elif days <= 15: return 'Critical (<15 Days)'
    elif days <= 30: return 'Warning (<30 Days)'
    else: return 'Safe (>30 Days)'

def assign_status_cro(row):
    filed = str(row.get('CORE FILED', '')).strip().lower()
    days = row.get('Remaining Days')
    if filed == 'yes': return 'Filed'
    if pd.isna(days): return 'Pending / No Data'
    if days < 0: return 'Late'
    elif days <= 15: return 'Critical (<15 Days)'
    elif days <= 30: return 'Warning (<30 Days)'
    else: return 'Safe (>30 Days)'

# --- DATA LOADING FUNCTION ---
@st.cache_data(ttl=15)
def load_compliance_data():
    turso_url = st.secrets.get("TURSO_DATABASE_URL", None)
    
    if HAS_TURSO and turso_url:
        df_ct = query_turso("SELECT * FROM corporation_tax")
        df_cro = query_turso("SELECT * FROM cro_annual_returns")
    else:
        import sqlite3
        conn = sqlite3.connect(DB_FILE)
        df_ct = pd.read_sql_query("SELECT * FROM corporation_tax", conn)
        df_cro = pd.read_sql_query("SELECT * FROM cro_annual_returns", conn)
        conn.close()

    df_ct = format_dataframe_dates(df_ct)
    df_cro = format_dataframe_dates(df_cro)

    df_ct['Compliance_Status'] = df_ct.apply(assign_status_ct, axis=1)
    df_cro['Compliance_Status'] = df_cro.apply(assign_status_cro, axis=1)

    return df_ct, df_cro

# --- RENDER DASHBOARD TABS ---
def render_compliance_page(df, title, filed_col_name, days_col, key_prefix):
    st.title(f"🍀 {title}")

    # Metrics Overview
    c1, c2, c3, c4 = st.columns(4)
    total_records = len(df)
    filed_count = len(df[df[filed_col_name].str.strip().str.lower() == 'yes'])
    critical_count = len(df[df['Compliance_Status'] == 'Critical (<15 Days)'])
    late_count = len(df[df['Compliance_Status'] == 'Late'])

    c1.metric("Total Returns", total_records)
    c2.metric("Filed", filed_count)
    c3.metric("Critical (<15 Days)", critical_count)
    c4.metric("Overdue / Late", late_count)

    st.markdown("---")

    # Status Distribution & Custom Pie Chart
    col_chart, col_filter = st.columns([1, 2])
    
    with col_chart:
        st.subheader("Compliance Breakdown")
        status_counts = df['Compliance_Status'].value_counts().to_dict()
        chart_selection = render_custom_pie_chart(status_counts, key=f"pie_{key_prefix}")

    with col_filter:
        st.subheader("Filter Options")
        status_list = list(df['Compliance_Status'].unique())
        selected_statuses = st.multiselect("Filter by Compliance Status:", status_list, default=status_list, key=f"filter_{key_prefix}")
        
        search_query = st.text_input("🔍 Search Company Name:", key=f"search_{key_prefix}")

    # Filter Application
    filtered_df = df[df['Compliance_Status'].isin(selected_statuses)]
    if search_query:
        filtered_df = filtered_df[filtered_df['Company Name'].str.contains(search_query, case=False, na=False)]

    if chart_selection:
        filtered_df = filtered_df[filtered_df['Compliance_Status'] == chart_selection]

    st.markdown("---")

    # Editable Table Section
    st.subheader("Data Records")
    enable_editing = st.toggle("Enable Direct Grid Editing", key=f"toggle_{key_prefix}")

    grid_display_df = filtered_df.drop(columns=['Compliance_Status'], errors='ignore')

    if enable_editing:
        st.info("💡 Edit cells directly below and click **Save Grid Changes** to persist updates.")
        edited_df = st.data_editor(
            grid_display_df,
            use_container_width=True,
            num_rows="fixed",
            key=f"editor_{key_prefix}"
        )

        if st.button("💾 Save Grid Changes", key=f"save_btn_{key_prefix}", type="primary"):
            table_db_name = "corporation_tax" if key_prefix == "ct" else "cro_annual_returns"
            updated_count = 0
            turso_url = st.secrets.get("TURSO_DATABASE_URL", None)

            if HAS_TURSO and turso_url:
                for idx in edited_df.index:
                    orig_row = grid_display_df.loc[idx]
                    new_row = edited_df.loc[idx]

                    if not orig_row.equals(new_row):
                        company_name = new_row['Company Name']
                        filed_val = new_row.get(filed_col_name, 'No')
                        days_val = int(new_row.get(days_col, 0))

                        sql_cmd = f'UPDATE {table_db_name} SET "{filed_col_name}" = ?, "{days_col}" = ? WHERE "Company Name" = ?'
                        execute_turso(sql_cmd, (filed_val, days_val, company_name))
                        updated_count += 1
            else:
                import sqlite3
                conn = sqlite3.connect(DB_FILE)
                cursor = conn.cursor()
                for idx in edited_df.index:
                    orig_row = grid_display_df.loc[idx]
                    new_row = edited_df.loc[idx]

                    if not orig_row.equals(new_row):
                        company_name = new_row['Company Name']
                        filed_val = new_row.get(filed_col_name, 'No')
                        days_val = int(new_row.get(days_col, 0))

                        cursor.execute(f'UPDATE {table_db_name} SET "{filed_col_name}" = ?, "{days_col}" = ? WHERE "Company Name" = ?', (filed_val, days_val, company_name))
                        updated_count += 1
                conn.commit()
                conn.close()

            if updated_count > 0:
                st.cache_data.clear()
                st.toast(f"🎉 Successfully saved {updated_count} record(s)!", icon="✅")
                st.rerun()
    else:
        st.dataframe(grid_display_df, use_container_width=True)


# --- MAIN APP ROUTING ---
def main():
    try:
        df_ct, df_cro = load_compliance_data()
    except Exception as e:
        st.error(f"Error loading database: {e}")
        return

    tab1, tab2 = st.tabs(["📊 CT1 Corporation Tax", "🏢 CRO Annual Returns"])

    with tab1:
        render_compliance_page(df_ct, "CT1 Corporation Tax Compliance", "CTR Filled", "DAYS Remaining", "ct")

    with tab2:
        render_compliance_page(df_cro, "CRO Annual Returns Compliance", "CORE FILED", "Remaining Days", "cro")

if __name__ == "__main__":
    main()