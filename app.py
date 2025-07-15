import streamlit as st
import pandas as pd
import re
from pathlib import Path
import hashlib

PASSWORD_HASH = d96d2f96fdc33dbc15fd3512a1f01beb0c01449f495db9e79e59ffce6b5aceaf

def check_password():
    """Password-protected access using Streamlit session state"""
    if "authenticated" not in st.session_state:
        st.session_state.authenticated = False

    if st.session_state.authenticated:
        return True

    st.sidebar.markdown("## 🔐 Login Required")
    password = st.sidebar.text_input("Enter password", type="password")

    if password:
        if hashlib.sha256(password.encode()).hexdigest() == PASSWORD_HASH:
            st.session_state.authenticated = True
            st.rerun()  # Rerun to hide the input box
        else:
            st.sidebar.error("Incorrect password")

    return False

MODEL_RUNS_DIR = Path("model_runs")

def normalise_building(name):
    if not isinstance(name, str):
        return None

    name = name.upper().strip()

    # Clean excess spacing
    name = re.sub(r"\s+", " ", name)

    if any(x in name for x in ["REACTOR", "RB", "R.B."]):
        return "Reactor Building"
    if any(x in name for x in ["AUX", "CONTROL", "AUXILIARY", "AUX/CON", "AUX/CONTROL"]):
        return "Auxiliary/Control Building"
    if "FUEL" in name:
        return "Fuel Building"
    if "DIESEL" in name:
        return "Diesel Building"
    if "RADWASTE" in name or "RAD WASTE" in name:
        return "Radwaste Building"
    if "DECONTAMINATION" in name:
        return "Decontamination Building"

    return name.title()
# --- Extract all TITLE= model runs ---
def extract_all_titles_from_folder(folder: Path):
    results = []
    text_files = list(folder.rglob("*.txt"))

    for file_path in text_files:
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                lines = f.readlines()

            current_run = None

            for line in lines:
                l = line.strip()

                title_match = re.search(r"\bTITLE\s*=\s*(.+)", l, re.IGNORECASE)
                if title_match:
                    if current_run:
                        results.append(current_run)

                    rel_path = file_path.relative_to(folder)
                    current_run = {
                        "RunFolder": folder.name,
                        "File": file_path.name,
                        "RelPath": str(rel_path),
                        "Title": title_match.group(1).strip(),
                        "Subtitle": None,
                        "Label": None,
                        "Building": None,
                        "Station": None,
                        "Year": None,
                        "Code": "Unknown"
                    }

                    parts = [p.strip() for p in current_run["Title"].split(",")]
                    for part in parts:
                        if "BUILDING" in part.upper():
                            current_run["Building"] = current_run["Building"] or part
                        if any(s in part.upper() for s in ["SZB", "SXB", "SIZEWELL", "PLANT", "STATION"]):
                            current_run["Station"] = current_run["Station"] or part

                    year_match = re.search(r"\b(19[8-9]\d|20[0-2]\d)\b", current_run["Title"])
                    if year_match:
                        current_run["Year"] = int(year_match.group(1))

                elif current_run:
                    if "SUBTITLE=" in l.upper() and current_run["Subtitle"] is None:
                        current_run["Subtitle"] = l.split("=", 1)[1].strip()
                    elif "LABEL=" in l.upper() and current_run["Label"] is None:
                        current_run["Label"] = l.split("=", 1)[1].strip()

            if current_run:
                results.append(current_run)

            # Enhance metadata post-scan
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()

            for run in results:
                if run["RunFolder"] != folder.name or run["RelPath"] != str(file_path.relative_to(folder)):
                    continue

                if run["Code"] == "Unknown":
                    if "NASTRAN" in content.upper():
                        run["Code"] = "NASTRAN"
                    elif "ANSYS" in content.upper():
                        run["Code"] = "ANSYS"
                    elif "SASA" in content.upper():
                        run["Code"] = "SASA"

                if not run["Building"]:
                    b_match = re.search(r"\b(REACTOR BUILDING|CONTROL BUILDING|RB|R\.B\.|AUXILIARY BUILDING)\b", content, re.IGNORECASE)
                    if b_match:
                        run["Building"] = b_match.group(0)

                if not run["Station"]:
                    s_match = re.search(r"\b(SZB|SXB|SIZEWELL|STATION|PLANT)\b", content, re.IGNORECASE)
                    if s_match:
                        run["Station"] = s_match.group(0)

                if run["Year"] is None:
                    full_date_match = re.search(
                        r"\b(?:JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|SEPT|OCT|NOV|DEC|"
                        r"JANUARY|FEBRUARY|MARCH|APRIL|JUNE|JULY|AUGUST|SEPTEMBER|OCTOBER|NOVEMBER|DECEMBER)"
                        r"[A-Z]*\s+\d{1,2},?\s+(19[8-9]\d|20[0-2]\d)\b",
                        content, re.IGNORECASE
                    )
                    if full_date_match:
                        run["Year"] = int(full_date_match.group(1))
                    else:
                        fallback_year = re.search(r"\b(19[8-9]\d|20[0-2]\d)\b", content)
                        if fallback_year:
                            run["Year"] = int(fallback_year.group(1))

        except Exception:
            continue

    return results

