"""
DC Label Generator
==================

Version 1.0.0 - Distribution Center Package Label Generator

Generates ZPL labels from Distru Packages and Products exports for Zebra printers.
Supports filtering by Created Date, Brand, and Vendor with options for per-package
or per-case label generation.

Label Format: 4" x 2" at 203 DPI (ZD621)

CHANGELOG:
v1.0.0 (2025-12-19)
- Initial release
- Package and Products CSV integration
- Brand extraction from product names (first hyphen)
- Vendor filtering from Products data
- Quick date selection (Today, Yesterday, This Week)
- Case quantity calculation from Products Units Per Case
- ZPL download and clipboard copy support

Author: DC Retail
"""

import streamlit as st
import pandas as pd
import io
import math
import base64
from datetime import datetime, timedelta
from typing import Optional, Tuple, List
import streamlit.components.v1 as components


# =============================================================================
# CONFIGURATION CONSTANTS
# =============================================================================

VERSION = "1.0.0"

# Label specifications for ZD621 printer
LABEL_WIDTH = 4.0    # inches
LABEL_HEIGHT = 2.0   # inches
DPI = 203            # dots per inch


# =============================================================================
# PAGE SETUP
# =============================================================================

st.set_page_config(
    page_title="DC Label Generator",
    page_icon="🏷️",
    layout="wide"
)


# =============================================================================
# SESSION STATE INITIALIZATION
# =============================================================================

def initialize_session_state():
    """Initialize all session state variables used by the application."""
    defaults = {
        "processed_data": None,
        "products_data": None,
        "packages_data": None,
        "date_selection": "all",
        "zpl_content": None,
        "zpl_filename": None,
        "label_count": 0
    }
    for key, default_value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = default_value


initialize_session_state()


# =============================================================================
# UTILITY FUNCTIONS
# =============================================================================

def safe_numeric(value, default=0.0):
    """
    Safely convert a value to a numeric type.
    
    Handles strings, NaN, None, and empty values gracefully.
    
    Args:
        value: The value to convert (can be str, float, int, None, etc.)
        default: Value to return if conversion fails
        
    Returns:
        Numeric value or default
    """
    if pd.isna(value) or value is None or value == "":
        return default
    try:
        if isinstance(value, str):
            value = value.strip()
            if value == "":
                return default
        num_val = float(value)
        if num_val == int(num_val):
            return int(num_val)
        return num_val
    except (ValueError, TypeError, AttributeError):
        return default


def extract_brand(product_name):
    """
    Extract brand and product name from a full product string.
    
    Uses the first hyphen as the delimiter between brand and product.
    Example: "Camino - Strawberry Sunset" -> ("Camino", "Strawberry Sunset")
    
    Args:
        product_name: Full product name string
        
    Returns:
        Tuple of (brand, product_remainder)
    """
    if pd.isna(product_name) or not product_name:
        return ("", str(product_name) if product_name else "")
    
    product_str = str(product_name).strip()
    
    # Try " - " delimiter first (more common format)
    if " - " in product_str:
        parts = product_str.split(" - ", 1)
        return (parts[0].strip(), parts[1].strip())
    
    # Fall back to "-" without spaces
    if "-" in product_str:
        parts = product_str.split("-", 1)
        return (parts[0].strip(), parts[1].strip())
    
    # No delimiter found - return empty brand
    return ("", product_str)


def load_csv(uploaded_file, file_type):
    """
    Load a CSV file into a DataFrame with all columns as strings.
    
    Args:
        uploaded_file: Streamlit UploadedFile object
        file_type: Description of file type for error messages
        
    Returns:
        DataFrame or None if loading fails
    """
    try:
        uploaded_file.seek(0)
        df = pd.read_csv(uploaded_file, dtype=str)
        if df.empty:
            return None
        return df
    except Exception as e:
        st.error(f"Error loading {file_type} CSV: {str(e)}")
        return None


def sanitize_qr_data(package_label):
    """
    Clean and validate package label for QR code generation.
    
    Args:
        package_label: Raw package label value
        
    Returns:
        Cleaned string safe for QR encoding
    """
    if pd.isna(package_label) or package_label is None:
        return ""
    return str(package_label).strip()


def calculate_case_labels_needed(quantity, units_per_case):
    """
    Calculate how many case labels are needed for a package.
    
    Args:
        quantity: Total package quantity
        units_per_case: Units that fit in one case
        
    Returns:
        Number of labels needed (rounded up)
    """
    if quantity <= 0 or units_per_case <= 0:
        return 0
    return math.ceil(quantity / units_per_case)


