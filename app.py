"""
DC Label Generator
==================

Version 1.1.6 - Distribution Center Package Label Generator

Generates ZPL labels from Distru Packages and Products exports for Zebra printers.
Supports filtering by Created Date, Brand, and Vendor with options for per-package
or per-case label generation.

Label Format: 4" x 2" at 203 DPI (ZD621)

CHANGELOG:
v1.1.6 (2025-01-15)
- Fixed Status filter to default to only "Active" (not all statuses)
- Fixed cascading filters to include date filter first
- Filter cascade order: Date → Status → Brand → Vendor
- Brand/Vendor lists now only show items matching selected date + status

v1.1.5 (2025-01-15)
- Redesigned filters: Status → Brand → Vendor (cascading)
- Filters now cascade - selecting brands limits vendor options
- Simplified filter UX (removed radio buttons)
- Status defaults to "Active" on load
- Hidden row index, reordered columns (Override, Case Qty first)

v1.1.4 (2025-01-15)
- Added Label Override column for custom label counts per product
- Changed default date filter to "Today"
- Changed default status filter to "Active"

v1.1.3 (2025-01-15)
- Fixed timezone issue: Now uses Pacific time for date filtering
- Resolves "Today" showing wrong date on Streamlit Cloud (UTC servers)

v1.1.2 (2025-01-15)
- Added Status filter from Packages import

v1.1.1 (2025-01-15)
- Labels now sorted by UID (Package Label) for consistent ordering

v1.1.0 (2025-01-15)
- Added weekly rotating symbol (18-week cycle)
- Symbols help distinguish batches received at different times
- Icons: house, sun, tree, car, cloud, envelope, ladder, key, anchor,
         lightbulb, lock, umbrella, flag, trashcan, clock, mug, book, rabbit

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
from zoneinfo import ZoneInfo


# =============================================================================
# CONFIGURATION CONSTANTS
# =============================================================================

VERSION = "1.1.6"

# Timezone - always use Pacific time for date filtering
TIMEZONE = ZoneInfo("America/Los_Angeles")

# Label specifications for ZD621 printer
LABEL_WIDTH = 4.0    # inches
LABEL_HEIGHT = 2.0   # inches
DPI = 203            # dots per inch

# Week symbol configuration
WEEK_SYMBOL_SIZE = 40  # Size in dots (40x40 pixels)

# Pre-converted ZPL hex data for 18 rotating weekly symbols
# Format: ^GFA,total_bytes,total_bytes,bytes_per_row,hex_data
WEEK_ICONS = {
    1: {
        "name": "house",
        "width": 40,
        "height": 40,
        "bytes_per_row": 5,
        "total_bytes": 200,
        "hex": "00000000000000000000000008000000000C0000000016000000006300000000C18000000180D6000001007E000002007E00000C007E000018007E000030007E000020007E00004000018001800000C00300000020077FFFFF7007FFFFFFF001800000C001800000C001800000C001800000C001800000C001800000C00180FF80C00180C180C00180C080C00180C080C00180C080C00180C080C00180C080C00180C080C00180C080C00180C080C00180C080C001FFFFFFC000FFFFFF800000000000"
    },
    2: {
        "name": "sun",
        "width": 40,
        "height": 40,
        "bytes_per_row": 5,
        "total_bytes": 200,
        "hex": "0000000000000000000000000000000000080000000008000000000800000000080000000008004001800800C000400801800020000200001800040000003E040000007F00000000C08000000100400000020020000006001000000C001800000C0018001FCC0019FE000C001800000C001800000400180000020030000001004000000080800000007F800000003F000000180004000020000200004008010000C00800C00180080040000008000000000800000000080000000008000000000800000000000000"
    },
    3: {
        "name": "tree",
        "width": 40,
        "height": 40,
        "bytes_per_row": 5,
        "total_bytes": 200,
        "hex": "000000000000000000000000000000000000000000000000000000FF800000030060000007007000000C0008000018000400002000020000400001000040000180004000018001800000C001800000C001800000C001800000C001800000C001800000C000400001800040000180006000030000300002000018000400000CFF98000003FFF0000003FFE0000000FF80000000FF80000000FF80000000FF80000000FF80000000FF80000000FF80000000FF80000000FF80000000FF80000000FF80000000000000"
    },
    4: {
        "name": "car",
        "width": 40,
        "height": 40,
        "bytes_per_row": 5,
        "total_bytes": 200,
        "hex": "0000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000007FFF000000FFFF8000030000600004000018003800000E0030000007004000000100400000010040000001004000000100438000E10043C001E10044200319007FFFFFFF001818060C001810040C000810060C00042003180003C001E00000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000"
    },
    5: {
        "name": "cloud",
        "width": 40,
        "height": 40,
        "bytes_per_row": 5,
        "total_bytes": 200,
        "hex": "0000000000000000000000000000000000000000000000000000000000000000000000000003E000000007F0000000180C0000006002000000C00100000EC00180001F80018000613000C00181087E4003010481C003010680C0020107004004010700600400CB01900400C90190040049031004002B02100400190C100300000010030000002001FFFFFFE000FFFFFFE000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000"
    },
    6: {
        "name": "envelope",
        "width": 40,
        "height": 40,
        "bytes_per_row": 5,
        "total_bytes": 200,
        "hex": "000000000000000000000000000000000000000000000000000000000000000000000007FFFFFFF03FFFFFFFFE180000000E3400000016338000006631C00000E6304000010630200002063018000406300C000806300600100630020020063001C0C0063000630006300036000630001C00063000080006300000000630000000063000000006300000000630000000063000000006300000000630000000063FFFFFFFFE1FFFFFFFFC000000000000000000000000000000000000000000000000000000000000"
    },
    7: {
        "name": "ladder",
        "width": 40,
        "height": 40,
        "bytes_per_row": 5,
        "total_bytes": 200,
        "hex": "0000000000000000000000200002000020000200002000020000200002000020000200003FFFFE00003FFFFE00002000020000200002000020000200002000020000200002000020000200003FFFFE00003000020000200002000020000200002000020000200002000020000200003FFFFE00003FFFFE00002000020000200002000020000200002000020000200002000020000200003FFFFE00003000020000200002000020000200002000020000200002000020000200002000020000200002000000000000"
    },
    8: {
        "name": "key",
        "width": 40,
        "height": 40,
        "bytes_per_row": 5,
        "total_bytes": 200,
        "hex": "00000000000000000000000000000000000000000000000000007E000000008100000001018000000200C000000400600000040060000004007FFFF004007FFFF004006018C004006018C00300C018C001818018C000FF001800007E000800000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000"
    },
    9: {
        "name": "anchor",
        "width": 40,
        "height": 40,
        "bytes_per_row": 5,
        "total_bytes": 200,
        "hex": "0000000000000000000000001C000000003E000000006300000000C880000000C880000000C880000000C9800000006B000000001E000000000800000007FFF0000007FFF80000000800000000080000000008000000000800000000080000000008000000000800000000080000000008000000000800000000080000000008000000000800000000080000040008001004000800100300080020018008004000E00803800060080300001E003C000001FFC0000000000000000000000000000000000000000000"
    },
    10: {
        "name": "lightbulb",
        "width": 40,
        "height": 40,
        "bytes_per_row": 5,
        "total_bytes": 200,
        "hex": "0000000000000000000000003E000000007F0000000180C00000020030000004001800000800080000180004000018000400002000020000200002000020000200002000020000200002000020000200001000040000180004000018000C00000C0018000002003000000180C0000001FFC0000001FFC00000010040000001FFC00000010040000001A6C0000001FFC00000010040000001FFC0000000C180000000C080000000C1800000003F000000000000000000000000000000000000000000000000000000"
    },
    11: {
        "name": "lock",
        "width": 40,
        "height": 40,
        "bytes_per_row": 5,
        "total_bytes": 200,
        "hex": "000000000000000000000000000000000000000000000000000000FF800000030060000007007000000C0008000018000400002000020000200002000020000200002000020000200002000020000200002000020000FFFFFF8001FFFFFFC001800000C001800000C001800000C001800000C001800000C001801E00C001803F00C001807F00C001807F00C001803F00C001801C00C001800000C001800000C001800000C001800000C001800000C001FFFFFFC00000000000000000000000000000000000000000"
    },
    12: {
        "name": "umbrella",
        "width": 40,
        "height": 40,
        "bytes_per_row": 5,
        "total_bytes": 200,
        "hex": "00000000000000000000000000000000000000000000000000000000000000000000000001FFC0000001FFC000001E003C00006000030000800000C0010000006002000000200400000010080000000C080000000C1000000004300000000630000000063FFFFFFFFE00000C000000000800000000080000000008000000000800000000080000000008000000000800000000080000000008000000000800000000080000000008000000010840000001084000000080800000007F800000003F00000000000000"
    },
    13: {
        "name": "flag",
        "width": 40,
        "height": 40,
        "bytes_per_row": 5,
        "total_bytes": 200,
        "hex": "0000000000000000000000000000000180000000018000000000C000000001BC00000001BFC000000183E0000001801E0000018003C0000180003E00018000118001800001C00180001E00018001F00001801E00000181FC00000181E0000001BE00000000C00000000180000000018000000001800000000180000000018000000001800000000180000000018000000001800000000180000000018000000001800000000180000000018000000001800000000180000000018000000000800000000000000000"
    },
    14: {
        "name": "trashcan",
        "width": 40,
        "height": 40,
        "bytes_per_row": 5,
        "total_bytes": 200,
        "hex": "000000000000000000000000000000000000000000000000000001FFC000000180400000010040000001004000000100400000FFFFFFC0003000030000200002000020000200002000020000210842000021084200002108420000210842000021084200002108420000210842000021084200002108420000210842000021084200002108420000210842000021084200002108420000210842000020000200002000020000200002000020000200003FFFFE000000000000000000000000000000000000000000"
    },
    15: {
        "name": "clock",
        "width": 40,
        "height": 40,
        "bytes_per_row": 5,
        "total_bytes": 200,
        "hex": "0000000000000000000000007F80000000FF8000000F0078000018000400006000030000E000038001800800400300080020030008002006000800100C00080018080008000C080008000C080008000C100008000630001C000630001E000630007F000630003FFE0630007F000630003E000630001C00063000000006080000000C080000000C080000000C0800000008040000001003000000200300000020010000004000800000C000600003000018000400000F0078000007FFF0000000FF80000000000000"
    },
    16: {
        "name": "mug",
        "width": 40,
        "height": 40,
        "bytes_per_row": 5,
        "total_bytes": 200,
        "hex": "000000000000000000000000000000000000000000000000000000000000000000000000FFFFFE0001FFFFFE00018000020001FFFFFE0001800002000180000300018000038001800002400180000220018000022001800002300180000210018000021001800002100180000210018000021001800002100180000220018000022001800002400180000380018000030001800002000180000200018000020001FFFFFE0000FFFFFE00000000000000000000000000000000000000000000000000000000000000"
    },
    17: {
        "name": "book",
        "width": 40,
        "height": 40,
        "bytes_per_row": 5,
        "total_bytes": 200,
        "hex": "0000000000000000000000000000000000000000000000000000FFFFFE00018C0003C0018C0003F0018C000230018C000210018C000210018C000210018C3FC210018C3FC210018C000210018C000210018C000210018C3FC210018C3FC210018C000210018C000210018C000210018C000210018C000210018C000210018C000210018C000210018C000210018C000210018C000210018C000210018C000210018C000210018C000210018C00026001FFFFFF800000000000000000000000000000000000000000"
    },
    18: {
        "name": "rabbit",
        "width": 40,
        "height": 40,
        "bytes_per_row": 5,
        "total_bytes": 200,
        "hex": "0000000000000000000000020020000006003000000D0048000018C084000018C084000010410600002063020000206302000020630200002063020000206302000020630200002063020000203F02000019C0C400001380E4000006003000000C00180000180004000018000400001000060000200002000020000200002000020000200002000020000200002000020000180004000018000400000C000800000600100000020020000001C0C00000007F00000000000000000000000000000000000000000000"
    },
}


# =============================================================================
# PAGE SETUP
# =============================================================================

st.set_page_config(
    page_title=f"DC Label Generator v{VERSION}",
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
        "date_selection": "today",  # Default to today
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
    Uses the first hyphen as the delimiter.
    """
    if pd.isna(product_name) or not product_name:
        return ("", str(product_name) if product_name else "")
    
    product_str = str(product_name).strip()
    
    if " - " in product_str:
        parts = product_str.split(" - ", 1)
        return (parts[0].strip(), parts[1].strip())
    
    if "-" in product_str:
        parts = product_str.split("-", 1)
        return (parts[0].strip(), parts[1].strip())
    
    return ("", product_str)


