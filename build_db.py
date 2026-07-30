import sqlite3
import pandas as pd

# 1. Read your Excel file sheets
excel_file = "Book2.xlsx"  # Make sure your file is named Book2.xlsx

df_ct = pd.read_excel(excel_file, sheet_name="CT-Data")
df_cro = pd.read_excel(excel_file, sheet_name="CORE-Data")

# 2. Connect to (or create) the SQLite database file
conn = sqlite3.connect("irish_tax_compliance.db")

# 3. Clean and save data into database tables
df_ct.dropna(how="all").to_sql(
    "corporation_tax", conn, if_exists="replace", index=False
)
df_cro.dropna(how="all").to_sql(
    "cro_annual_returns", conn, if_exists="replace", index=False
)

conn.close()

print(
    "Success! Created 'irish_tax_compliance.db' with your CT and CRO data."
)