def calculate_individual_case_quantities(quantity, units_per_case):
    """
    Calculate the quantity for each individual case label.
    
    Handles partial cases (last case may have fewer units).
    
    Args:
        quantity: Total package quantity
        units_per_case: Units that fit in one case
        
    Returns:
        List of quantities for each case label
    """
    if quantity <= 0 or units_per_case <= 0:
        return []
    
    quantities = []
    remaining = quantity
    
    while remaining > 0:
        if remaining >= units_per_case:
            quantities.append(units_per_case)
            remaining -= units_per_case
        else:
            quantities.append(remaining)
            remaining = 0
    
    return quantities


# =============================================================================
# DATA PROCESSING
# =============================================================================

def merge_data_sources(packages_df, products_df):
    """
    Merge Packages and Products data to create the working dataset.
    
    Joins on Distru Product (packages) -> Name (products) to get:
    - Units Per Case for case label calculations
    - Vendor for filtering
    - Category fallback from products
    
    Args:
        packages_df: Raw packages DataFrame
        products_df: Raw products DataFrame
        
    Returns:
        Merged and processed DataFrame or None if error
    """
    try:
        # Store raw data in session state
        st.session_state.packages_data = packages_df
        st.session_state.products_data = products_df
        
        # Select columns needed from products and merge
        products_subset = products_df[["Name", "Units Per Case", "Category", "Vendor"]].copy()
        products_subset = products_subset.rename(columns={"Category": "Product_Category"})
        
        merged_df = packages_df.merge(
            products_subset,
            left_on="Distru Product",
            right_on="Name",
            how="left",
            suffixes=("", "_products")
        )
        
        # Extract brand and clean product name
        merged_df["Brand"] = merged_df["Distru Product"].apply(lambda x: extract_brand(x)[0])
        merged_df["Product_Name_Clean"] = merged_df["Distru Product"].apply(lambda x: extract_brand(x)[1])
        
        # Parse creation date
        merged_df["Created_Date"] = pd.to_datetime(
            merged_df["Created in Distru At (UTC)"],
            errors="coerce"
        ).dt.date
        
        # Convert numeric columns
        merged_df["Quantity_Num"] = merged_df["Quantity"].apply(safe_numeric)
        merged_df["Units_Per_Case_Num"] = merged_df["Units Per Case"].apply(safe_numeric)
        
        # Calculate case labels needed
        merged_df["Case_Labels_Needed"] = merged_df.apply(
            lambda row: calculate_case_labels_needed(
                row["Quantity_Num"],
                row["Units_Per_Case_Num"]
            ) if row["Units_Per_Case_Num"] > 0 else 0,
            axis=1
        )
        
        # Use package Category if available, fallback to product category
        merged_df["Display_Category"] = merged_df["Category"].fillna(merged_df["Product_Category"])
        
        # Select and rename columns for the final dataset
        result_df = merged_df[[
            "Distru Product", "Brand", "Product_Name_Clean", "Package Label",
            "Quantity", "Quantity_Num", "Units Per Case", "Units_Per_Case_Num",
            "Case_Labels_Needed", "Distru Batch Number", "Display_Category",
            "Created_Date", "Created in Distru At (UTC)", "Status", "Location", "Vendor"
        ]].copy()
        
        result_df.columns = [
            "Product Name", "Brand", "Product (Clean)", "Package Label",
            "Quantity", "Quantity_Num", "Units Per Case", "Units_Per_Case_Num",
            "Case Labels Needed", "Batch No", "Category",
            "Created Date", "Created At (Full)", "Status", "Location", "Vendor"
        ]
        
        return result_df
        
    except Exception as e:
        st.error(f"Error processing data: {str(e)}")
        import traceback
        st.error(traceback.format_exc())
        return None


# =============================================================================
# ZPL LABEL GENERATION
# =============================================================================

