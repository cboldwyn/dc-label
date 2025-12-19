"""
DC Label Generator
==================

Version 1.0.0 - Distribution Center Package Label Generator
- Generates labels from Distru Packages and Products exports
- Filter by Created Date and Brand
- Print 1 label per package OR 1 label per case
- 4" × 2" at 203 DPI (ZD621) label format

CHANGELOG:
v1.0.0 (2025-06-XX)
- Initial release
- Package and Products CSV integration
- Brand extraction from product names
- Case quantity calculation from Products data
- Date and Brand filtering
- ZPL download and Browser Print support

Author: DC Retail
"""

import streamlit as st
import pandas as pd
import io
import math
import socket
from datetime import datetime, timedelta
from typing import Optional, Tuple, List, Dict, Any
import streamlit.components.v1 as components
import base64

# =============================================================================
# CONFIGURATION
# =============================================================================

VERSION = "1.0.0"

# Label dimensions (4" × 2" at 203 DPI)
LABEL_WIDTH = 4.0
LABEL_HEIGHT = 2.0
DPI = 203

# Page configuration
st.set_page_config(
    page_title="DC Label Generator",
    page_icon="🏷️",
    layout="wide"
)

# =============================================================================
# SESSION STATE MANAGEMENT
# =============================================================================

def initialize_session_state():
    """Initialize session state variables"""
    session_vars = ['processed_data', 'products_data', 'packages_data']
    
    for var in session_vars:
        if var not in st.session_state:
            st.session_state[var] = None

initialize_session_state()

# =============================================================================
# UTILITY FUNCTIONS
# =============================================================================

def safe_numeric(value, default=0):
    """Convert any value to numeric, handling strings, NaN, None, etc."""
    if pd.isna(value) or value is None or value == '':
        return default
    try:
        if isinstance(value, str):
            value = value.strip()
            if value == '':
                return default
        num_val = float(value)
        return int(num_val) if num_val.is_integer() else num_val
    except (ValueError, TypeError, AttributeError):
        return default

def safe_sum(series):
    """Safely sum a series that might contain strings"""
    return sum(safe_numeric(x) for x in series)

def extract_brand(product_name: str) -> Tuple[str, str]:
    """
    Extract brand and product from product name using first hyphen.
    
    Args:
        product_name: Full product name (e.g., "Camino - Strawberry Sunset Sours")
        
    Returns:
        Tuple of (brand, product_remainder)
    """
    if pd.isna(product_name) or not product_name:
        return ("", str(product_name) if product_name else "")
    
    product_name_str = str(product_name).strip()
    
    # Try splitting on " - " first (with spaces)
    if ' - ' in product_name_str:
        parts = product_name_str.split(' - ', 1)
        return (parts[0].strip(), parts[1].strip())
    
    # Try splitting on "-" without spaces
    elif '-' in product_name_str:
        parts = product_name_str.split('-', 1)
        return (parts[0].strip(), parts[1].strip())
    
    # No hyphen found - return empty brand
    return ("", product_name_str)

def load_csv(uploaded_file, file_type: str) -> Optional[pd.DataFrame]:
    """Load CSV file with string preservation"""
    try:
        uploaded_file.seek(0)
        df = pd.read_csv(uploaded_file, dtype=str)
        return df if not df.empty else None
    except Exception as e:
        st.error(f"Error loading {file_type} CSV: {str(e)}")
        return None

def sanitize_qr_data(package_label) -> str:
    """Preserve complete package label for QR code."""
    if pd.isna(package_label) or package_label is None:
        return ""
    return str(package_label).strip()

def calculate_case_labels(quantity: float, units_per_case: float) -> int:
    """Calculate number of case labels needed."""
    if quantity <= 0 or units_per_case <= 0:
        return 0
    return math.ceil(quantity / units_per_case)

