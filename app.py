import os
import sys
import pandas as pd
import base64
from datetime import datetime, date
import streamlit as st
import streamlit.components.v1 as components

# --- ATTEMPT LIBSQL IMPORT FOR TURSO CLOUD ---
try:
    import libsql_client
    HAS_TURSO = True
except ImportError:
    import sqlite3
    HAS_TURSO = False

# --- PATH RESOLUTION ---
def get_resource_path(relative_path):
    """Get absolute path to resource, works for dev and Streamlit Cloud."""
    base_path = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base_path, relative_path)

def get_base64_image(image_path):
    """Encodes a local image to base64 for embedding in HTML templates."""
    if os.path.exists(image_path):
        with open(image_path, "rb") as img_file:
            return base64.b64encode(img_file.read()).decode()
    return ""

# --- PAGE CONFIGURATION ---
st.set_page_config(
    page_title="A4SE Tax Filing Compliance Portal",
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
        display: flex;
        justify-content: space-between;
        align-items: center;
    }
    .main-header-content {
        flex: 1;
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
    .header-logo-right {
        max-height: 75px;
        width: auto;
        border-radius: 8px;
        background-color: white;
        padding: 6px;
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.2);
    }
    .sidebar-contact-card {
        background-color: #FFFFFF;
        border: 1px solid #E2E8F0;
        border-radius: 8px;
        padding: 12px;
        margin-top: 16px;
        font-size: 0.85rem;
        color: #334155;
    }
    .sidebar-contact-card a {
        color: #0284C7;
        text-decoration: none;
        font-weight: 600;
    }
    iframe[data-testid="stCustomComponentV1"] {
        width: 100% !important;
        max-width: 100% !important;
        overflow: visible !important;
    }
</style>
""", unsafe_allow_html=True)

# Declare Custom Two-Way Component
COMPONENT_PATH = get_resource_path("pie_chart_component")
interactive_pie_chart = components.declare_component("interactive_pie_chart", path=COMPONENT_PATH)

# DB File Path & Image Paths
DB_FILE = get_resource_path("irish_tax_compliance.db")
LOGO1_PATH = get_resource_path("logo1.png")
LOGO2_PATH = get_resource_path("logo2.png")

# --- TURSO / SQLITE HELPERS ---
def query_turso(query_str, params=()):
    """Executes SELECT queries on Turso Cloud using libsql-client."""
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
    """Executes UPDATE/INSERT/DELETE statements on Turso Cloud."""
    turso_url = st.secrets.get("TURSO_DATABASE_URL")
    turso_token = st.secrets.get("TURSO_AUTH_TOKEN")
    
    if turso_url.startswith("libsql://"):
        turso_url = turso_url.replace("libsql://", "https://")

    with libsql_client.create_client_sync(turso_url, auth_token=turso_token) as client:
        client.execute(query_str, params)

def execute_db_command(query_str, params=()):
    """Unified handler for C/U/D operations across Turso and local SQLite."""
    turso_url = st.secrets.get("TURSO_DATABASE_URL", None)
    if HAS_TURSO and turso_url:
        execute_turso(query_str, params)
    else:
        import sqlite3
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute(query_str, params)
        conn.commit()
        conn.close()

def format_dataframe_dates(df):
    """Converts datetime columns into clean Python date objects for DD/MM/YYYY formatting."""
    for col in df.columns:
        if any(keyword in col.lower() for keyword in ['date', 'due', 'period', 'ard', 'start', 'end']) and 'ct return' not in col.lower():
            try:
                df[col] = pd.to_datetime(df[col], errors='coerce').dt.date
            except Exception:
                pass
    return df

@st.cache_data(ttl=15)
def load_compliance_data():
    turso_url = st.secrets.get("TURSO_DATABASE_URL", None)

    if HAS_TURSO and turso_url:
        df_ct = query_turso("SELECT * FROM corporation_tax")
        df_cro = query_turso("SELECT * FROM cro_annual_returns")
    else:
        import sqlite3
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

# --- SIDEBAR CONTROLS & BRANDING ---
# Replaced Ireland flag with logo1.png in the sidebar
if os.path.exists(LOGO1_PATH):
    st.sidebar.image(LOGO1_PATH, use_container_width=True)

st.sidebar.title("A4SE WORKPLAN")
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

st.sidebar.markdown("---")
# Official Contact Section in Sidebar
st.sidebar.markdown("""
<div class="sidebar-contact-card">
    <p style="margin: 0 0 6px 0; font-weight: 700; color: #0F172A;">💼 ACCOUNTANTS 4SME</p>
    <p style="margin: 0 0 4px 0;">🌐 <a href="https://www.accountant4sme.ie" target="_blank">www.accountant4sme.ie</a></p>
    <p style="margin: 0 0 4px 0;">✉️ <a href="mailto:info@accountants4sme.ie">info@accountants4sme.ie</a></p>
    <p style="margin: 0; font-size: 0.78rem; color: #64748B;">Certified Tax Advisors & Accountants (AIA / CPA)</p>