# --- Index builder ---
@st.cache_data(show_spinner=False)
def build_model_index(model_path):
    folders = sorted([f for f in model_path.iterdir() if f.is_dir()])
    metadata_rows = []
    for f in folders:
        metadata_rows.extend(extract_all_titles_from_folder(f))
    
    df = pd.DataFrame(metadata_rows)
    
    # Save index for reuse elsewhere
    df.to_parquet("model_index.parquet", index=False)
    
    return df

# # --- UI ---
# st.set_page_config(layout="wide")
# st.title("📂 Structural Model Runs Index (Per Title)")
# df = build_model_index(MODEL_RUNS_DIR)

# # --- Sidebar Filters ---
# st.sidebar.header("🔍 Filter Model Runs")
# stations = sorted(df["Station"].dropna().unique())
# buildings = sorted(df["Building"].dropna().unique())
# codes = sorted(df["Code"].dropna().unique())
# years = df["Year"].dropna().astype(int)

# min_year, max_year = (1980, 2025) if years.empty else (years.min(), years.max())

# if min_year == max_year:
    # selected_years = (min_year, max_year)
    # st.sidebar.number_input("Only one year in index", value=min_year, disabled=True)
# else:
    # selected_years = st.sidebar.slider("Year range", min_year, max_year, (min_year, max_year))

# selected_station = st.sidebar.multiselect("Station", stations)
# selected_building = st.sidebar.multiselect("Building", buildings)
# selected_code = st.sidebar.multiselect("Code", codes)

# # --- Apply Filters ---
# filtered = df.copy()
# if selected_station:
    # filtered = filtered[filtered["Station"].isin(selected_station)]
# if selected_building:
    # filtered = filtered[filtered["Building"].isin(selected_building)]
# if selected_code:
    # filtered = filtered[filtered["Code"].isin(selected_code)]
# filtered = filtered[
    # filtered["Year"].between(selected_years[0], selected_years[1], inclusive="both")
# ]

# # --- UI Output ---
# st.subheader("📋 Filtered Model Runs")
# if not filtered.empty:
    # st.download_button(
        # label="📥 Download Metadata CSV",
        # data=filtered.to_csv(index=False),
        # file_name="filtered_model_metadata.csv",
        # mime="text/csv"
    # )

    # selected_run = st.selectbox(
        # "Select a model run to inspect",
        # options=filtered.index,
        # format_func=lambda i: f"{filtered.loc[i, 'RunFolder']} — {filtered.loc[i, 'RelPath']}"
    # )

    # run_meta = filtered.loc[selected_run]
    # run_path = MODEL_RUNS_DIR / run_meta["RunFolder"] / run_meta["RelPath"]

    # col1, col2 = st.columns([1, 2])

    # with col1:
        # st.markdown(f"### 📦 {run_meta['RunFolder']} / {run_meta['RelPath']}")
        # st.markdown(f"**Station:** {run_meta['Station'] or '—'}")
        # st.markdown(f"**Building:** {run_meta['Building'] or '—'}")
        # st.markdown(f"**Year:** {run_meta['Year'] or '—'}")
        # st.markdown(f"**Code:** {run_meta['Code'] or '—'}")
        # st.markdown("---")
        # st.markdown(f"**Title:**\n> {run_meta['Title'] or '—'}")
        # st.markdown(f"**Subtitle:**\n> {run_meta['Subtitle'] or '—'}")
        # st.markdown(f"**Label:**\n> {run_meta['Label'] or '—'}")

    # with col2:
        # st.markdown("### 📖 File Preview")
        # try:
            # with open(run_path, 'r', encoding='utf-8', errors='ignore') as f:
                # preview = f.read(3000)
            # st.text_area("Preview", preview, height=400)
        # except Exception as e:
            # st.error(f"Could not read file: {e}")