def load_csv(uploaded_file, file_type):
    """Load a CSV file into a DataFrame with all columns as strings."""
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
    """Clean and validate package label for QR code generation."""
    if pd.isna(package_label) or package_label is None:
        return ""
    return str(package_label).strip()


def calculate_case_labels_needed(quantity, units_per_case):
    """Calculate how many case labels are needed for a package."""
    if quantity <= 0 or units_per_case <= 0:
        return 0
    return math.ceil(quantity / units_per_case)


def calculate_individual_case_quantities(quantity, units_per_case):
    """Calculate the quantity for each individual case label."""
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
# WEEK SYMBOL FUNCTIONS
# =============================================================================

def get_week_number(date_value=None):
    """
    Get the week number (1-18) for symbol rotation based on date.
    
    Uses the package created date if provided, otherwise uses current date.
    Symbols rotate on an 18-week cycle.
    
    Args:
        date_value: Optional date string or datetime. If None, uses today.
        
    Returns:
        int: Week number 1-18 for symbol selection
    """
    try:
        if date_value is not None and pd.notna(date_value):
            date_obj = pd.to_datetime(date_value)
        else:
            date_obj = datetime.now(TIMEZONE)
        
        # Get ISO week number (1-52/53)
        iso_week = date_obj.isocalendar()[1]
        
        # Convert to 1-18 cycle
        return ((iso_week - 1) % 18) + 1
    except (ValueError, TypeError):
        return 1  # Default to week 1 symbol