</div>
""", unsafe_allow_html=True)

# --- HEADER SECTION WITH RIGHT-ALIGNED LOGO2 ---
logo2_b64 = get_base64_image(LOGO2_PATH)
logo2_html = f'<img src="data:image/png;base64,{logo2_b64}" class="header-logo-right" alt="A4SE Logo" />' if logo2_b64 else ''

st.markdown(f"""
    <div class="main-header">
        <div class="main-header-content">
            <h1>🇮🇪 A4SE TAX FILING COMPLIANCE PORTAL</h1>
            <p>Certified Tax Advisors & Accountants @ <b>Accountants 4SME</b> | Irish CT1 & CRO B1 Compliance | <b>{datetime.now().strftime('%d/%m/%Y')}</b></p>
        </div>
        {logo2_html}
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
    form_show_key = f"show_add_form_{key_prefix}"

    if state_key not in st.session_state:
        st.session_state[state_key] = "All"

    if reset_counter_key not in st.session_state:
        st.session_state[reset_counter_key] = 0

    if form_show_key not in st.session_state:
        st.session_state[form_show_key] = False

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

    # CSS Grid for KPI buttons with explicit white text on "ALL CLIENTS"
    st.markdown("""
    <style>
        div[data-testid="column"] {
            width: 100% !important;
            flex: 1 1 0px !important;
            min-width: 0px !important;
            padding: 0 4px !important;
        }
        
        div[data-testid="column"] button {
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
        }

        div[data-testid="column"] button p {
            font-size: 0.82rem !important;
            font-weight: 700 !important;
            letter-spacing: 0.5px !important;
            line-height: 1.2 !important;
            text-align: center !important;
            white-space: pre-wrap !important;
            margin: 0 !important;
        }

        div[data-testid="stColumn"]:nth-of-type(1) button p {
            color: #FFFFFF !important;
        }
    </style>
    """, unsafe_allow_html=True)

    # Render KPI Cards
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

    # --- CRUD FUNCTIONALITY: 1. CREATE (ADD NEW RECORD FORM) ---
    table_db_name = "corporation_tax" if key_prefix == "ct" else "cro_annual_returns"
    all_table_columns = [col for col in df.columns if col != 'Compliance_Status']

    # Toggle Button for Form
    btn_label = "❌ Close Add Record Form" if st.session_state[form_show_key] else f"➕ Add New {title} Record"
    if st.button(btn_label, key=f"toggle_add_btn_{key_prefix}", type="primary" if not st.session_state[form_show_key] else "secondary"):
        st.session_state[form_show_key] = not st.session_state[form_show_key]
        st.rerun()

    # Dynamic Form Container
    if st.session_state[form_show_key]:
        st.info(f"📋 **Add New Entry:** Fill in all fields for `{table_db_name}` below. Dates use **DD/MM/YYYY** format.")
        
        with st.container(border=True):
            form_inputs = {}
            
            # --- SPECIAL HANDLING FOR CT RETURN / PERIOD DATES ---
            if key_prefix == "ct":
                st.markdown("##### 📅 Accounting Period")
                p_col1, p_col2 = st.columns(2)
                
                with p_col1:
                    ct_start = st.date_input(
                        "CT Period Start",
                        value=date(2025, 6, 22),
                        format="DD/MM/YYYY",
                        key=f"start_date_{key_prefix}"
                    )
                with p_col2:
                    ct_end = st.date_input(
                        "CT Period End",
                        value=date(2026, 6, 22),
                        format="DD/MM/YYYY",
                        key=f"start_end_{key_prefix}"
                    )
                
                # Auto-populate CT Return as Text formatted like "22/06/2025 - 22/06/2026"
                computed_ct_return = f"{ct_start.strftime('%d/%m/%Y')} - {ct_end.strftime('%d/%m/%Y')}"
                
                # Show live generated CT Return field to the user
                st.text_input(
                    "CT Return (Auto-generated Period Text)",
                    value=computed_ct_return,
                    disabled=True,
                    help="This field is populated automatically from the start and end dates selected above."
                )
                
                # Save into dictionary for SQL query insertion
                form_inputs["CT_Period_Start"] = ct_start
                form_inputs["CT_Period_End"] = ct_end
                form_inputs["CT Return"] = computed_ct_return
                
                st.markdown("---")

            # --- REMAINING FORM FIELDS ---
            remaining_columns = [
                c for c in all_table_columns 
                if c not in ["CT_Period_Start", "CT_Period_End", "CT Return"]
            ]

            form_cols = st.columns(3)
            for idx, col_name in enumerate(remaining_columns):
                c_target = form_cols[idx % 3]
                col_lower = col_name.lower()
                
                with c_target:
                    # Selectbox logic for filing status
                    if any(term in col_lower for term in ['filled', 'filed', 'status']) and 'date' not in col_lower:
                        form_inputs[col_name] = st.selectbox(
                            f"{col_name}", 
                            options=["No", "Yes"], 
                            key=f"field_{key_prefix}_{col_name}"
                        )
                    # Single Date pickers for standard date fields
                    elif any(keyword in col_lower for keyword in ['date', 'due', 'ard']):
                        form_inputs[col_name] = st.date_input(
                            f"{col_name}", 
                            value=date.today(),
                            format="DD/MM/YYYY",
                            key=f"field_{key_prefix}_{col_name}"
                        )
                    # Number inputs
                    elif 'days' in col_lower or 'remaining' in col_lower or ('num' in col_lower and 'cro' not in col_lower):
                        form_inputs[col_name] = st.number_input(
                            f"{col_name}", 
                            step=1, 
                            value=30,
                            key=f"field_{key_prefix}_{col_name}"
                        )
                    # Text inputs for everything else
                    else:
                        is_required = "Company Name" in col_name
                        form_inputs[col_name] = st.text_input(
                            f"{col_name}{' *' if is_required else ''}", 
                            key=f"field_{key_prefix}_{col_name}"
                        )

            st.markdown("---")
            # Action Buttons: Save & Cancel
            action_col1, action_col2, _ = st.columns([0.2, 0.2, 0.6])
            
            with action_col1:
                if st.button("💾 Save Record", key=f"submit_form_{key_prefix}", type="primary", use_container_width=True):
                    comp_name_val = form_inputs.get("Company Name", "").strip() if "Company Name" in form_inputs else ""
                    if "Company Name" in form_inputs and not comp_name_val:
                        st.error("Company Name is required!")
                    else:
                        # Construct SQL Query
                        columns_str = ", ".join([f'"{c}"' for c in form_inputs.keys()])
                        placeholders = ", ".join(["?" for _ in form_inputs])
                        
                        # Format values (convert dates to ISO format YYYY-MM-DD for SQL storage)
                        formatted_values = []
                        for val in form_inputs.values():
                            if isinstance(val, (date, datetime)):
                                formatted_values.append(val.strftime('%Y-%m-%d'))
                            else:
                                formatted_values.append(val)

                        insert_sql = f'INSERT INTO {table_db_name} ({columns_str}) VALUES ({placeholders})'
                        
                        execute_db_command(insert_sql, tuple(formatted_values))
                        st.cache_data.clear()
                        st.session_state[form_show_key] = False
                        st.toast(f"🎉 Successfully inserted record into {table_db_name}!", icon="✅")
                        st.rerun()

            with action_col2:
                if st.button("❌ Cancel", key=f"cancel_form_{key_prefix}", type="secondary", use_container_width=True):
                    st.session_state[form_show_key] = False
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

    col_title, col_edit_toggle, col_reset = st.columns([0.50, 0.30, 0.20])
    
    with col_title:
        st.markdown(f"### {table_title}")
        
    with col_edit_toggle:
        edit_mode = st.toggle("✏️ Enable Direct Grid Editing (UPDATE/DELETE)", value=False, key=f"toggle_edit_{key_prefix}")

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

        # Apply strict DD/MM/YYYY formatting to all date columns in the data grid
        for col in grid_display_df.columns:
            if any(keyword in col.lower() for keyword in ['date', 'due', 'period', 'ard', 'start', 'end']) and 'ct return' not in col.lower():
                column_configs[col] = st.column_config.DateColumn(
                    label=col,
                    format="DD/MM/YYYY"
                )

        if edit_mode:
            st.info("💡 **Interactive Grid Active:** Modify cells directly to **Update**, or select row checkboxes and use the delete option below to **Delete**.")
            
            # READ & UPDATE / DELETE via data_editor
            edited_df = st.data_editor(
                grid_display_df,
                height=480,
                hide_index=True,
                use_container_width=True,
                column_config=column_configs,
                num_rows="dynamic",
                key=f"grid_editor_{key_prefix}_{st.session_state[reset_counter_key]}"
            )

            btn_col1, _ = st.columns([0.5, 0.5])

            # SAVE CHANGES (UPDATE & DELETE FROM GRID ACTION)
            with btn_col1:
                if st.button("💾 Save Grid Changes (UPDATE)", key=f"save_grid_btn_{key_prefix}", type="primary"):
                    updated_count = 0
                    
                    # Track deleted rows
                    if len(edited_df) < len(grid_display_df):
                        remaining_companies = edited_df['Company Name'].tolist()
                        deleted_rows = grid_display_df[~grid_display_df['Company Name'].isin(remaining_companies)]
                        for _, d_row in deleted_rows.iterrows():
                            del_sql = f'DELETE FROM {table_db_name} WHERE "Company Name" = ?'
                            execute_db_command(del_sql, (d_row['Company Name'],))
                            updated_count += 1

                    # Track updated rows
                    for idx in edited_df.index:
                        if idx in grid_display_df.index:
                            orig_row = grid_display_df.loc[idx]
                            new_row = edited_df.loc[idx]

                            if not orig_row.equals(new_row):
                                company_name = new_row['Company Name']
                                filed_val = new_row.get(filed_col_name, 'No')
                                days_val = int(new_row.get(days_col, 0))

                                sql_cmd = f'UPDATE {table_db_name} SET "{filed_col_name}" = ?, "{days_col}" = ? WHERE "Company Name" = ?'
                                execute_db_command(sql_cmd, (filed_val, days_val, company_name))
                                updated_count += 1

                    if updated_count > 0:
                        st.cache_data.clear()
                        st.toast(f"🎉 Successfully saved changes ({updated_count} record/s affected)!", icon="✅")
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