def calculate_individual_case_quantities(quantity: float, units_per_case: float) -> List[float]:
    """
    Calculate individual case label quantities, handling partials correctly.
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

def merge_data_sources(packages_df: pd.DataFrame, products_df: pd.DataFrame) -> Optional[pd.DataFrame]:
    """Merge packages with products to get Units Per Case and Vendor."""
    try:
        st.session_state.packages_data = packages_df
        st.session_state.products_data = products_df
        
        # Merge on Distru Product (packages) -> Name (products)
        # Include Vendor from products
        merged_df = packages_df.merge(
            products_df[['Name', 'Units Per Case', 'Category', 'Vendor']].rename(columns={'Category': 'Product_Category'}),
            left_on='Distru Product',
            right_on='Name',
            how='left',
            suffixes=('', '_products')
        )
        
        # Extract brand from Distru Product
        merged_df['Brand'] = merged_df['Distru Product'].apply(lambda x: extract_brand(x)[0])
        merged_df['Product_Name_Clean'] = merged_df['Distru Product'].apply(lambda x: extract_brand(x)[1])
        
        # Parse Created in Distru date
        merged_df['Created_Date'] = pd.to_datetime(
            merged_df['Created in Distru At (UTC)'], 
            errors='coerce'
        ).dt.date
        
        # Convert numeric columns
        merged_df['Quantity_Num'] = merged_df['Quantity'].apply(safe_numeric)
        merged_df['Units_Per_Case_Num'] = merged_df['Units Per Case'].apply(safe_numeric)
        
        # Calculate case labels needed
        merged_df['Case_Labels_Needed'] = merged_df.apply(
            lambda row: calculate_case_labels(
                row['Quantity_Num'], 
                row['Units_Per_Case_Num']
            ) if row['Units_Per_Case_Num'] > 0 else 0,
            axis=1
        )
        
        # Use package Category if available, fallback to product category
        merged_df['Display_Category'] = merged_df['Category'].fillna(merged_df['Product_Category'])
        
        # Select and rename columns for display
        result_df = merged_df[[
            'Distru Product', 'Brand', 'Product_Name_Clean', 'Package Label',
            'Quantity', 'Quantity_Num', 'Units Per Case', 'Units_Per_Case_Num',
            'Case_Labels_Needed', 'Distru Batch Number', 'Display_Category',
            'Created_Date', 'Created in Distru At (UTC)', 'Status', 'Location', 'Vendor'
        ]].copy()
        
        result_df.columns = [
            'Product Name', 'Brand', 'Product (Clean)', 'Package Label',
            'Quantity', 'Quantity_Num', 'Units Per Case', 'Units_Per_Case_Num',
            'Case Labels Needed', 'Batch No', 'Category',
            'Created Date', 'Created At (Full)', 'Status', 'Location', 'Vendor'
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

def generate_label_zpl(product_name: str, brand: str, product_clean: str,
                      batch_no: str, qty: float, package_label: str, 
                      category: str, created_date: str, label_type: str = "Package") -> str:
    """
    Generate ZPL code for 4" × 2" label at 203 DPI.
    
    Layout:
    - Black bar with Brand (white text) and Category (right-aligned)
    - Product name (wraps to 2 lines if needed)
    - UID (Package Label) - centered, large
    - Created date - centered below UID, smaller
    - Batch number - bottom left, larger
    - Quantity - bottom right
    - QR code - right side
    """
    width_dots = int(LABEL_WIDTH * DPI)   # 812 dots
    height_dots = int(LABEL_HEIGHT * DPI)  # 406 dots
    
    # Font sizes
    fonts = {
        'extra_large': 38,
        'large': 32,
        'medium': 24,
        'large_plus': 28,
        'small': 20,
        'small_plus': 22
    }
    
    # Layout constants
    left_margin = 20
    right_margin = 20
    
    # Vertical positions
    brand_bar_y = 8
    brand_bar_height = 50
    product_y = 70
    uid_y = 180          # UID centered in middle area
    date_y = 220         # Date right below UID
    bottom_y = 360       # Bottom row for Batch and Qty
    qr_y = 120
    
    # QR code positioning
    qr_size = 5
    qr_box_size = qr_size * 30
    qr_x = width_dots - qr_box_size - 15
    
    # Calculate available width for text
    text_available_width = width_dots - left_margin - right_margin
    max_chars_brand = int(text_available_width / (fonts['large'] * 0.45))
    max_chars_product = int(text_available_width / (fonts['large'] * 0.45))
    
    # Prepare brand text
    brand_display = str(brand) if pd.notna(brand) and brand else ""
    if len(brand_display) > max_chars_brand:
        brand_display = brand_display[:max_chars_brand-3] + "..."
    
    # Prepare product text (may need wrapping)
    product_display = str(product_clean) if pd.notna(product_clean) else str(product_name)
    product_lines = []
    
    if len(product_display) > max_chars_product:
        words = product_display.split()
        current_line = ""
        
        for word in words:
            test_line = (current_line + " " + word).strip() if current_line else word
            if len(test_line) <= max_chars_product:
                current_line = test_line
            else:
                if current_line:
                    product_lines.append(current_line)
                current_line = word
        
        if current_line:
            product_lines.append(current_line)
        
        # Limit to 2 lines
        if len(product_lines) > 2:
            product_lines = product_lines[:2]
            if len(product_lines[1]) > max_chars_product - 3:
                product_lines[1] = product_lines[1][:max_chars_product-3] + "..."
    else:
        product_lines = [product_display]
    
    # QR data (UID)
    qr_data = sanitize_qr_data(package_label)
    
    # Format created date
    created_date_display = ""
    if pd.notna(created_date) and created_date:
        try:
            if isinstance(created_date, str):
                date_obj = pd.to_datetime(created_date)
            else:
                date_obj = pd.to_datetime(created_date)
            created_date_display = date_obj.strftime('%m/%d/%Y')
        except:
            created_date_display = str(created_date)
    
    # Build ZPL
    zpl_lines = ["^XA"]
    
    # INVERTED BRAND BAR - white text on black background
    zpl_lines.append(f"^FO0,{brand_bar_y}^GB{width_dots},{brand_bar_height},{brand_bar_height}^FS")
    
    # Brand text (white on black)
    brand_text_y = brand_bar_y + int((brand_bar_height - fonts['large']) / 2)
    if brand_display:
        zpl_lines.append("^FR")
        zpl_lines.append(f"^CF0,{fonts['large']}")
        zpl_lines.append(f"^FO{left_margin},{brand_text_y}^FR^FD{brand_display}^FS")
    
    # Category - right aligned (also white on black)
    category_text = str(category) if pd.notna(category) else ""
    if category_text:
        category_width = len(category_text) * int(fonts['medium'] * 0.5)
        category_x = width_dots - right_margin - category_width
        category_text_y = brand_bar_y + int((brand_bar_height - fonts['medium']) / 2)
        zpl_lines.append(f"^CF0,{fonts['medium']}")
        zpl_lines.append(f"^FO{category_x},{category_text_y}^FR^FD{category_text}^FS")
    
    # Product name - below brand bar
    zpl_lines.append(f"^CF0,{fonts['large']}")
    current_y = product_y
    for line in product_lines:
        zpl_lines.append(f"^FO{left_margin},{current_y}^FD{line}^FS")
        current_y += int(38 * 0.8)
    
    # UID (Package Label) - CENTERED, LARGE (where qty used to be)
    if qr_data:
        uid_text_width = len(qr_data) * int(fonts['extra_large'] * 0.5)
        uid_x = int((width_dots - uid_text_width) / 2)
        zpl_lines.append(f"^CF0,{fonts['extra_large']}")
        zpl_lines.append(f"^FO{uid_x},{uid_y}^FD{qr_data}^FS")
    
    # Created Date - centered below UID, smaller font
    if created_date_display:
        date_text = f"Created: {created_date_display}"
        date_text_width = len(date_text) * int(fonts['small_plus'] * 0.5)
        date_x = int((width_dots - date_text_width) / 2)
        zpl_lines.append(f"^CF0,{fonts['small_plus']}")
        zpl_lines.append(f"^FO{date_x},{date_y}^FD{date_text}^FS")
    
    # QR code - right side
    if qr_data:
        zpl_lines.append(f"^FO{qr_x},{qr_y}^BQN,2,{qr_size}^FDQA,{qr_data}^FS")
    
    # BATCH - bottom LEFT, larger size
    batch_display = str(batch_no) if pd.notna(batch_no) and batch_no else ""
    if batch_display:
        zpl_lines.append(f"^CF0,{fonts['large_plus']}")
        zpl_lines.append(f"^FO{left_margin},{bottom_y}^FDBatch: {batch_display}^FS")
    
    # QUANTITY - bottom RIGHT
    if qty == int(qty):
        qty_display = f"{label_type} Qty: {int(qty)}"
    else:
        qty_display = f"{label_type} Qty: {qty:.1f}"
    
    qty_text_width = len(qty_display) * int(fonts['large_plus'] * 0.5)
    qty_x = width_dots - right_margin - qty_text_width
    zpl_lines.append(f"^CF0,{fonts['large_plus']}")
    zpl_lines.append(f"^FO{qty_x},{bottom_y}^FD{qty_display}^FS")
    
    zpl_lines.append("^XZ")
    return "\n".join(zpl_lines)

def generate_labels_for_row(row: pd.Series, label_mode: str) -> List[str]:
    """
    Generate labels for a single row.
    
    Args:
        row: DataFrame row
        label_mode: "package" (1 per package) or "case" (1 per case)
    """
    labels = []
    
    quantity = safe_numeric(row.get('Quantity_Num', 0))
    units_per_case = safe_numeric(row.get('Units_Per_Case_Num', 0))
    created_date = row.get('Created At (Full)', '')
    
    if quantity <= 0:
        return []
    
    if label_mode == "package":
        # 1 label per package - show total quantity
        zpl = generate_label_zpl(
            product_name=row.get('Product Name', ''),
            brand=row.get('Brand', ''),
            product_clean=row.get('Product (Clean)', ''),
            batch_no=row.get('Batch No', ''),
            qty=quantity,
            package_label=row.get('Package Label', ''),
            category=row.get('Category', ''),
            created_date=created_date,
            label_type="Pkg"
        )
        labels.append(zpl)
    
    elif label_mode == "case" and units_per_case > 0:
        # 1 label per case - calculate individual case quantities
        case_quantities = calculate_individual_case_quantities(quantity, units_per_case)
        
        for case_qty in case_quantities:
            zpl = generate_label_zpl(
                product_name=row.get('Product Name', ''),
                brand=row.get('Brand', ''),
                product_clean=row.get('Product (Clean)', ''),
                batch_no=row.get('Batch No', ''),
                qty=case_qty,
                package_label=row.get('Package Label', ''),
                category=row.get('Category', ''),
                created_date=created_date,
                label_type="Case"
            )
            labels.append(zpl)
    
    return labels

def generate_all_labels(df: pd.DataFrame, label_mode: str) -> List[str]:
    """Generate all labels for the dataset."""
    all_labels = []
    
    # Sort by Brand, then Product Name
    df_sorted = df.sort_values(['Brand', 'Product Name'], ascending=[True, True])
    
    for _, row in df_sorted.iterrows():
        row_labels = generate_labels_for_row(row, label_mode)
        all_labels.extend(row_labels)
    
    return all_labels

def generate_filename(data: pd.DataFrame, label_mode: str) -> str:
    """Generate descriptive filename."""
    timestamp = pd.Timestamp.now().strftime('%Y%m%d_%H%M%S')
    
    brands = data['Brand'].dropna().unique()
    if len(brands) == 1:
        brand_part = str(brands[0]).replace(' ', '_')[:20]
    elif len(brands) <= 3:
        brand_part = '_'.join([str(b).replace(' ', '_')[:10] for b in brands])[:30]
    else:
        brand_part = f"Multiple_{len(brands)}brands"
    
    mode_part = "per_package" if label_mode == "package" else "per_case"
    
    return f"dc_labels_{brand_part}_{mode_part}_{timestamp}.zpl"

# =============================================================================
# BROWSER PRINT INTEGRATION
# =============================================================================

def create_browser_print_launcher(zpl_data: str, label_count: int) -> None:
    """Create a launcher for Browser Print that works with Streamlit Cloud."""
    
    b64_zpl = base64.b64encode(zpl_data.encode()).decode()
    
    html_content = f"""
    <div style="padding: 20px; border: 2px solid #4CAF50; border-radius: 10px; background-color: #f9f9f9;">
        <h3 style="color: #333; margin-top: 0;">🖨️ Ready to Print {label_count} Labels</h3>
        
        <p style="color: #666;">Choose your printing method:</p>
        
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
                    <li>Open Zebra Setup Utilities or send via network</li>
                    <li>Paste the ZPL code and send to printer</li>
                </ol>
            </div>
        </details>
    </div>
    
    <script>
        const zplData = atob('{b64_zpl}');
        
        function copyToClipboard() {{
            const statusDiv = document.getElementById('status');
            
            navigator.clipboard.writeText(zplData).then(() => {{
                statusDiv.style.display = 'block';
                statusDiv.style.backgroundColor = '#d4edda';
                statusDiv.style.color = '#155724';
                statusDiv.innerHTML = '✅ ZPL copied to clipboard!';
            }}).catch(() => {{
                const textarea = document.createElement('textarea');
                textarea.value = zplData;
                textarea.style.position = 'fixed';
                textarea.style.opacity = '0';
                document.body.appendChild(textarea);
                textarea.select();
                document.execCommand('copy');
                document.body.removeChild(textarea);
                
                statusDiv.style.display = 'block';
                statusDiv.style.backgroundColor = '#d4edda';
                statusDiv.style.color = '#155724';
                statusDiv.innerHTML = '✅ ZPL copied to clipboard!';
            }});
        }}
    </script>
    """
    
    components.html(html_content, height=250)

# =============================================================================
# MAIN APPLICATION
# =============================================================================

def main():
    st.title("🏷️ DC Label Generator")
    st.markdown("**DC Retail** | Generate labels from Distru package exports")
    
    # Sidebar - Data Sources
    st.sidebar.header("📊 Data Sources")
    
    st.sidebar.subheader("📦 Packages")
    packages_file = st.sidebar.file_uploader(
        "Choose Packages CSV", type=['csv'], key="packages_upload"
    )
    
    st.sidebar.subheader("📋 Products")
    products_file = st.sidebar.file_uploader(
        "Choose Products CSV", type=['csv'], key="products_upload"
    )
    
    # Process button
    if st.sidebar.button("🚀 Process Data", type="primary", 
                        disabled=not (packages_file and products_file)):
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
    
    # Main Content
    if st.session_state.processed_data is not None:
        processed_df = st.session_state.processed_data
        
        tab1, tab2 = st.tabs(["🎯 Generate Labels", "📊 Data Overview"])
        
        with tab1:
            st.header("🎯 Generate Labels")
            
            # Filters
            col1, col2 = st.columns(2)
            
            with col1:
                # Date filter
                st.subheader("📅 Filter by Created Date")
                
                available_dates = sorted(processed_df['Created Date'].dropna().unique())
                
                if available_dates:
                    min_date = min(available_dates)
                    max_date = max(available_dates)
                    
                    # Quick date selection buttons
                    st.markdown("**Quick Select:**")
                    quick_col1, quick_col2, quick_col3, quick_col4 = st.columns(4)
                    
                    today = datetime.now().date()
                    yesterday = today - timedelta(days=1)
                    week_start = today - timedelta(days=today.weekday())  # Monday of this week
                    
                    with quick_col1:
                        if st.button("📅 Today", use_container_width=True):
                            st.session_state['date_selection'] = 'today'
                    with quick_col2:
                        if st.button("⏪ Yesterday", use_container_width=True):
                            st.session_state['date_selection'] = 'yesterday'
                    with quick_col3:
                        if st.button("📆 This Week", use_container_width=True):
                            st.session_state['date_selection'] = 'this_week'
                    with quick_col4:
                        if st.button("🔄 All Dates", use_container_width=True):
                            st.session_state['date_selection'] = 'all'
                    
                    # Initialize date selection state
                    if 'date_selection' not in st.session_state:
                        st.session_state['date_selection'] = 'all'
                    
                    # Determine selected dates based on quick selection or manual
                    date_filter_type = st.radio(
                        "Or select manually:",
                        ["Use quick selection", "Date range", "Specific dates"],
                        horizontal=True
                    )
                    
                    if date_filter_type == "Use quick selection":
                        if st.session_state['date_selection'] == 'today':
                            selected_dates = [d for d in available_dates if d == today]
                            st.info(f"📅 Showing packages from today ({today.strftime('%m/%d/%Y')})")
                        elif st.session_state['date_selection'] == 'yesterday':
                            selected_dates = [d for d in available_dates if d == yesterday]
                            st.info(f"⏪ Showing packages from yesterday ({yesterday.strftime('%m/%d/%Y')})")
                        elif st.session_state['date_selection'] == 'this_week':
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
                            selected_dates = [d for d in available_dates 
                                            if date_range[0] <= d <= date_range[1]]
                        else:
                            selected_dates = list(available_dates)
                    else:  # Specific dates
                        selected_dates = st.multiselect(
                            "Select specific dates:",
                            options=available_dates,
                            default=[],
                            format_func=lambda x: x.strftime('%m/%d/%Y') if hasattr(x, 'strftime') else str(x)
                        )
                else:
                    selected_dates = []
                    st.warning("No dates found in data")
            
            with col2:
                # Brand filter
                st.subheader("🏷️ Filter by Brand")
                
                all_brands = sorted(processed_df['Brand'].dropna().unique())
                
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
                
                all_vendors = sorted(processed_df['Vendor'].dropna().unique())
                
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
            
            # Apply filters
            filtered_df = processed_df.copy()
            
            if selected_dates:
                filtered_df = filtered_df[filtered_df['Created Date'].isin(selected_dates)]
            
            if selected_brands:
                filtered_df = filtered_df[filtered_df['Brand'].isin(selected_brands)]
            
            if selected_vendors:
                filtered_df = filtered_df[filtered_df['Vendor'].isin(selected_vendors)]
            
            st.markdown("---")
            
            # Data display
            st.subheader(f"📦 Filtered Packages ({len(filtered_df):,} records)")
            
            if not filtered_df.empty:
                # Display columns
                display_cols = [
                    'Brand', 'Product (Clean)', 'Package Label', 
                    'Quantity', 'Units Per Case', 'Case Labels Needed',
                    'Batch No', 'Category', 'Vendor', 'Created Date'
                ]
                display_cols = [c for c in display_cols if c in filtered_df.columns]
                
                st.dataframe(filtered_df[display_cols], use_container_width=True, height=400)
                
                # Label generation options
                st.markdown("---")
                st.header("🖨️ Label Generation")
                
                col1, col2, col3 = st.columns([2, 2, 4])
                
                with col1:
                    label_mode = st.selectbox(
                        "Label Mode",
                        ["1 Label per Package", "1 Label per Case"],
                        help="Package: 1 label showing total qty. Case: Multiple labels, one per case."
                    )
                    label_mode_key = "package" if "Package" in label_mode else "case"
                
                with col2:
                    st.markdown("**Label Size:**")
                    st.info(f"4\" × 2\" at {DPI} DPI")
                
                # Calculate total labels
                if label_mode_key == "package":
                    total_labels = len(filtered_df)
                else:
                    total_labels = int(filtered_df['Case Labels Needed'].sum())
                    # Count packages without Units Per Case data
                    no_case_data = filtered_df[filtered_df['Units_Per_Case_Num'] == 0]
                    if len(no_case_data) > 0:
                        st.warning(f"⚠️ {len(no_case_data)} packages missing Units Per Case data - no case labels will be generated for these")
                
                with col3:
                    st.metric("Total Labels to Generate", f"{total_labels:,}")
                
                if total_labels > 0:
                    col1, col2 = st.columns(2)
                    
                    with col1:
                        if st.button(f"📥 Generate {total_labels} Labels", type="primary", use_container_width=True):
                            try:
                                with st.spinner("Generating ZPL..."):
                                    labels = generate_all_labels(filtered_df, label_mode_key)
                                    
                                    if not labels:
                                        st.error("No labels were generated")
                                    else:
                                        zpl_content = "\n".join(labels)
                                        filename = generate_filename(filtered_df, label_mode_key)
                                        
                                        st.session_state['zpl_content'] = zpl_content
                                        st.session_state['zpl_filename'] = filename
                                        st.session_state['label_count'] = len(labels)
                                        st.success(f"Generated {len(labels)} labels!")
                            except Exception as e:
                                st.error(f"Error during generation: {str(e)}")
                                import traceback
                                st.error(traceback.format_exc())
                    
                    with col2:
                        if st.button("👀 Preview Sample Label", use_container_width=True):
                            if len(filtered_df) > 0:
                                sample_row = filtered_df.iloc[0]
                                sample_labels = generate_labels_for_row(sample_row, label_mode_key)
                                
                                if sample_labels:
                                    st.code(sample_labels[0], language="text")
                                else:
                                    st.warning("No label generated for this product")
                    
                    # Download/Print section
                    if 'zpl_content' in st.session_state and st.session_state['zpl_content']:
                        st.markdown("---")
                        st.subheader("💾 Download / Print")
                        
                        col1, col2 = st.columns(2)
                        
                        with col1:
                            st.download_button(
                                label=f"💾 Download ZPL File ({st.session_state['label_count']} labels)",
                                data=st.session_state['zpl_content'],
                                file_name=st.session_state['zpl_filename'],
                                mime="text/plain",
                                use_container_width=True
                            )
                        
                        with col2:
                            st.markdown("**Or copy to clipboard:**")
                        
                        create_browser_print_launcher(
                            st.session_state['zpl_content'], 
                            st.session_state['label_count']
                        )
                else:
                    st.warning("No labels to generate with current selection")
                
                # CSV Export
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
        
        with tab2:
            st.header("📊 Data Overview")
            
            col1, col2, col3, col4, col5 = st.columns(5)
            
            with col1:
                st.metric("Total Packages", len(processed_df))
            with col2:
                st.metric("Unique Brands", len(processed_df['Brand'].dropna().unique()))
            with col3:
                st.metric("Unique Vendors", len(processed_df['Vendor'].dropna().unique()))
            with col4:
                st.metric("Total Quantity", f"{int(processed_df['Quantity_Num'].sum()):,}")
            with col5:
                has_case_data = (processed_df['Units_Per_Case_Num'] > 0).sum()
                st.metric("With Case Data", f"{has_case_data:,}")
            
            col1, col2 = st.columns(2)
            
            with col1:
                st.subheader("📈 Brand Breakdown")
                brand_counts = processed_df['Brand'].value_counts().head(15)
                st.bar_chart(brand_counts)
            
            with col2:
                st.subheader("🏢 Vendor Breakdown")
                vendor_counts = processed_df['Vendor'].value_counts().head(15)
                st.bar_chart(vendor_counts)
            
            st.subheader("📅 Packages by Date")
            date_counts = processed_df['Created Date'].value_counts().sort_index()
            st.bar_chart(date_counts)
            
            st.subheader("🔍 Complete Dataset")
            st.dataframe(processed_df, use_container_width=True)
    
    else:
        # Welcome screen
        if not packages_file and not products_file:
            st.info("👆 Upload Packages and Products CSV files in the sidebar to get started")
            
            with st.expander("ℹ️ How it Works", expanded=True):
                st.markdown(f"""
                **DC Label Generator v{VERSION}**
                
                Generate labels from Distru package exports for your distribution center.
                
                **Required Files:**
                - **Packages CSV** - Export from Distru containing package data
                - **Products CSV** - Export from Distru containing product data (for Units Per Case)
                
                **Features:**
                - 🏷️ **Brand Extraction** - Automatically extracts brand from product names
                - 📅 **Date Filtering** - Filter by package creation date
                - 🔍 **Brand Filtering** - Filter by specific brands
                - 📦 **Two Label Modes:**
                    - **1 Label per Package** - Single label showing total quantity
                    - **1 Label per Case** - Multiple labels based on Units Per Case
                
                **Label Format (4" × 2"):**
                - Black bar with Brand name (white text) and Category
                - Product name (wraps to 2 lines if needed)
                - Batch number
                - Quantity (centered, bold)
                - QR code with package label
                - Package label ID at bottom
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

if __name__ == "__main__":
    main()