# else:
    # st.info("No matching model runs found.")




# --- UI ---
st.set_page_config(layout="wide")
st.title("📂 Structural Model Runs Index")

#df = build_model_index(MODEL_RUNS_DIR)
df = pd.read_parquet("model_index.parquet")
df["Building"] = df["Building"].apply(normalise_building)
if df.empty:
    st.warning("No model runs found.")
    st.stop()

# --- Sidebar Filters ---
st.sidebar.header("🔍 Filter Model Runs")
#stations = sorted(df["Station"].dropna().unique())
buildings = sorted(df["Building"].dropna().unique())
codes = sorted(df["Code"].dropna().unique())
years = df["Year"].dropna().astype(int)

min_year, max_year = (1980, 2025) if years.empty else (years.min(), years.max())

if min_year == max_year:
    selected_years = (min_year, max_year)
    st.sidebar.number_input("Only one year in index", value=min_year, disabled=True)
else:
    selected_years = st.sidebar.slider("Year range", min_year, max_year, (min_year, max_year))

#selected_station = st.sidebar.multiselect("Station", stations)
selected_building = st.sidebar.multiselect("Building", buildings)
selected_code = st.sidebar.multiselect("Code", codes)

# --- Apply filters ---
filtered = df.copy()
#if selected_station:
#    filtered = filtered[filtered["Station"].isin(selected_station)]
if selected_building:
    filtered = filtered[filtered["Building"].isin(selected_building)]
if selected_code:
    filtered = filtered[filtered["Code"].isin(selected_code)]
filtered = filtered[
    filtered["Year"].between(selected_years[0], selected_years[1], inclusive="both")
]

# --- Layout: Left = folders, Right = model cards ---
st.markdown("### 📁 Available Model Run Folders")
st.download_button(
    label="📥 Download Metadata CSV",
    data=filtered.to_csv(index=False),
    file_name="filtered_model_metadata.csv",
    mime="text/csv"
)
col1, col2 = st.columns([1, 2])

if filtered.empty:
    col1.info("No folders match the selected filters.")
    col2.info("No model runs to display.")
else:
    with col1:
        folders_in_filtered = sorted(filtered["RunFolder"].unique())

        st.markdown("### 📁 Select a Folder")
        cols = st.columns(2)

        # Initialise default selection
        if "selected_folder" not in st.session_state:
            st.session_state.selected_folder = folders_in_filtered[0] if folders_in_filtered else None

        for i, folder in enumerate(folders_in_filtered):
            col = cols[i % len(cols)]
            is_selected = folder == st.session_state.selected_folder
            label = f"✅ {folder}" if is_selected else f"📂 {folder}"
            if col.button(label, key=f"folder_btn_{folder}"):
                st.session_state.selected_folder = folder
                st.rerun()

        selected_folder = st.session_state.selected_folder

    with col2:
        folder_df = filtered[filtered["RunFolder"] == selected_folder]
        st.markdown(f"### 📦 Model Runs in `{selected_folder}`")
        for _, row in folder_df.iterrows():
            with st.container():
                st.markdown("----")
                st.markdown(f"#### 📄 `{row['RelPath']}`")
                cols = st.columns([1.2, 2])

                with cols[0]:
                    st.markdown(f"**Year:** {int(row['Year']) if pd.notna(row['Year']) else '—'}")
                    st.markdown(f"**Code:** {row['Code'] or '—'}")
                    st.markdown(f"**Building:** {row['Building'] or '—'}")
                    st.markdown(f"**Station:** {row['Station'] or '—'}")

                with cols[1]:
                    st.markdown(f"**Title:**\n> {row['Title'] or '—'}")
                    if row.get("Subtitle"):
                        st.markdown(f"**Subtitle:**\n> {row['Subtitle']}")
                    if row.get("Label"):
                        st.markdown(f"**Label:**\n> {row['Label']}")