def get_week_icon_name(week_num):
    """Get the icon name for a given week number."""
    week_num = ((week_num - 1) % 18) + 1  # Ensure 1-18 range
    return WEEK_ICONS.get(week_num, {}).get("name", "unknown")


def generate_week_symbol_zpl(week_num, x, y):
    """
    Generate ZPL commands to draw the weekly symbol at specified position.
    
    Args:
        week_num: Week number 1-18 (cycles automatically)
        x: X position in dots
        y: Y position in dots
        
    Returns:
        String of ZPL commands for the graphic
    """
    # Ensure week_num is in 1-18 range
    week_num = ((week_num - 1) % 18) + 1
    
    icon = WEEK_ICONS.get(week_num)
    if not icon:
        return ""
    
    # ZPL ^GF command: Graphic Field
    # Format: ^GFA,total_bytes,total_bytes,bytes_per_row,hex_data
    zpl = f"^FO{x},{y}^GFA,{icon['total_bytes']},{icon['total_bytes']},{icon['bytes_per_row']},{icon['hex']}^FS"
    
    return zpl


# =============================================================================
# DATA PROCESSING
# =============================================================================

def merge_data_sources(packages_df, products_df):
    """
    Merge Packages and Products data to create the working dataset.
    """
    try:
        st.session_state.packages_data = packages_df
        st.session_state.products_data = products_df
        
        products_subset = products_df[["Name", "Units Per Case", "Category", "Vendor"]].copy()
        products_subset = products_subset.rename(columns={"Category": "Product_Category"})
        
        merged_df = packages_df.merge(
            products_subset,
            left_on="Distru Product",
            right_on="Name",
            how="left",
            suffixes=("", "_products")
        )
        
        merged_df["Brand"] = merged_df["Distru Product"].apply(lambda x: extract_brand(x)[0])
        merged_df["Product_Name_Clean"] = merged_df["Distru Product"].apply(lambda x: extract_brand(x)[1])
        
        merged_df["Created_Date"] = pd.to_datetime(
            merged_df["Created in Distru At (UTC)"],
            errors="coerce"
        ).dt.date
        
        merged_df["Quantity_Num"] = merged_df["Quantity"].apply(safe_numeric)
        merged_df["Units_Per_Case_Num"] = merged_df["Units Per Case"].apply(safe_numeric)
        
        merged_df["Case_Labels_Needed"] = merged_df.apply(
            lambda row: calculate_case_labels_needed(
                row["Quantity_Num"],
                row["Units_Per_Case_Num"]
            ) if row["Units_Per_Case_Num"] > 0 else 0,
            axis=1
        )
        
        merged_df["Display_Category"] = merged_df["Category"].fillna(merged_df["Product_Category"])
        
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
    | Batch: ABC-123    [ICON]                    Case Qty: 25  |
    +-----------------------------------------------------------+
    
    Args:
        product_name: Full product name (fallback if product_clean empty)
        brand: Brand name for top bar
        product_clean: Cleaned product name (without brand)
        batch_no: Batch/lot number
        qty: Units Per Case from Products table (displayed as "Case Qty")
        package_label: UID for QR code and center display
        category: Product category for top bar
        created_date: Package creation date (also used for week symbol selection)
        
    Returns:
        Complete ZPL code string for the label
    """
    # Calculate dimensions in dots
    width_dots = int(LABEL_WIDTH * DPI)   # 812 dots
    
    # Font size definitions (in dots)
    font_uid = 46
    font_large = 32
    font_large_plus = 28
    font_medium = 24
    font_small_plus = 22
    
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
    
    # Get week number for symbol
    week_num = get_week_number(created_date)
    
    # Build ZPL command list
    zpl = []
    zpl.append("^XA")  # Start format
    
    # --- BLACK BRAND BAR (inverted colors) ---
    zpl.append(f"^FO0,{brand_bar_y}^GB{width_dots},{brand_bar_height},{brand_bar_height}^FS")
    
    # Brand text (white on black via field reverse)
    brand_text_y = brand_bar_y + (brand_bar_height - font_large) // 2
    if brand_display:
        zpl.append("^FR")
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
        available_width = qr_x - left_margin - 20
        uid_x = left_margin + (available_width - uid_width) // 2
        if uid_x < left_margin:
            uid_x = left_margin
        zpl.append(f"^CF0,{font_uid}")
        zpl.append(f"^FO{uid_x},{uid_y}^FD{qr_data}^FS")
    
    # --- CREATED DATE (centered in area left of QR code, below UID) ---
    if created_date_display:
        date_text = f"Created: {created_date_display}"
        date_width = len(date_text) * (font_small_plus // 2)
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
    
    # --- WEEK SYMBOL (bottom center) ---
    # Position between batch and case qty
    symbol_x = (width_dots // 2) - (WEEK_SYMBOL_SIZE // 2)
    symbol_y = bottom_y - 4  # Slight vertical adjustment to center with text
    week_symbol_zpl = generate_week_symbol_zpl(week_num, symbol_x, symbol_y)
    if week_symbol_zpl:
        zpl.append(week_symbol_zpl)
    
    # --- CASE QUANTITY (bottom right) ---
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
    """Generate all labels needed for a single package row."""
    labels = []
    
    quantity = safe_numeric(row.get("Quantity_Num", 0))
    units_per_case = safe_numeric(row.get("Units_Per_Case_Num", 0))
    created_date = row.get("Created At (Full)", "")
    
    if quantity <= 0:
        return []
    
    units_per_case_display = units_per_case if units_per_case > 0 else None
    
    if label_mode == "package":
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
        num_cases = calculate_case_labels_needed(quantity, units_per_case)
        
        for _ in range(num_cases):
            zpl = generate_label_zpl(
                product_name=row.get("Product Name", ""),
                brand=row.get("Brand", ""),
                product_clean=row.get("Product (Clean)", ""),
                batch_no=row.get("Batch No", ""),
                qty=units_per_case,
                package_label=row.get("Package Label", ""),
                category=row.get("Category", ""),
                created_date=created_date
            )
            labels.append(zpl)
    
    return labels


def generate_all_labels(df, label_mode):
    """
    Generate labels for all rows in the DataFrame, sorted by UID.
    
    If a row has a "Label Override" value, that exact number of labels is generated.
    Otherwise, the label_mode determines the count (1 per package or 1 per case).
    """
    all_labels = []
    
    # Sort by Package Label (UID) for consistent ordering
    df_sorted = df.sort_values(["Package Label"], ascending=[True])
    
    for idx, row in df_sorted.iterrows():
        override = row.get("Label Override")
        
        # Check if override is set (not None/NaN and > 0)
        if pd.notna(override) and int(override) > 0:
            # Generate the override number of labels
            override_count = int(override)
            created_date = row.get("Created At (Full)", "")
            units_per_case = safe_numeric(row.get("Units_Per_Case_Num", 0))
            units_per_case_display = units_per_case if units_per_case > 0 else None
            
            for _ in range(override_count):
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
                all_labels.append(zpl)
        elif pd.notna(override) and int(override) == 0:
            # Override of 0 means skip this row
            continue
        else:
            # No override - use normal label mode
            row_labels = generate_labels_for_row(row, label_mode)
            all_labels.extend(row_labels)
    
    return all_labels


def generate_filename(data, label_mode):
    """Generate a descriptive filename for the ZPL download."""
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
    """Create an HTML component for copying ZPL to clipboard."""
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
    
    st.title(f"🏷️ DC Label Generator v{VERSION}")
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
                # Reset status filter to allow new defaults
                if "status_filter_selection" in st.session_state:
                    del st.session_state["status_filter_selection"]
                st.success(f"Successfully processed {len(processed_data):,} packages")
    
    # Week symbol reference
    st.sidebar.markdown("---")
    with st.sidebar.expander("🗓️ Week Symbols (18-week cycle)"):
        # Show current week symbol
        current_week = get_week_number()
        current_icon = get_week_icon_name(current_week)
        st.markdown(f"**Current week:** {current_week} ({current_icon})")
        st.markdown("---")
        st.markdown("**Symbol Rotation:**")
        for i in range(1, 19):
            icon_name = WEEK_ICONS[i]["name"]
            marker = " ← current" if i == current_week else ""
            st.markdown(f"{i}. {icon_name}{marker}")
    
    # Changelog
    with st.sidebar.expander("📋 Version History & Changelog"):
        st.markdown("""
        **v1.1.6** (Current)
        - Fixed Status default to only "Active"
        - Full cascade: Date → Status → Brand → Vendor
        
        **v1.1.5** (2025-01-15)
        - Cascading filters, simplified UX
        - Hidden row index, reordered columns
        
        **v1.1.4** (2025-01-15)
        - Added Label Override column
        - Default date: Today, status: Active
        
        **v1.1.3** (2025-01-15)
        - Fixed timezone (Pacific time)
        
        **v1.1.2** (2025-01-15)
        - Added Status filter
        
        **v1.1.1** (2025-01-15)
        - Labels sorted by UID
        
        **v1.1.0** (2025-01-15)
        - Weekly rotating symbols (18-week)
        
        **v1.0.0** (2025-12-19)
        - Initial release
        """)
    
    # Version info at bottom
    st.sidebar.markdown("---")
    st.sidebar.markdown(f"**Version {VERSION}**")
    
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
            
            col1, col2 = st.columns(2)
            
            # --- DATE FILTER ---
            with col1:
                st.subheader("📅 Filter by Created Date")
                
                available_dates = sorted(processed_df["Created Date"].dropna().unique())
                
                if available_dates:
                    min_date = min(available_dates)
                    max_date = max(available_dates)
                    
                    st.markdown("**Quick Select:**")
                    qcol1, qcol2, qcol3, qcol4 = st.columns(4)
                    
                    # Use Pacific timezone for date calculations
                    today = datetime.now(TIMEZONE).date()
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
                    
                    date_filter_type = st.radio(
                        "Or select manually:",
                        ["Use quick selection", "Date range", "Specific dates"],
                        horizontal=True
                    )
                    
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
                    
                    else:
                        selected_dates = st.multiselect(
                            "Select specific dates:",
                            options=available_dates,
                            default=[],
                            format_func=lambda x: x.strftime("%m/%d/%Y") if hasattr(x, "strftime") else str(x)
                        )
                else:
                    selected_dates = []
                    st.warning("No dates found in data")
            
            # --- BRAND, VENDOR, STATUS FILTERS (Cascading from Date) ---
            with col2:
                # First, apply date filter to get the base dataset for other filters
                if selected_dates:
                    date_filtered_df = processed_df[processed_df["Created Date"].isin(selected_dates)]
                else:
                    date_filtered_df = processed_df
                
                # Status filter (cascaded from date)
                st.subheader("📊 Status")
                available_statuses = sorted(date_filtered_df["Status"].dropna().unique())
                
                if available_statuses:
                    # Use session state to ensure Active is default on first load
                    status_key = "status_filter_selection"
                    if status_key not in st.session_state:
                        st.session_state[status_key] = ["Active"] if "Active" in available_statuses else []
                    
                    # If current selection has items not in available options, reset
                    current_selection = st.session_state.get(status_key, [])
                    valid_selection = [s for s in current_selection if s in available_statuses]
                    if not valid_selection and "Active" in available_statuses:
                        valid_selection = ["Active"]
                    
                    selected_statuses = st.multiselect(
                        "Filter by status:",
                        options=available_statuses,
                        default=valid_selection,
                        key=status_key,
                        help="Defaults to 'Active' packages"
                    )
                    if not selected_statuses:
                        selected_statuses = list(available_statuses)  # If cleared, show all
                else:
                    selected_statuses = []
                
                # Apply status filter
                status_filtered_df = date_filtered_df[date_filtered_df["Status"].isin(selected_statuses)] if selected_statuses else date_filtered_df
                
                # Brand filter (cascaded from date + status)
                st.subheader("🏷️ Brand")
                available_brands = sorted(status_filtered_df["Brand"].dropna().unique())
                
                if available_brands:
                    selected_brands = st.multiselect(
                        "Filter by brand:",
                        options=available_brands,
                        default=[],  # Empty = all brands
                        placeholder="All brands (click to filter)"
                    )
                    if not selected_brands:
                        selected_brands = list(available_brands)
                else:
                    selected_brands = []
                    st.warning("No brands found")
                
                # Apply brand filter to get available vendors
                brand_filtered_df = status_filtered_df[status_filtered_df["Brand"].isin(selected_brands)] if selected_brands else status_filtered_df
                
                # Vendor filter (cascaded from date + status + brand)
                st.subheader("🏢 Vendor")
                available_vendors = sorted(brand_filtered_df["Vendor"].dropna().unique())
                
                if available_vendors:
                    selected_vendors = st.multiselect(
                        "Filter by vendor:",
                        options=available_vendors,
                        default=[],  # Empty = all vendors
                        placeholder="All vendors (click to filter)"
                    )
                    if not selected_vendors:
                        selected_vendors = list(available_vendors)
                else:
                    selected_vendors = []
                    st.info("No vendor data")
            
            # --- APPLY FILTERS ---
            filtered_df = processed_df.copy()
            
            if selected_dates:
                filtered_df = filtered_df[filtered_df["Created Date"].isin(selected_dates)]
            
            if selected_brands:
                filtered_df = filtered_df[filtered_df["Brand"].isin(selected_brands)]
            
            if selected_vendors:
                filtered_df = filtered_df[filtered_df["Vendor"].isin(selected_vendors)]
            
            if selected_statuses:
                filtered_df = filtered_df[filtered_df["Status"].isin(selected_statuses)]
            
            st.markdown("---")
            
            # --- FILTERED DATA DISPLAY ---
            st.subheader(f"📦 Filtered Packages ({len(filtered_df):,} records)")
            
            if not filtered_df.empty:
                # Add Label Override column (None means follow Label Mode)
                filtered_df = filtered_df.copy()
                filtered_df.insert(0, "Label Override", None)
                
                display_cols = [
                    "Label Override", "Case Labels Needed", "Brand", "Product (Clean)", 
                    "Package Label", "Quantity", "Units Per Case",
                    "Batch No", "Category", "Status", "Vendor", "Created Date"
                ]
                display_cols = [c for c in display_cols if c in filtered_df.columns]
                
                # Configure column for editing
                column_config = {
                    "Label Override": st.column_config.NumberColumn(
                        "🏷️ Override",
                        help="Enter custom label count (leave empty to use Label Mode)",
                        min_value=0,
                        max_value=100,
                        step=1,
                        default=None,
                        width="small"
                    ),
                    "Case Labels Needed": st.column_config.NumberColumn(
                        "Case Qty",
                        help="Labels needed based on Units Per Case",
                        width="small"
                    )
                }
                
                st.caption("💡 **Tip:** Enter a number in 'Override' to print that many labels for a specific product")
                
                edited_df = st.data_editor(
                    filtered_df[display_cols],
                    column_config=column_config,
                    use_container_width=True,
                    height=400,
                    num_rows="fixed",
                    hide_index=True,
                    disabled=[c for c in display_cols if c != "Label Override"]
                )
                
                # Update filtered_df with edited values
                filtered_df["Label Override"] = edited_df["Label Override"].values
                
                # --- LABEL GENERATION OPTIONS ---
                st.markdown("---")
                st.header("🖨️ Label Generation")
                
                gen_col1, gen_col2, gen_col3 = st.columns([2, 2, 4])
                
                with gen_col1:
                    label_mode = st.selectbox(
                        "Label Mode",
                        ["1 Label per Package", "1 Label per Case"],
                        help="Package: 1 label per package. Case: Multiple labels based on package qty ÷ units per case."
                    )
                    label_mode_key = "package" if "Package" in label_mode else "case"
                
                with gen_col2:
                    st.markdown("**Label Size:**")
                    st.info(f"4\" x 2\" at {DPI} DPI")
                    
                    # Show week symbol for current selection
                    if not filtered_df.empty:
                        sample_date = filtered_df["Created At (Full)"].iloc[0]
                        sample_week = get_week_number(sample_date)
                        sample_icon = get_week_icon_name(sample_week)
                        st.markdown(f"**Week Symbol:** {sample_icon} (wk {sample_week})")
                
                # Calculate total labels (accounting for overrides)
                override_labels = 0
                override_count = 0
                non_override_df = filtered_df.copy()
                
                # Process overrides
                for idx, row in filtered_df.iterrows():
                    override = row.get("Label Override")
                    if pd.notna(override):
                        override_labels += int(override)
                        override_count += 1
                        non_override_df = non_override_df.drop(idx)
                
                # Calculate non-override labels based on mode
                if label_mode_key == "package":
                    mode_labels = len(non_override_df)
                else:
                    mode_labels = int(non_override_df["Case Labels Needed"].sum()) if not non_override_df.empty else 0
                    no_case_data = non_override_df[non_override_df["Units_Per_Case_Num"] == 0]
                    if len(no_case_data) > 0:
                        st.warning(f"⚠️ {len(no_case_data)} packages missing Units Per Case - no labels for these")
                
                total_labels = override_labels + mode_labels
                
                with gen_col3:
                    if override_count > 0:
                        st.metric("Total Labels to Generate", f"{total_labels:,}", 
                                  delta=f"{override_count} override(s)")
                    else:
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
        # WELCOME SCREEN
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
                - 🗓️ **Weekly Rotating Symbols** - 18 unique icons that rotate weekly
                    to help distinguish batches received at different times
                
                **Label Layout (4" x 2"):**
                - Top: Black bar with Brand (white) and Category
                - Middle: Product name, UID (large, left-of-center), Created date
                - Bottom: Batch number (left), Week symbol (center), Case Qty (right)
                - Right side: QR code with package label
                
                **Week Symbols (18-week cycle):**
                house, sun, tree, car, cloud, envelope, ladder, key, anchor,
                lightbulb, lock, umbrella, flag, trashcan, clock, mug, book, rabbit
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