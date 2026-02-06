import pandas as pd
import numpy as np
from datetime import datetime
import os
import sys

# Add parent directory to path to import modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from data_pipeline.clean import *
from data_pipeline.database import create_tables, create_sales_master_view, get_connection

def create_relational_tables(df):
    """Split data into relational tables (for compatibility)"""
    # For this simplified version, we return the same dataframe for all
    return df.copy(), df.copy(), df.copy()

def run_pipeline(file):
    """Main pipeline function"""
    print("🚀 Starting Data Pipeline...")
    
    try:
        # Read file based on type
        if hasattr(file, "filename"):  # Flask file object
            filename = file.filename.lower()
            
            if filename.endswith(".csv"):
                df = pd.read_csv(file)
                print(f"📄 Read CSV file: {filename}")
            else:
                df = pd.read_excel(file)
                print(f"📄 Read Excel file: {filename}")
        else:  # Local file path
            if str(file).lower().endswith(".csv"):
                df = pd.read_csv(file)
                print(f"📄 Read CSV file: {file}")
            else:
                df = pd.read_excel(file)
                print(f"📄 Read Excel file: {file}")
        
        print(f"📊 Initial data shape: {df.shape}")
        
        # Clean data
        print("🧹 Cleaning data...")
        df = clean_data(df)
        df = map_columns(df)
        df = ensure_schema(df)
        df = fix_types(df)
        df = column_wise_cleaning(df)
        df = advanced_cleaning(df)
        df = fill_missing_values(df)
        df = create_order_id(df)
        df = validate_contact_fields(df)
        
        print(f"✅ Cleaned data shape: {df.shape}")
        
        # Create relational tables (for compatibility)
        customers, invoices, items = create_relational_tables(df)
        
        # Database operations
        print("💾 Storing data in database...")
        create_tables()
        
        # Insert into database
        conn = get_connection()
        df.to_sql('sales_master', conn, if_exists='append', index=False)
        conn.close()
        
        create_sales_master_view()
        
        print(f"✅ Pipeline completed successfully!")
        print(f"📈 Processed {len(df)} records")
        
        # Show sample of cleaned data
        print("\n📋 Sample of cleaned data:")
        print(df[['order_id', 'order_date', 'customer_name', 'product_name', 'total_price']].head())
        
        return df
        
    except Exception as e:
        print(f"❌ Pipeline error: {e}")
        import traceback
        traceback.print_exc()
        raise

if __name__ == "__main__":
    # Test with sample data
    sample_data = {
        'order_id': ['ORD001', 'ORD002'],
        'order_date': ['2024-01-15', '2024-01-16'],
        'customer_name': ['John Doe', 'Jane Smith'],
        'product_name': ['Laptop', 'Mouse'],
        'quantity': [1, 2],
        'unit_price': [50000, 1500],
        'total_price': [50000, 3000],
        'country': ['India', 'USA'],
        'category': ['Electronics', 'Electronics'],
        'payment_mode': ['Credit Card', 'UPI']
    }
    
    df = pd.DataFrame(sample_data)
    run_pipeline(df)
    print("✅ Test completed successfully!")