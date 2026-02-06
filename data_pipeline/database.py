import sqlite3
import pandas as pd
from datetime import datetime

DB_NAME = "sales.db"

def get_connection():
    """Get database connection"""
    return sqlite3.connect(DB_NAME)

def create_tables():
    """Create database tables"""
    conn = get_connection()
    cursor = conn.cursor()
    
    # Drop existing tables if they exist
    cursor.execute("DROP TABLE IF EXISTS sales_master")
    
    # Create sales_master table
    cursor.execute('''
    CREATE TABLE sales_master (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        order_id TEXT,
        order_date TEXT,
        customer_name TEXT,
        customer_email TEXT,
        customer_phone TEXT,
        city TEXT,
        state TEXT,
        country TEXT,
        region TEXT,
        product_id TEXT,
        product_name TEXT,
        brand TEXT,
        category TEXT,
        sub_category TEXT,
        quantity INTEGER,
        unit_price REAL,
        discount REAL,
        tax REAL,
        total_price REAL,
        payment_mode TEXT,
        payment_status TEXT,
        order_status TEXT,
        shipping_mode TEXT,
        shipping_cost REAL,
        sales_channel TEXT,
        platform TEXT,
        rating INTEGER,
        feedback TEXT,
        returned INTEGER,
        return_reason TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    ''')
    
    # Create indexes
    cursor.execute('CREATE INDEX idx_order_date ON sales_master(order_date)')
    cursor.execute('CREATE INDEX idx_category ON sales_master(category)')
    cursor.execute('CREATE INDEX idx_country ON sales_master(country)')
    cursor.execute('CREATE INDEX idx_payment_mode ON sales_master(payment_mode)')
    cursor.execute('CREATE INDEX idx_order_status ON sales_master(order_status)')
    
    conn.commit()
    conn.close()
    print("✅ Database tables created")

def create_sales_master_view():
    """Create sales master view"""
    conn = get_connection()
    cursor = conn.cursor()
    
    # Drop existing view
    cursor.execute("DROP VIEW IF EXISTS sales_master_view")
    
    # Create view
    cursor.execute('''
    CREATE VIEW sales_master_view AS
    SELECT 
        id,
        order_id,
        order_date,
        customer_name,
        customer_email,
        customer_phone,
        city,
        state,
        country,
        region,
        product_id,
        product_name,
        brand,
        category,
        sub_category,
        quantity,
        unit_price,
        discount,
        tax,
        total_price,
        payment_mode,
        payment_status,
        order_status,
        shipping_mode,
        shipping_cost,
        sales_channel,
        platform,
        rating,
        feedback,
        returned,
        return_reason,
        created_at
    FROM sales_master
    ''')
    
    conn.commit()
    conn.close()
    print("✅ Sales master view created")

def insert_to_db(customers, invoices, items):
    """Insert data into database (legacy function for compatibility)"""
    # For backward compatibility, we'll insert all data into sales_master
    conn = get_connection()
    
    # Combine all data if provided
    if customers is not None and not customers.empty:
        customers.to_sql('customers_temp', conn, if_exists='replace', index=False)
    
    if invoices is not None and not invoices.empty:
        invoices.to_sql('invoices_temp', conn, if_exists='replace', index=False)
    
    if items is not None and not items.empty:
        items.to_sql('items_temp', conn, if_exists='replace', index=False)
    
    conn.close()
    print("✅ Data inserted into database (compatibility mode)")

def check_database():
    """Check database status"""
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = cursor.fetchall()
    
    print(f"📊 Database has {len(tables)} tables:")
    for table in tables:
        cursor.execute(f"SELECT COUNT(*) FROM {table[0]}")
        count = cursor.fetchone()[0]
        print(f"  - {table[0]}: {count} rows")
    
    conn.close()