def generate_label_zpl(product_name, brand, product_clean, batch_no, qty, package_label, category, created_date):
    """
    Generate ZPL code for a single 4" x 2" label at 203 DPI.
    
    Label Layout:
    +-----------------------------------------------------------+
    | BRAND (white on black)                        Category    |
    +-----------------------------------------------------------+
    | Product Name (up to 2 lines)                              |
    |                                                      +---+|
    |       1A406030002C881000003648                      |QR ||
    |         Created: 09/09/2024                         |   ||
    |                                                      +---+|
    | Batch: ABC-123                              Case Qty: 25  |
    +-----------------------------------------------------------+
    
    Args:
        product_name: Full product name (fallback if product_clean empty)
        brand: Brand name for top bar
        product_clean: Cleaned product name (without brand)
        batch_no: Batch/lot number
        qty: Units Per Case from Products table (displayed as "Case Qty")
        package_label: UID for QR code and center display
        category: Product category for top bar
        created_date: Package creation date
        
    Returns:
        Complete ZPL code string for the label
    """
    # Calculate dimensions in dots
    width_dots = int(LABEL_WIDTH * DPI)   # 812 dots
    
    # Font size definitions (in dots)
    font_uid = 46           # UID display (larger for visibility)
    font_large = 32         # Brand, product name
    font_large_plus = 28    # Batch, quantity
    font_medium = 24        # Category
    font_small_plus = 22    # Created date
    
    # Layout positioning (in dots)
    left_margin = 20
    right_margin = 20
    
    # Vertical positions
    brand_bar_y = 8
    brand_bar_height = 50
    product_y = 70
    uid_y = 180
    date_y = 220
    bottom_y = 360
    qr_y = 120
    
    # QR code sizing and positioning
    qr_magnification = 5
    qr_box_size = qr_magnification * 30
    qr_x = width_dots - qr_box_size - 15
    
    # Calculate text width limits
    text_width = width_dots - left_margin - right_margin
    max_chars = int(text_width / (font_large * 0.45))
    
    # Prepare brand text (truncate if needed)
    brand_display = str(brand) if pd.notna(brand) and brand else ""
    if len(brand_display) > max_chars:
        brand_display = brand_display[:max_chars - 3] + "..."
    
    # Prepare product text with word wrapping (max 2 lines)
    if pd.notna(product_clean) and product_clean:
        product_display = str(product_clean)
    else:
        product_display = str(product_name)
    
    product_lines = []
    
    if len(product_display) > max_chars:
        words = product_display.split()
        current_line = ""
        
        for word in words:
            if current_line:
                test_line = current_line + " " + word
            else:
                test_line = word
            
            if len(test_line) <= max_chars:
                current_line = test_line
            else:
                if current_line:
                    product_lines.append(current_line)
                current_line = word
        
        if current_line:
            product_lines.append(current_line)
        
        # Limit to 2 lines, truncate second line if needed
        if len(product_lines) > 2:
            product_lines = product_lines[:2]
            if len(product_lines[1]) > max_chars - 3:
                product_lines[1] = product_lines[1][:max_chars - 3] + "..."
    else:
        product_lines = [product_display]
    
    # Prepare QR data (UID)
    qr_data = sanitize_qr_data(package_label)
    
    # Format created date
    created_date_display = ""
    if pd.notna(created_date) and created_date:
        try:
            date_obj = pd.to_datetime(created_date)
            created_date_display = date_obj.strftime("%m/%d/%Y")
        except (ValueError, TypeError):
            created_date_display = str(created_date)
    
    # Build ZPL command list
    zpl = []
    zpl.append("^XA")  # Start format
    
    # --- BLACK BRAND BAR (inverted colors) ---
    zpl.append(f"^FO0,{brand_bar_y}^GB{width_dots},{brand_bar_height},{brand_bar_height}^FS")
    
    # Brand text (white on black via field reverse)
    brand_text_y = brand_bar_y + (brand_bar_height - font_large) // 2
    if brand_display:
        zpl.append("^FR")  # Field reverse for white text
        zpl.append(f"^CF0,{font_large}")
        zpl.append(f"^FO{left_margin},{brand_text_y}^FR^FD{brand_display}^FS")
    
    # Category (right-aligned, white on black)
    if pd.notna(category) and category:
        category_text = str(category)
        category_width = len(category_text) * (font_medium // 2)
        category_x = width_dots - right_margin - category_width
        category_text_y = brand_bar_y + (brand_bar_height - font_medium) // 2
        zpl.append(f"^CF0,{font_medium}")
        zpl.append(f"^FO{category_x},{category_text_y}^FR^FD{category_text}^FS")
    
    # --- PRODUCT NAME (below brand bar) ---
    zpl.append(f"^CF0,{font_large}")
    current_y = product_y
    for line in product_lines:
        zpl.append(f"^FO{left_margin},{current_y}^FD{line}^FS")
        current_y += int(font_large * 1.2)
    
    # --- UID (left-of-center to avoid QR code, larger font) ---
    if qr_data:
        uid_width = len(qr_data) * (font_uid // 2)
        # Shift left: center within the area left of QR code (qr_x - margin)
        available_width = qr_x - left_margin - 20  # Leave gap before QR
        uid_x = left_margin + (available_width - uid_width) // 2
        # Ensure minimum left margin
        if uid_x < left_margin:
            uid_x = left_margin
        zpl.append(f"^CF0,{font_uid}")
        zpl.append(f"^FO{uid_x},{uid_y}^FD{qr_data}^FS")
    
    # --- CREATED DATE (centered in area left of QR code, below UID) ---
    if created_date_display:
        date_text = f"Created: {created_date_display}"
        date_width = len(date_text) * (font_small_plus // 2)
        # Center in same area as UID (left of QR code)
        available_width = qr_x - left_margin - 20
        date_x = left_margin + (available_width - date_width) // 2
        if date_x < left_margin:
            date_x = left_margin
        zpl.append(f"^CF0,{font_small_plus}")
        zpl.append(f"^FO{date_x},{date_y}^FD{date_text}^FS")
    
    # --- QR CODE (right side) ---
    if qr_data:
        zpl.append(f"^FO{qr_x},{qr_y}^BQN,2,{qr_magnification}^FDQA,{qr_data}^FS")
    
    # --- BATCH NUMBER (bottom left) ---
    if pd.notna(batch_no) and batch_no:
        batch_display = str(batch_no)
        zpl.append(f"^CF0,{font_large_plus}")
        zpl.append(f"^FO{left_margin},{bottom_y}^FDBatch: {batch_display}^FS")
    
    # --- CASE QUANTITY (bottom right) - Shows Units Per Case from Products table ---
    if qty is not None:
        qty_num = safe_numeric(qty, 0)
        if qty_num == int(qty_num):
            qty_display = f"Case Qty: {int(qty_num)}"
        else:
            qty_display = f"Case Qty: {qty_num:.1f}"
    else:
        qty_display = "Case Qty: N/A"
    
    qty_width = len(qty_display) * (font_large_plus // 2)
    qty_x = width_dots - right_margin - qty_width
    zpl.append(f"^CF0,{font_large_plus}")
    zpl.append(f"^FO{qty_x},{bottom_y}^FD{qty_display}^FS")
    
    zpl.append("^XZ")  # End format
    
    return "\n".join(zpl)


def generate_labels_for_row(row, label_mode):
    """
    Generate all labels needed for a single package row.
    
    Args:
        row: DataFrame row containing package data
        label_mode: "package" for 1 label or "case" for multiple labels
        
    Returns:
        List of ZPL strings (one per label)
    """
    labels = []
    
    quantity = safe_numeric(row.get("Quantity_Num", 0))
    units_per_case = safe_numeric(row.get("Units_Per_Case_Num", 0))
    created_date = row.get("Created At (Full)", "")
    
    if quantity <= 0:
        return []
    
    # Case Qty always shows Units Per Case from Products table
    # If Units Per Case is missing, still generate label but show the value we have
    units_per_case_display = units_per_case if units_per_case > 0 else None
    
    if label_mode == "package":
        # Single label for the package
        zpl = generate_label_zpl(
            product_name=row.get("Product Name", ""),
            brand=row.get("Brand", ""),
            product_clean=row.get("Product (Clean)", ""),
            batch_no=row.get("Batch No", ""),
            qty=units_per_case_display,
            package_label=row.get("Package Label", ""),
            category=row.get("Category", ""),
            created_date=created_date
        )
        labels.append(zpl)
    
    elif label_mode == "case" and units_per_case > 0:
        # Multiple labels, one per case - all show same Units Per Case
        num_cases = calculate_case_labels_needed(quantity, units_per_case)
        
        for _ in range(num_cases):
            zpl = generate_label_zpl(
                product_name=row.get("Product Name", ""),
                brand=row.get("Brand", ""),
                product_clean=row.get("Product (Clean)", ""),
                batch_no=row.get("Batch No", ""),
                qty=units_per_case,  # Always show Units Per Case
                package_label=row.get("Package Label", ""),
                category=row.get("Category", ""),
                created_date=created_date
            )
            labels.append(zpl)
    
    return labels


def generate_all_labels(df, label_mode):
    """
    Generate labels for all rows in the DataFrame.
    
    Sorts by Brand then Product Name for organized printing.
    
    Args:
        df: Filtered DataFrame of packages
        label_mode: "package" or "case"
        
    Returns:
        List of all ZPL strings
    """
    all_labels = []
    
    # Sort for organized output
    df_sorted = df.sort_values(["Brand", "Product Name"], ascending=[True, True])
    
    for idx, row in df_sorted.iterrows():
        row_labels = generate_labels_for_row(row, label_mode)
        all_labels.extend(row_labels)
    
    return all_labels


def generate_filename(data, label_mode):
    """
    Generate a descriptive filename for the ZPL download.
    
    Args:
        data: DataFrame used for label generation
        label_mode: "package" or "case"
        
    Returns:
        Filename string with timestamp
    """
    timestamp = pd.Timestamp.now().strftime("%Y%m%d_%H%M%S")
    
    brands = data["Brand"].dropna().unique()
    if len(brands) == 1:
        brand_part = str(brands[0]).replace(" ", "_")[:20]
    elif len(brands) <= 3:
        brand_part = "_".join([str(b).replace(" ", "_")[:10] for b in brands])[:30]
    else:
        brand_part = f"Multiple_{len(brands)}_brands"
    
    mode_part = "per_package" if label_mode == "package" else "per_case"
    
    return f"dc_labels_{brand_part}_{mode_part}_{timestamp}.zpl"


# =============================================================================
# BROWSER PRINT INTEGRATION
# =============================================================================

def create_browser_print_launcher(zpl_data, label_count):
    """
    Create an HTML component for copying ZPL to clipboard.
    
    Provides a user-friendly interface for getting the ZPL data
    to send to a Zebra printer.
    
    Args:
        zpl_data: Complete ZPL string for all labels
        label_count: Number of labels for display
    """
    # Encode ZPL as base64 for safe embedding
    b64_zpl = base64.b64encode(zpl_data.encode()).decode()
    
    html_content = f'''
    <div style="padding: 20px; border: 2px solid #4CAF50; border-radius: 10px; background-color: #f9f9f9;">
        <h3 style="color: #333; margin-top: 0;">🖨️ Ready to Print {label_count} Labels</h3>
        
        <p style="color: #666;">Click to copy ZPL code to clipboard:</p>
        
        <div style="display: flex; gap: 10px; margin-top: 15px;">
            <button onclick="copyToClipboard()" style="
                background-color: #4CAF50;
                color: white;
                padding: 12px 20px;
                font-size: 16px;
                border: none;
                border-radius: 5px;
                cursor: pointer;
                flex: 1;
            ">
                📋 Copy ZPL to Clipboard
            </button>
        </div>
        
        <div id="status" style="margin-top: 15px; padding: 10px; display: none;"></div>
        
        <details style="margin-top: 20px;">
            <summary style="cursor: pointer; color: #666;">ℹ️ Printing Instructions</summary>
            <div style="margin-top: 10px; padding: 10px; background-color: #fff; border-radius: 5px;">
                <strong>How to Print:</strong>
                <ol style="margin: 10px 0;">
                    <li>Click "Copy ZPL to Clipboard"</li>
                    <li>Open Zebra Setup Utilities or your print application</li>
                    <li>Paste the ZPL code and send to printer</li>
                </ol>
            </div>
        </details>
    </div>
    
    <script>
        const zplData = atob("{b64_zpl}");
        
        function copyToClipboard() {{
            const statusDiv = document.getElementById("status");
            
            navigator.clipboard.writeText(zplData).then(() => {{
                statusDiv.style.display = "block";
                statusDiv.style.backgroundColor = "#d4edda";
                statusDiv.style.color = "#155724";
                statusDiv.innerHTML = "✅ ZPL copied to clipboard!";
            }}).catch(() => {{
                // Fallback for older browsers
                const textarea = document.createElement("textarea");
                textarea.value = zplData;
                textarea.style.position = "fixed";
                textarea.style.opacity = "0";
                document.body.appendChild(textarea);
                textarea.select();
                document.execCommand("copy");
                document.body.removeChild(textarea);
                
                statusDiv.style.display = "block";
                statusDiv.style.backgroundColor = "#d4edda";
                statusDiv.style.color = "#155724";
                statusDiv.innerHTML = "✅ ZPL copied to clipboard!";
            }});
        }}
    </script>
    '''
    
    components.html(html_content, height=250)


# =============================================================================
# MAIN APPLICATION
# =============================================================================

def main():
    """Main application entry point."""
    
    st.title("🏷️ DC Label Generator")
    st.markdown("**DC Retail** | Generate labels from Distru package exports")
    
    # -------------------------------------------------------------------------
    # SIDEBAR - Data Sources
    # -------------------------------------------------------------------------
    
    st.sidebar.header("📊 Data Sources")
    
    st.sidebar.subheader("📦 Packages")
    packages_file = st.sidebar.file_uploader(
        "Choose Packages CSV",
        type=["csv"],
        key="packages_upload",
        help="Export from Distru containing package data"
    )
    
    st.sidebar.subheader("📋 Products")
    products_file = st.sidebar.file_uploader(
        "Choose Products CSV",
        type=["csv"],
        key="products_upload",
        help="Export from Distru containing product data (Units Per Case, Vendor)"
    )
    
    # Process button
    process_disabled = not (packages_file and products_file)
    if st.sidebar.button("🚀 Process Data", type="primary", disabled=process_disabled):
        with st.spinner("Processing your data..."):
            packages_df = load_csv(packages_file, "Packages")
            products_df = load_csv(products_file, "Products")
            
            if packages_df is None or products_df is None:
                st.error("Failed to load one or more CSV files")
                st.stop()
            
            st.success(f"Files loaded: Packages ({len(packages_df):,} rows) | Products ({len(products_df):,} rows)")
            
            processed_data = merge_data_sources(packages_df, products_df)
            
            if processed_data is not None:
                st.session_state.processed_data = processed_data
                st.success(f"Successfully processed {len(processed_data):,} packages")
    
    # Version info
    st.sidebar.markdown("---")
    st.sidebar.caption(f"Version {VERSION}")
    st.sidebar.caption("© 2025 DC Retail")
    
    # -------------------------------------------------------------------------
    # MAIN CONTENT
    # -------------------------------------------------------------------------
    
    if st.session_state.processed_data is not None:
        processed_df = st.session_state.processed_data
        
        tab1, tab2 = st.tabs(["🎯 Generate Labels", "📊 Data Overview"])
        
        # ---------------------------------------------------------------------
        # TAB 1: Generate Labels
        # ---------------------------------------------------------------------
        with tab1:
            st.header("🎯 Generate Labels")
            
            # Filter columns
            col1, col2 = st.columns(2)
            
            # --- DATE FILTER ---
            with col1:
                st.subheader("📅 Filter by Created Date")
                
                available_dates = sorted(processed_df["Created Date"].dropna().unique())
                
                if available_dates:
                    min_date = min(available_dates)
                    max_date = max(available_dates)
                    
                    # Quick selection buttons
                    st.markdown("**Quick Select:**")
                    qcol1, qcol2, qcol3, qcol4 = st.columns(4)
                    
                    today = datetime.now().date()
                    yesterday = today - timedelta(days=1)
                    week_start = today - timedelta(days=today.weekday())
                    
                    with qcol1:
                        if st.button("📅 Today", use_container_width=True):
                            st.session_state["date_selection"] = "today"
                    with qcol2:
                        if st.button("⏪ Yesterday", use_container_width=True):
                            st.session_state["date_selection"] = "yesterday"
                    with qcol3:
                        if st.button("📆 This Week", use_container_width=True):
                            st.session_state["date_selection"] = "this_week"
                    with qcol4:
                        if st.button("🔄 All Dates", use_container_width=True):
                            st.session_state["date_selection"] = "all"
                    
                    # Manual selection option
                    date_filter_type = st.radio(
                        "Or select manually:",
                        ["Use quick selection", "Date range", "Specific dates"],
                        horizontal=True
                    )
                    
                    # Determine selected dates based on filter type
                    if date_filter_type == "Use quick selection":
                        selection = st.session_state.get("date_selection", "all")
                        
                        if selection == "today":
                            selected_dates = [d for d in available_dates if d == today]
                            st.info(f"📅 Showing packages from today ({today.strftime('%m/%d/%Y')})")
                        elif selection == "yesterday":
                            selected_dates = [d for d in available_dates if d == yesterday]
                            st.info(f"⏪ Showing packages from yesterday ({yesterday.strftime('%m/%d/%Y')})")
                        elif selection == "this_week":
                            selected_dates = [d for d in available_dates if d >= week_start]
                            st.info(f"📆 Showing packages from this week ({week_start.strftime('%m/%d/%Y')} - {today.strftime('%m/%d/%Y')})")
                        else:
                            selected_dates = list(available_dates)
                            st.info(f"🔄 Showing all dates ({len(available_dates)} dates)")
                    
                    elif date_filter_type == "Date range":
                        date_range = st.date_input(
                            "Select date range:",
                            value=(min_date, max_date),
                            min_value=min_date,
                            max_value=max_date
                        )
                        if isinstance(date_range, tuple) and len(date_range) == 2:
                            selected_dates = [d for d in available_dates if date_range[0] <= d <= date_range[1]]
                        else:
                            selected_dates = list(available_dates)
                    
                    else:  # Specific dates
                        selected_dates = st.multiselect(
                            "Select specific dates:",
                            options=available_dates,
                            default=[],
                            format_func=lambda x: x.strftime("%m/%d/%Y") if hasattr(x, "strftime") else str(x)
                        )
                else:
                    selected_dates = []
                    st.warning("No dates found in data")
            
            # --- BRAND & VENDOR FILTERS ---
            with col2:
                st.subheader("🏷️ Filter by Brand")
                
                all_brands = sorted(processed_df["Brand"].dropna().unique())
                
                if all_brands:
                    brand_filter_type = st.radio(
                        "Brand filter type:",
                        ["All brands", "Select brands"],
                        horizontal=True
                    )
                    
                    if brand_filter_type == "Select brands":
                        selected_brands = st.multiselect(
                            "Select brands:",
                            options=all_brands,
                            default=[]
                        )
                    else:
                        selected_brands = list(all_brands)
                else:
                    selected_brands = []
                    st.warning("No brands found in data")
                
                # Vendor filter
                st.subheader("🏢 Filter by Vendor")
                
                all_vendors = sorted(processed_df["Vendor"].dropna().unique())
                
                if all_vendors:
                    vendor_filter_type = st.radio(
                        "Vendor filter type:",
                        ["All vendors", "Select vendors"],
                        horizontal=True
                    )
                    
                    if vendor_filter_type == "Select vendors":
                        selected_vendors = st.multiselect(
                            "Select vendors:",
                            options=all_vendors,
                            default=[]
                        )
                    else:
                        selected_vendors = list(all_vendors)
                else:
                    selected_vendors = []
                    st.info("No vendor data available")
            
            # --- APPLY FILTERS ---
            filtered_df = processed_df.copy()
            
            if selected_dates:
                filtered_df = filtered_df[filtered_df["Created Date"].isin(selected_dates)]
            
            if selected_brands:
                filtered_df = filtered_df[filtered_df["Brand"].isin(selected_brands)]
            
            if selected_vendors:
                filtered_df = filtered_df[filtered_df["Vendor"].isin(selected_vendors)]
            
            st.markdown("---")
            
            # --- FILTERED DATA DISPLAY ---
            st.subheader(f"📦 Filtered Packages ({len(filtered_df):,} records)")
            
            if not filtered_df.empty:
                # Select display columns
                display_cols = [
                    "Brand", "Product (Clean)", "Package Label",
                    "Quantity", "Units Per Case", "Case Labels Needed",
                    "Batch No", "Category", "Vendor", "Created Date"
                ]
                display_cols = [c for c in display_cols if c in filtered_df.columns]
                
                st.dataframe(filtered_df[display_cols], use_container_width=True, height=400)
                
                # --- LABEL GENERATION OPTIONS ---
                st.markdown("---")
                st.header("🖨️ Label Generation")
                
                gen_col1, gen_col2, gen_col3 = st.columns([2, 2, 4])
                
                with gen_col1:
                    label_mode = st.selectbox(
                        "Label Mode",
                        ["1 Label per Package", "1 Label per Case"],
                        help="Package: 1 label per package. Case: Multiple labels based on package qty ÷ units per case. All labels show Units Per Case."
                    )
                    label_mode_key = "package" if "Package" in label_mode else "case"
                
                with gen_col2:
                    st.markdown("**Label Size:**")
                    st.info(f"4\" x 2\" at {DPI} DPI")
                
                # Calculate total labels
                if label_mode_key == "package":
                    total_labels = len(filtered_df)
                else:
                    total_labels = int(filtered_df["Case Labels Needed"].sum())
                    no_case_data = filtered_df[filtered_df["Units_Per_Case_Num"] == 0]
                    if len(no_case_data) > 0:
                        st.warning(f"⚠️ {len(no_case_data)} packages missing Units Per Case - no labels for these")
                
                with gen_col3:
                    st.metric("Total Labels to Generate", f"{total_labels:,}")
                
                # --- GENERATE BUTTONS ---
                if total_labels > 0:
                    btn_col1, btn_col2 = st.columns(2)
                    
                    with btn_col1:
                        if st.button(f"📥 Generate {total_labels} Labels", type="primary", use_container_width=True):
                            try:
                                with st.spinner("Generating ZPL..."):
                                    labels = generate_all_labels(filtered_df, label_mode_key)
                                    
                                    if not labels:
                                        st.error("No labels were generated")
                                    else:
                                        zpl_content = "\n".join(labels)
                                        filename = generate_filename(filtered_df, label_mode_key)
                                        
                                        st.session_state["zpl_content"] = zpl_content
                                        st.session_state["zpl_filename"] = filename
                                        st.session_state["label_count"] = len(labels)
                                        st.success(f"Generated {len(labels)} labels!")
                            except Exception as e:
                                st.error(f"Error during generation: {str(e)}")
                    
                    with btn_col2:
                        if st.button("👀 Preview Sample Label", use_container_width=True):
                            if len(filtered_df) > 0:
                                sample_row = filtered_df.iloc[0]
                                sample_labels = generate_labels_for_row(sample_row, label_mode_key)
                                
                                if sample_labels:
                                    st.code(sample_labels[0], language="text")
                                else:
                                    st.warning("No label generated for this product")
                    
                    # Download/Print section
                    if st.session_state.get("zpl_content"):
                        st.markdown("---")
                        st.subheader("💾 Download / Print")
                        
                        dl_col1, dl_col2 = st.columns(2)
                        
                        with dl_col1:
                            st.download_button(
                                label=f"💾 Download ZPL File ({st.session_state['label_count']} labels)",
                                data=st.session_state["zpl_content"],
                                file_name=st.session_state["zpl_filename"],
                                mime="text/plain",
                                use_container_width=True
                            )
                        
                        with dl_col2:
                            st.markdown("**Or copy to clipboard:**")
                        
                        create_browser_print_launcher(
                            st.session_state["zpl_content"],
                            st.session_state["label_count"]
                        )
                else:
                    st.warning("No labels to generate with current selection")
                
                # --- CSV EXPORT ---
                st.markdown("---")
                st.subheader("💾 Export Data")
                
                csv_buffer = io.StringIO()
                filtered_df.to_csv(csv_buffer, index=False)
                
                st.download_button(
                    label="📄 Download Filtered Data CSV",
                    data=csv_buffer.getvalue(),
                    file_name=f"dc_packages_{pd.Timestamp.now().strftime('%Y%m%d_%H%M%S')}.csv",
                    mime="text/csv"
                )
            else:
                st.warning("No packages match the current filters")
        
        # ---------------------------------------------------------------------
        # TAB 2: Data Overview
        # ---------------------------------------------------------------------
        with tab2:
            st.header("📊 Data Overview")
            
            # Summary metrics
            metric_col1, metric_col2, metric_col3, metric_col4, metric_col5 = st.columns(5)
            
            with metric_col1:
                st.metric("Total Packages", len(processed_df))
            with metric_col2:
                st.metric("Unique Brands", len(processed_df["Brand"].dropna().unique()))
            with metric_col3:
                st.metric("Unique Vendors", len(processed_df["Vendor"].dropna().unique()))
            with metric_col4:
                st.metric("Total Quantity", f"{int(processed_df['Quantity_Num'].sum()):,}")
            with metric_col5:
                has_case_data = (processed_df["Units_Per_Case_Num"] > 0).sum()
                st.metric("With Case Data", f"{has_case_data:,}")
            
            # Charts
            chart_col1, chart_col2 = st.columns(2)
            
            with chart_col1:
                st.subheader("📈 Brand Breakdown")
                brand_counts = processed_df["Brand"].value_counts().head(15)
                st.bar_chart(brand_counts)
            
            with chart_col2:
                st.subheader("🏢 Vendor Breakdown")
                vendor_counts = processed_df["Vendor"].value_counts().head(15)
                st.bar_chart(vendor_counts)
            
            st.subheader("📅 Packages by Date")
            date_counts = processed_df["Created Date"].value_counts().sort_index()
            st.bar_chart(date_counts)
            
            st.subheader("🔍 Complete Dataset")
            st.dataframe(processed_df, use_container_width=True)
    
    else:
        # ---------------------------------------------------------------------
        # WELCOME SCREEN (no data loaded)
        # ---------------------------------------------------------------------
        if not packages_file and not products_file:
            st.info("👆 Upload Packages and Products CSV files in the sidebar to get started")
            
            with st.expander("ℹ️ How it Works", expanded=True):
                st.markdown(f"""
                **DC Label Generator v{VERSION}**
                
                Generate labels from Distru package exports for your distribution center.
                
                **Required Files:**
                - **Packages CSV** - Export from Distru containing package data
                - **Products CSV** - Export from Distru containing product data (Units Per Case, Vendor)
                
                **Features:**
                - 🏷️ **Brand Extraction** - Automatically extracts brand from product names
                - 📅 **Quick Date Selection** - Today, Yesterday, This Week buttons
                - 🏢 **Vendor Filtering** - Filter by vendor from Products data
                - 📦 **Two Label Modes:**
                    - **1 Label per Package** - Single label per package
                    - **1 Label per Case** - Multiple labels (qty ÷ units per case)
                
                **Label Layout (4" x 2"):**
                - Top: Black bar with Brand (white) and Category
                - Middle: Product name, UID (large, left-of-center), Created date
                - Bottom: Batch number (left), Case Qty (right)
                - Right side: QR code with package label
                """)
        elif packages_file and products_file:
            st.info("Click the 'Process Data' button in the sidebar to analyze your files")
        else:
            missing = []
            if not packages_file:
                missing.append("Packages")
            if not products_file:
                missing.append("Products")
            st.warning(f"Please upload the {' and '.join(missing)} CSV file(s)")


# =============================================================================
# ENTRY POINT
# =============================================================================

if __name__ == "__main__":
    main()