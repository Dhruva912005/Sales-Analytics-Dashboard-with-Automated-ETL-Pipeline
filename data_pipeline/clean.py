import pandas as pd
import numpy as np
from datetime import datetime
import re

def clean_data(df):
    """Main cleaning function"""
    df = df.copy()
    
    # Clean column names
    df.columns = [col.strip().lower().replace(' ', '_').replace('-', '_') for col in df.columns]
    
    return df

def map_columns(df):
    """Map column names to standard names"""
    column_mapping = {
        # Order details
        'order_id': ['order_id', 'orderid', 'id', 'transaction_id'],
        'order_date': ['order_date', 'date', 'purchase_date', 'transaction_date'],
        'customer_name': ['customer_name', 'customer', 'client_name', 'buyer_name'],
        'customer_email': ['customer_email', 'email', 'email_address'],
        'customer_phone': ['customer_phone', 'phone', 'phone_number', 'mobile'],
        
        # Location
        'city': ['city', 'customer_city'],
        'state': ['state', 'customer_state', 'province'],
        'country': ['country', 'customer_country'],
        'region': ['region', 'area', 'zone'],
        
        # Product details
        'product_id': ['product_id', 'productid', 'sku', 'item_id'],
        'product_name': ['product_name', 'product', 'item_name', 'description'],
        'brand': ['brand', 'manufacturer', 'maker'],
        'category': ['category', 'product_category', 'type'],
        'sub_category': ['sub_category', 'subcategory', 'product_subcategory'],
        
        # Financials
        'quantity': ['quantity', 'qty', 'units', 'number'],
        'unit_price': ['unit_price', 'price', 'cost_per_unit', 'unit_cost'],
        'discount': ['discount', 'discount_amount', 'rebate'],
        'tax': ['tax', 'tax_amount', 'gst', 'vat'],
        'total_price': ['total_price', 'total', 'amount', 'revenue', 'sales_amount'],
        
        # Order info
        'payment_mode': ['payment_mode', 'payment_method', 'payment_type'],
        'payment_status': ['payment_status', 'payment'],
        'order_status': ['order_status', 'status', 'delivery_status'],
        'shipping_mode': ['shipping_mode', 'shipping_method', 'delivery_method'],
        'shipping_cost': ['shipping_cost', 'shipping', 'delivery_charge'],
        
        # Channel
        'sales_channel': ['sales_channel', 'channel', 'source'],
        'platform': ['platform', 'website', 'store'],
        
        # Feedback
        'rating': ['rating', 'review_score', 'score'],
        'feedback': ['feedback', 'review', 'comments'],
        'returned': ['returned', 'return', 'is_returned'],
        'return_reason': ['return_reason', 'reason_for_return']
    }
    
    # Apply mapping
    for standard_name, variants in column_mapping.items():
        for variant in variants:
            if variant in df.columns and standard_name not in df.columns:
                df[standard_name] = df[variant]
                break
    
    return df

def ensure_schema(df):
    """Ensure all required columns exist"""
    required_columns = [
        'order_id', 'order_date', 'customer_name', 'product_name',
        'quantity', 'unit_price', 'total_price', 'country'
    ]
    
    for col in required_columns:
        if col not in df.columns:
            df[col] = None
    
    return df

def fix_types(df):
    """Fix data types"""
    # Date columns
    date_columns = ['order_date']
    for col in date_columns:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors='coerce')
    
    # Numeric columns
    numeric_columns = ['quantity', 'unit_price', 'discount', 'tax', 
                      'total_price', 'shipping_cost', 'rating']
    for col in numeric_columns:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce')
    
    # String columns
    string_columns = ['customer_name', 'product_name', 'category', 
                     'country', 'payment_mode', 'order_status']
    for col in string_columns:
        if col in df.columns:
            df[col] = df[col].astype(str).str.strip()
    
    return df

def column_wise_cleaning(df):
    """Column-specific cleaning"""
    if 'customer_name' in df.columns:
        df['customer_name'] = df['customer_name'].str.title()
    
    if 'product_name' in df.columns:
        df['product_name'] = df['product_name'].str.title()
    
    if 'category' in df.columns:
        df['category'] = df['category'].str.title()
    
    if 'country' in df.columns:
        df['country'] = df['country'].str.title()
    
    # Clean email
    if 'customer_email' in df.columns:
        df['customer_email'] = df['customer_email'].str.lower().str.strip()
    
    # Clean phone numbers
    if 'customer_phone' in df.columns:
        df['customer_phone'] = df['customer_phone'].astype(str).str.replace(r'\D', '', regex=True)
    
    return df

def advanced_cleaning(df):
    """Advanced data cleaning"""
    # Remove duplicate orders
    if 'order_id' in df.columns:
        df = df.drop_duplicates(subset=['order_id'], keep='first')
    
    # Remove rows with negative prices
    price_columns = ['unit_price', 'total_price']
    for col in price_columns:
        if col in df.columns:
            df = df[df[col] >= 0]
    
    # Remove rows with negative quantity
    if 'quantity' in df.columns:
        df = df[df['quantity'] > 0]
    
    return df

def fill_missing_values(df):
    """Fill missing values"""
    # Fill categorical columns with 'Unknown'
    categorical_cols = ['category', 'country', 'payment_mode', 'order_status']
    for col in categorical_cols:
        if col in df.columns:
            df[col] = df[col].fillna('Unknown')
    
    # Fill numeric columns with 0
    numeric_cols = ['quantity', 'unit_price', 'discount', 'tax', 
                   'total_price', 'shipping_cost']
    for col in numeric_cols:
        if col in df.columns:
            df[col] = df[col].fillna(0)
    
    # Fill customer name with placeholder
    if 'customer_name' in df.columns:
        df['customer_name'] = df['customer_name'].fillna('Unknown Customer')
    
    # Fill product name
    if 'product_name' in df.columns:
        df['product_name'] = df['product_name'].fillna('Unknown Product')
    
    return df

def create_order_id(df):
    """Create order ID if missing"""
    if 'order_id' not in df.columns or df['order_id'].isna().all():
        df['order_id'] = ['ORD_' + str(i+1).zfill(6) for i in range(len(df))]
    
    return df

def validate_contact_fields(df):
    """Validate contact information"""
    # Email validation regex
    email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    
    if 'customer_email' in df.columns:
        # Mark invalid emails
        df['email_valid'] = df['customer_email'].str.match(email_pattern, na=False)
    
    # Phone validation (basic)
    if 'customer_phone' in df.columns:
        df['customer_phone'] = df['customer_phone'].astype(str)
        # Keep only digits and ensure minimum length
        df['customer_phone'] = df['customer_phone'].str.extract(r'(\d+)')[0]
        df['phone_valid'] = df['customer_phone'].str.len() >= 10
    
    return df