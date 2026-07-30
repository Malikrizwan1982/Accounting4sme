import os
import sys
import sqlite3
import pandas as pd
from datetime import datetime
import streamlit as st
import streamlit.components.v1 as components

# --- PATH RESOLUTION FOR PYINSTALLER & LOCAL DEV ---
def get_resource_path(relative_path):
    """Get absolute path to resource, works for dev and for PyInstaller."""
    if getattr(sys, 'frozen', False):
        base_path = getattr(sys, '_MEIPASS', os.path.dirname(sys.executable))
    else:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

# --- PAGE CONFIGURATION ---
st.set_page_config(
    page_title="Irish Tax Filing Compliance Portal",
    page_icon="🇮🇪",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- COLOR PALETTE DEFINITION ---
COLOR_MAP = {
    'All': '#1E293B',                 # Slate Dark
    'Filed': '#0284C7',               # Sky Blue
    'Late': '#DC2626',                # Crimson Red
    'Critical (<15 Days)': '#EA580C',  # Vibrant Orange
    'Warning (<30 Days)': '#D97706',   # Amber Yellow
    'Safe (>30 Days)': '#16A34A',     # Emerald Green
    'Pending / No Data': '#64748B'    # Slate Grey
}

# --- GLOBAL CUSTOM CSS ---
st.markdown("""
<style>
    .stApp {
        background-color: #F8FAFC;
    }
    .main-header {
        background: linear-gradient(135deg, #0F172A 0%, #1E293B 100%);
        padding: 24px 32px;
        border-radius: 12px;
        color: white;
        margin-bottom: 24px;
        box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.1);
    }
    .main-header h1 {
        color: #F8FAFC !important;
        margin: 0;
        font-weight: 700;
        font-size: 2rem;
    }
    .main-header p {
        color: #94A3B8;
        margin: 4px 0 0 0;
        font-size: 0.95rem;
    }
</style>
""", unsafe_allow_html=True)

# Declare Custom Two-Way Component with proper path resolution
COMPONENT_PATH = get_resource_path("pie_chart_component")
interactive_pie_chart = components.declare_component("interactive_pie_chart", path=COMPONENT_PATH)

# --- DATABASE FETCHING & PROCESSING ---
DB_FILE = get_resource_path("irish_tax_compliance.db")

def format_dataframe_dates(df):
    """Converts datetime columns into clean DD/MM/YYYY formatted dates with no time component."""
    for col in df.columns:
        if any(keyword in col.lower() for keyword in ['date', 'due', 'period', 'ard']):
            try:
                df[col] = pd.to_datetime(df[col], errors='coerce').dt.date
            except Exception:
                pass
    return df

@st.cache_data(ttl=60)
def load_compliance_data():
    if not os.path.exists(DB_FILE):
        st.error(f"Database file not found at path: {DB_FILE}")
        st.stop()

    conn = sqlite3.connect(DB_FILE)
    df_ct = pd.read_sql_query("SELECT * FROM corporation_tax", conn)
    df_cro = pd.read_sql_query("SELECT * FROM cro_annual_returns", conn)
    conn.close()

    # Format all Date columns upfront
    df_ct = format_dataframe_dates(df_ct)
    df_cro = format_dataframe_dates(df_cro)

    def assign_status_ct(row):
        filed = str(row.get('CTR Filled', '')).strip().lower()
        days = row.get('DAYS Remaining')
        if filed == 'yes':
            return 'Filed'
        if pd.isna(days):
            return 'Pending / No Data'
        if days < 0:
            return 'Late'
        elif days <= 15:
            return 'Critical (<15 Days)'
        elif days <= 30:
            return 'Warning (<30 Days)'
        else:
            return 'Safe (>30 Days)'

    def assign_status_cro(row):
        filed = str(row.get('CORE FILED', '')).strip().lower()
        days = row.get('Remaining Days')
        if filed == 'yes':
            return 'Filed'
        if pd.isna(days):
            return 'Pending / No Data'
        if days < 0:
            return 'Late'
        elif days <= 15:
            return 'Critical (<15 Days)'
        elif days <= 30:
            return 'Warning (<30 Days)'
        else:
            return 'Safe (>30 Days)'

    df_ct['Compliance_Status'] = df_ct.apply(assign_status_ct, axis=1)
    df_cro['Compliance_Status'] = df_cro.apply(assign_status_cro, axis=1)

    return df_ct, df_cro

df_ct_raw, df_cro_raw = load_compliance_data()

# --- SIDEBAR CONTROLS ---
st.sidebar.image("https://img.icons8.com/color/96/ireland.png", width=50)
st.sidebar.title("Compliance Portal")
st.sidebar.markdown("---")

search_term = st.sidebar.text_input("🔍 Search Company Name / CRO", "")

available_sources = sorted(list(set(
    df_ct_raw['Source'].dropna().tolist() + df_cro_raw['Source'].dropna().tolist()
))) if 'Source' in df_ct_raw.columns and 'Source' in df_cro_raw.columns else []

selected_sources = st.sidebar.multiselect("Filter Lead / Source:", options=available_sources, default=[])

# Apply Sidebar Filters
df_ct = df_ct_raw.copy()
df_cro = df_cro_raw.copy()

if search_term:
    df_ct = df_ct[
        df_ct['Company Name'].astype(str).str.contains(search_term, case=False, na=False) |
        df_ct['CRO Num'].astype(str).str.contains(search_term, case=False, na=False)
    ]
    df_cro = df_cro[
        df_cro['Company Name'].astype(str).str.contains(search_term, case=False, na=False) |
        df_cro['CRO Num'].astype(str).str.contains(search_term, case=False, na=False)
    ]

if selected_sources:
    if 'Source' in df_ct.columns:
        df_ct = df_ct[df_ct['Source'].isin(selected_sources)]
    if 'Source' in df_cro.columns:
        df_cro = df_cro[df_cro['Source'].isin(selected_sources)]

# --- HEADER SECTION ---
st.markdown(f"""
    <div class="main-header">
        <h1>🇮🇪 TAX FILING COMPLIANCE PORTAL</h1>
        <p>Irish Corporate Tax (CT1) & CRO Annual Returns (B1) | Dynamic SQLite Compliance Analytics | <b>{datetime.now().strftime('%d/%m/%Y')}</b></p>
    </div>
""", unsafe_allow_html=True)


def render_compliance_page(title, df, days_col, key_prefix):
    counts = df['Compliance_Status'].value_counts()
    total = len(df)
    filed = counts.get('Filed', 0)
    late = counts.get('Late', 0)
    critical = counts.get('Critical (<15 Days)', 0)
    warning = counts.get('Warning (<30 Days)', 0)
    safe = counts.get('Safe (>30 Days)', 0)
    pending = counts.get('Pending / No Data', 0)

    state_key = f"selected_status_{key_prefix}"
    reset_counter_key = f"chart_reset_counter_{key_prefix}"

    if state_key not in st.session_state:
        st.session_state[state_key] = "All"

    if reset_counter_key not in st.session_state:
        st.session_state[reset_counter_key] = 0

    st.markdown("##### 📌 Compliance Metrics:")
    
    metrics = [
        ("ALL CLIENTS", total, "All"),
        ("FILED", filed, "Filed"),
        ("LATE", late, "Late"),
        ("CRITICAL <15D", critical, "Critical (<15 Days)"),
        ("WARNING <30D", warning, "Warning (<30 Days)"),
        ("SAFE >30D", safe, "Safe (>30 Days)"),
        ("PENDING", pending, "Pending / No Data")
    ]

    # Clean CSS Grid to make all 7 KPI buttons exactly equal in width, height, and alignment
    st.markdown(f"""
    <style>
        /* Force Streamlit column container to distribute evenly without gaps */
        div[data-testid="column"] {{
            width: 100% !important;
            flex: 1 1 0px !important;
            min-width: 0px !important;
            padding: 0 4px !important;
        }}
        
        /* Enforce exact button height, font scaling, and alignment across all cards */
        div[data-testid="column"] button {{
            width: 100% !important;
            height: 80px !important;
            min-height: 80px !important;
            max-height: 80px !important;
            display: flex !important;
            flex-direction: column !important;
            align-items: center !important;
            justify-content: center !important;
            padding: 8px !important;
            border-radius: 8px !important;
            margin: 0 !important;
        }}

        div[data-testid="column"] button p {{
            font-size: 0.82rem !important;
            font-weight: 700 !important;
            letter-spacing: 0.5px !important;
            line-height: 1.2 !important;
            text-align: center !important;
            white-space: pre-wrap !important;
            margin: 0 !important;
        }}
    </style>
    """, unsafe_allow_html=True)

    # Render KPI Cards in equal columns
    cols = st.columns(7)
    for idx, (col, (label, val, status_val)) in enumerate(zip(cols, metrics)):
        bg_color = COLOR_MAP.get(status_val, '#64748B')
        is_active = (st.session_state[state_key] == status_val)
        border_style = "3px solid #0F172A" if is_active else "1px solid rgba(255,255,255,0.2)"
        box_shadow = "0 6px 12px rgba(0,0,0,0.2)" if is_active else "0 2px 4px rgba(0,0,0,0.08)"
        
        with col:
            st.markdown(f"""
            <style>
                div[data-testid="stColumn"]:nth-of-type({idx+1}) button {{
                    background-color: {bg_color} !important;
                    border: {border_style} !important;
                    box-shadow: {box_shadow} !important;
                }}
                div[data-testid="stColumn"]:nth-of-type({idx+1}) button:hover {{
                    transform: translateY(-2px) !important;
                    filter: brightness(1.1) !important;
                }}
            </style>
            """, unsafe_allow_html=True)
            
            button_text = f"{label}\n{val}"
            if st.button(button_text, key=f"kpi_btn_{key_prefix}_{idx}"):
                st.session_state[state_key] = status_val
                st.session_state[reset_counter_key] += 1
                st.rerun()

    st.markdown("---")

    # --- TWO-WAY INTERACTIVE CHART COMPONENT ---
    df_counts = pd.DataFrame({'Status': counts.index, 'Count': counts.values})
    
    labels_js = list(df_counts['Status'])
    values_js = [int(v) for v in df_counts['Count']]
    colors_js = [COLOR_MAP.get(s, '#64748B') for s in labels_js]
    pull_js = [0.12 if s == st.session_state[state_key] else 0 for s in labels_js]

    chart_key = f"pie_{key_prefix}_{st.session_state[reset_counter_key]}"

    clicked_slice = interactive_pie_chart(
        labels=labels_js,
        values=values_js,
        colors=colors_js,
        pull=pull_js,
        title=f"{title} Compliance Status Breakup",
        selected_status=st.session_state[state_key],
        key=chart_key
    )

    if clicked_slice and clicked_slice != st.session_state[state_key]:
        st.session_state[state_key] = clicked_slice
        st.rerun()

    st.markdown("---")

    # --- STREAMLIT GRID SECTION ---
    current_status = st.session_state[state_key]
    if current_status == "All":
        filtered_df = df.copy()
        table_title = f"📋 Full Records ({len(filtered_df)} Companies)"
    else:
        filtered_df = df[df['Compliance_Status'] == current_status].copy()
        table_title = f"📋 Filtered Records: **{current_status}** ({len(filtered_df)} Companies)"

    col_title, col_edit_toggle, col_reset = st.columns([0.55, 0.25, 0.20])
    
    with col_title:
        st.markdown(f"### {table_title}")
        
    with col_edit_toggle:
        edit_mode = st.toggle("✏️ Enable Direct Grid Editing", value=False, key=f"toggle_edit_{key_prefix}")

    with col_reset:
        if current_status != "All":
            if st.button("🔄 Clear Filter (Show All)", key=f"reset_btn_{key_prefix}"):
                st.session_state[state_key] = "All"
                st.session_state[reset_counter_key] += 1
                st.rerun()

    if not filtered_df.empty:
        if days_col in filtered_df.columns:
            filtered_df = filtered_df.sort_values(by=days_col, ascending=True)

        grid_display_df = filtered_df.drop(columns=['Compliance_Status'], errors='ignore')
        filed_col_name = "CTR Filled" if key_prefix == "ct" else "CORE FILED"
        
        column_configs = {
            "Company Name": st.column_config.TextColumn("Company Name"),
            "CRO Num": st.column_config.TextColumn("CRO Number"),
            filed_col_name: st.column_config.SelectboxColumn(
                "Filed Status",
                options=["Yes", "No"],
                required=True
            ),
            days_col: st.column_config.NumberColumn(
                "Days Remaining",
                step=1,
                format="%d"
            )
        }

        for col in grid_display_df.columns:
            if any(keyword in col.lower() for keyword in ['date', 'due', 'period', 'ard']):
                column_configs[col] = st.column_config.DateColumn(
                    label=col,
                    format="DD/MM/YYYY"
                )

        if edit_mode:
            st.info("💡 **Interactive Grid Active:** Double-click cells to modify values, then click **'Save Grid Changes'** below.")
            
            edited_df = st.data_editor(
                grid_display_df,
                height=480,
                hide_index=True,
                use_container_width=True,
                column_config=column_configs,
                key=f"grid_editor_{key_prefix}_{st.session_state[reset_counter_key]}"
            )

            if st.button("💾 Save Grid Changes", key=f"save_grid_btn_{key_prefix}", type="primary"):
                conn = sqlite3.connect(DB_FILE)
                cursor = conn.cursor()
                
                table_db_name = "corporation_tax" if key_prefix == "ct" else "cro_annual_returns"
                updated_count = 0
                
                for idx in edited_df.index:
                    orig_row = grid_display_df.loc[idx]
                    new_row = edited_df.loc[idx]

                    if not orig_row.equals(new_row):
                        company_name = new_row['Company Name']
                        filed_val = new_row.get(filed_col_name, 'No')
                        days_val = new_row.get(days_col, 0)

                        cursor.execute(f"""
                            UPDATE {table_db_name}
                            SET "{filed_col_name}" = ?, "{days_col}" = ?
                            WHERE "Company Name" = ?
                        """, (filed_val, days_val, company_name))
                        
                        updated_count += 1

                conn.commit()
                conn.close()

                if updated_count > 0:
                    st.cache_data.clear()
                    st.toast(f"🎉 Successfully updated {updated_count} record(s) in SQLite database!", icon="✅")
                    st.rerun()
                else:
                    st.warning("No changes detected in the grid.")

        else:
            st.dataframe(
                grid_display_df,
                height=480,
                hide_index=True,
                use_container_width=True,
                column_config=column_configs
            )
    else:
        st.info(f"No records found for compliance status '{current_status}'.")


# --- MAIN TABS ---
tab_ct, tab_cro = st.tabs([
    "🏛️ CT1 Master Data", 
    "📜 CRO Master Data"
])

with tab_ct:
    render_compliance_page("Corporation Tax (CT1)", df_ct, 'DAYS Remaining', 'ct')

with tab_cro:
    render_compliance_page("CRO Annual Returns (B1)", df_cro, 'Remaining Days', 'cro')