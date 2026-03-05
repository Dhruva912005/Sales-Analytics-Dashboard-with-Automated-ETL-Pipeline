from flask import Flask, render_template, request, redirect, url_for, send_file, jsonify, session, flash
import pandas as pd
import sqlite3
from datetime import datetime, timedelta
import io
import json
import numpy as np

from utils.pdf_report import generate_pdf_report

import os
from functools import wraps
from contextlib import contextmanager
import logging
from logging.handlers import RotatingFileHandler
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', 'dev-secret-key-change-in-production')  # Use environment variable
DB = os.getenv('DATABASE_PATH', 'sales.db')

# -------------------- LOGGING SETUP --------------------
def setup_logging():
    """
    Configure logging safely for Windows + Flask debug mode.

    Flask debug mode starts two processes:
      - The reloader (watcher) process
      - The actual worker process (WERKZEUG_RUN_MAIN='true')

    Both processes would otherwise open the same log file, causing
    PermissionError on Windows during log rotation (file rename).
    We restrict file handler setup to the worker process only.
    """
    # Avoid attaching duplicate handlers on hot-reload
    if app.logger.hasHandlers():
        return

    formatter = logging.Formatter(
        '%(asctime)s %(levelname)s [%(process)d]: %(message)s '
        '[in %(pathname)s:%(lineno)d]'
    )

    # Always attach a StreamHandler so we see logs in the console
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    console_handler.setLevel(logging.DEBUG if app.debug else logging.INFO)
    app.logger.addHandler(console_handler)

    # Only add the RotatingFileHandler in the worker process.
    # In debug mode, WERKZEUG_RUN_MAIN is set to 'true' only in the
    # child (worker) process. In production (non-debug), there is only
    # one process so we always add the file handler.
    is_worker_process = os.environ.get('WERKZEUG_RUN_MAIN') == 'true'
    if not app.debug or is_worker_process:
        os.makedirs('logs', exist_ok=True)
        file_handler = RotatingFileHandler(
            'logs/analytics_app.log',
            maxBytes=1_000_000,   # 1 MB
            backupCount=5,
            delay=True            # Don't open the file until first write
        )
        file_handler.setFormatter(formatter)
        file_handler.setLevel(logging.INFO)
        app.logger.addHandler(file_handler)

    app.logger.setLevel(logging.DEBUG if app.debug else logging.INFO)
    app.logger.info('Analytics application startup (pid=%d)', os.getpid())

# -------------------- DATABASE CONTEXT MANAGER --------------------
@contextmanager
def get_db_connection():
    """Context manager for database connections"""
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()

# -------------------- HELPER FUNCTIONS --------------------
def convert_to_python_types(obj):
    """Convert NumPy and pandas types to Python native types for JSON serialization"""
    if isinstance(obj, (np.integer, np.int32, np.int64)):
        return int(obj)
    elif isinstance(obj, (np.floating, np.float32, np.float64)):
        return float(obj)
    elif isinstance(obj, np.ndarray):
        return obj.tolist()
    elif isinstance(obj, (pd.Timestamp, datetime)):
        return obj.isoformat()
    elif isinstance(obj, pd.Period):
        return str(obj)
    elif isinstance(obj, (pd.Timedelta, timedelta)):
        return str(obj)
    elif isinstance(obj, pd.Series):
        return obj.tolist()
    elif isinstance(obj, pd.DataFrame):
        return obj.to_dict(orient='records')
    elif isinstance(obj, dict):
        return {key: convert_to_python_types(value) for key, value in obj.items()}
    elif isinstance(obj, list):
        return [convert_to_python_types(item) for item in obj]
    elif np.isscalar(obj) and pd.isna(obj):
        return None
    else:
        return obj

def get_filtered_df(conn):
    """Utility to get filtered dataframe from current request arguments"""
    df = pd.read_sql("SELECT * FROM sales", conn)
    if df.empty:
        return df

    # Date conversion
    df['order_date'] = pd.to_datetime(df['order_date'], errors='coerce')
    df = df.dropna(subset=['order_date'])

    # Get filters
    date_range = request.args.get('date_range', 'all_time')
    category = request.args.get('category', 'all')
    country = request.args.get('country', 'all')
    brand = request.args.get('brand', 'all')

    # Apply categorical filters first
    if category != 'all':
        df = df[df['category'] == category]
    if country != 'all':
        df = df[df['country'] == country]
    if brand != 'all':
        df = df[df['product_name'] == brand]

    if df.empty:
        return df

    # Time Filter relative to LATEST date in dataset (standard BI practice)
    # This prevents blank dashboards if data is old.
    latest_date = df['order_date'].max()
    
    if date_range == 'last_7_days':
        df = df[df['order_date'] >= (latest_date - timedelta(days=7))]
    elif date_range == 'last_30_days':
        df = df[df['order_date'] >= (latest_date - timedelta(days=30))]
    elif date_range == 'this_month':
        df = df[(df['order_date'].dt.month == latest_date.month) & (df['order_date'].dt.year == latest_date.year)]
    elif date_range == 'last_month':
        last_m = (latest_date.replace(day=1) - timedelta(days=1))
        df = df[(df['order_date'].dt.month == last_m.month) & (df['order_date'].dt.year == last_m.year)]
    elif date_range == 'this_year':
        df = df[df['order_date'].dt.year == latest_date.year]
    
    return df
# -------------------- LOGIN REQUIRED DECORATOR --------------------
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function


def validate_upload_file(file):
    """Validate uploaded file"""
    ALLOWED_EXTENSIONS = {'csv', 'xlsx', 'xls'}
    
    if '.' not in file.filename:
        return False, "No file extension"
    
    ext = file.filename.rsplit('.', 1)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        return False, f"File type not allowed. Allowed: {', '.join(ALLOWED_EXTENSIONS)}"
    
    # Check file size (max 10MB)
    file.seek(0, 2)
    size = file.tell()
    file.seek(0)
    
    if size > 10 * 1024 * 1024:  # 10MB
        return False, "File size too large (max 10MB)"
    
    return True, "Valid"

def validate_date_range(f):
    """Decorator to validate date_range parameter"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        date_range = request.args.get('date_range', 'last_30_days')
        valid_ranges = ['last_7_days', 'last_30_days', 'this_month', 
                       'last_month', 'this_year', 'last_year', 'all_time']
        
        if date_range not in valid_ranges:
            return jsonify({
                "status": "error",
                "message": f"Invalid date_range. Must be one of: {', '.join(valid_ranges)}"
            }), 400
        return f(*args, **kwargs)
    return decorated_function

# -------------------- DATABASE --------------------
def init_db():
    with get_db_connection() as conn:
        c = conn.cursor()
        c.execute('''
        CREATE TABLE IF NOT EXISTS sales(
            order_id TEXT,
            order_date TEXT,
            customer_name TEXT,
            product_name TEXT,
            category TEXT,
            quantity REAL,
            unit_price REAL,
            total_price REAL,
            country TEXT,
            payment_mode TEXT
        )
        ''')
        
        c.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        ''')
        
        # Add indexes for better query performance
        c.execute('CREATE INDEX IF NOT EXISTS idx_order_date ON sales(order_date)')
        c.execute('CREATE INDEX IF NOT EXISTS idx_category ON sales(category)')
        c.execute('CREATE INDEX IF NOT EXISTS idx_country ON sales(country)')
        c.execute('CREATE INDEX IF NOT EXISTS idx_customer ON sales(customer_name)')
        c.execute('CREATE INDEX IF NOT EXISTS idx_product ON sales(product_name)')
        
        conn.commit()
    

# -------------------- HEALTH CHECK --------------------
@app.route('/health')
def health_check():
    try:
        # Check database connection
        with get_db_connection() as conn:
            c = conn.cursor()
            c.execute("SELECT 1")
            db_ok = c.fetchone()[0] == 1
        
        return jsonify({
            "status": "healthy",
            "database": "connected" if db_ok else "disconnected",
            "timestamp": datetime.now().isoformat(),
            "version": "1.0.0"
        })
    except Exception as e:
        return jsonify({
            "status": "unhealthy",
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        }), 500

# -------------------- REGISTER --------------------
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        name = request.form.get('name')
        email = request.form.get('email')
        password = request.form.get('password')
        
        if not name or not email or not password:
            flash('All fields are required', 'danger')
            return redirect(url_for('register'))
            
        with get_db_connection() as conn:
            c = conn.cursor()
            
            # Check if user already exists
            c.execute("SELECT id FROM users WHERE email = ?", (email,))
            if c.fetchone():
                flash('Email already registered', 'danger')
                return redirect(url_for('register'))
                
            password_hash = generate_password_hash(password)
            c.execute(
                "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
                (name, email, password_hash)
            )
            conn.commit()
            
        flash('Registration successful! Please login.', 'success')
        return redirect(url_for('login'))
        
    return render_template('register.html')

# -------------------- LOGIN --------------------
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        
        if not email or not password:
            flash('Email and password are required', 'danger')
            return redirect(url_for('login'))

        with get_db_connection() as conn:
            c = conn.cursor()
            c.execute("SELECT id, name, email, password_hash FROM users WHERE email = ?", (email,))
            user = c.fetchone()
            
            if user and check_password_hash(user['password_hash'], password):
                session['user'] = user['email']
                session['user_name'] = user['name']
                session['user_id'] = user['id']
                flash('Login successful!', 'success')
                return redirect(url_for('analytics_dashboard'))
            else:
                flash('Invalid email or password', 'danger')
                return redirect(url_for('login'))

    return render_template('login.html')

# -------------------- LOGOUT --------------------
@app.route('/logout')
def logout():
    session.clear()
    flash('You have been logged out.', 'info')
    return redirect(url_for('login'))

# -------------------- DASHBOARD --------------------
@app.route('/')
def home():
    if 'user' in session:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))

# -------------------- ANALYTICS DASHBOARD --------------------
@app.route('/analytics-dashboard')
@app.route('/dashboard')
@login_required
def dashboard():
    return render_template(
        "analytics_dashboard.html",
        now=datetime.now(),
        full_name="Dhruva Jain"
    )

@app.route('/analytics-dashboard-legacy')
@login_required
def analytics_dashboard():
    return redirect(url_for('dashboard'))

@app.route('/add-customer', methods=['GET', 'POST'])
@login_required
def add_customer():
    if request.method == 'POST':
        try:
            customer_name = request.form.get('customer_name')
            order_date = request.form.get('order_date')
            product_name = request.form.get('product_name')
            category = request.form.get('category')
            quantity = float(request.form.get('quantity', 0))
            unit_price = float(request.form.get('unit_price', 0))
            country = request.form.get('country')
            payment_mode = request.form.get('payment_mode')
            
            total_price = quantity * unit_price
            order_id = f"MANUAL-{datetime.now().strftime('%Y%m%d%H%M')}"

            with get_db_connection() as conn:
                c = conn.cursor()
                c.execute('''
                    INSERT INTO sales (order_id, order_date, customer_name, product_name, category, 
                                      quantity, unit_price, total_price, country, payment_mode)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (order_id, order_date, customer_name, product_name, category, 
                      quantity, unit_price, total_price, country, payment_mode))
                conn.commit()
            
            flash('Sale record added successfully!', 'success')
            return redirect(url_for('dashboard'))
        except Exception as e:
            flash(f'Error adding record: {str(e)}', 'danger')
            
    return render_template("add_customer.html", now=datetime.now())

@app.route('/data-management')
@login_required
def data_management():
    page = int(request.args.get('page', 1))
    per_page = 50
    offset = (page - 1) * per_page
    
    with get_db_connection() as conn:
        total_records = pd.read_sql("SELECT COUNT(*) FROM sales", conn).iloc[0,0]
        df = pd.read_sql(f"SELECT * FROM sales ORDER BY order_date DESC LIMIT {per_page} OFFSET {offset}", conn)
    
    total_pages = (total_records + per_page - 1) // per_page
    
    return render_template(
        "data_management.html", 
        data=df.to_dict(orient='records'), 
        page=page,
        per_page=per_page,
        total_records=total_records,
        total_pages=total_pages,
        now=datetime.now()
    )

@app.route('/profile')
@login_required
def profile():
    with get_db_connection() as conn:
        c = conn.cursor()
        c.execute("SELECT * FROM users WHERE email = ?", (session['user'],))
        user = c.fetchone()
    
    return render_template(
        "profile.html",
        username=user['name'],
        email=user['email'],
        full_name=user['name'],
        role="Administrator",
        created_at=user['created_at'],
        now=datetime.now()
    )

@app.route('/change-password', methods=['GET', 'POST'])
@login_required
def change_password():
    if request.method == 'POST':
        curr_pass = request.form.get('current_password')
        new_pass = request.form.get('new_password')
        conf_pass = request.form.get('confirm_password')
        
        if new_pass != conf_pass:
            flash('Passwords do not match', 'danger')
            return redirect(url_for('change_password'))
            
        with get_db_connection() as conn:
            c = conn.cursor()
            c.execute("SELECT password_hash FROM users WHERE email = ?", (session['user'],))
            user = c.fetchone()
            
            if user and check_password_hash(user['password_hash'], curr_pass):
                new_hash = generate_password_hash(new_pass)
                c.execute("UPDATE users SET password_hash = ? WHERE email = ?", (new_hash, session['user']))
                conn.commit()
                flash('Password updated successfully!', 'success')
                return redirect(url_for('profile'))
            else:
                flash('Incorrect current password', 'danger')
                
    return render_template("change_password.html", now=datetime.now())

@app.route('/clear-data')
@login_required
def clear_data():
    try:
        with get_db_connection() as conn:
            c = conn.cursor()
            c.execute("DELETE FROM sales")
            conn.commit()
        flash('All sales records have been cleared.', 'success')
    except Exception as e:
        flash(f'Error clearing data: {str(e)}', 'danger')
    return redirect(url_for('data_management'))

@app.route('/backup-database')
@login_required
def backup_database():
    try:
        # Simple backup by copying file
        import shutil
        backup_name = f"backups/sales_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
        os.makedirs('backups', exist_ok=True)
        shutil.copy2(DB, backup_name)
        flash(f'Database backup created: {backup_name}', 'success')
    except Exception as e:
        flash(f'Backup failed: {str(e)}', 'danger')
    return redirect(url_for('data_management'))

@app.route('/api/filter-options')
@login_required
def filter_options():
    try:
        with get_db_connection() as conn:
            df = pd.read_sql("SELECT DISTINCT category, country, product_name FROM sales", conn)
        
        return jsonify({
            "categories": sorted(df['category'].dropna().unique().tolist()) if not df.empty else [],
            "countries": sorted(df['country'].dropna().unique().tolist()) if not df.empty else [],
            "brands": sorted(df['product_name'].dropna().unique().tolist()) if not df.empty else []
        })
    except Exception as e:
        app.logger.error(f"Error in filter_options: {str(e)}")
        return jsonify({"categories": [], "countries": [], "brands": []})

@app.route('/api/advanced-chart-data')
@login_required
@validate_date_range
def advanced_chart_data():

    try:
        with get_db_connection() as conn:
            df = get_filtered_df(conn)

        if df.empty:
            return jsonify({
                "status": "success",
                "revenue_metrics": {
                    "total_revenue": 0, "total_orders": 0, "total_customers": 0,
                    "avg_order_value": 0, "avg_basket_size": 0, "total_profit": 0,
                    "avg_profit_margin": 20.0, "growth_rate": 0
                },
                "trends": {"daily": [], "monthly": [], "weekly": [], "hourly": []},
                "category_analysis": [], "geography_analysis": [], "product_analysis": [],
                "payment_methods": [], "clv_table": [], "customer_segments": [],
                "predictive": {"confidence_score": 0, "growth_rate": 0, "forecast_revenue": 0, "summary": "No data"}
            })

        # -------- METRICS --------
        total_revenue = float(df['total_price'].sum())
        total_orders = int(df['order_id'].nunique())
        total_customers = int(df['customer_name'].nunique())
        avg_order_value = float(total_revenue / total_orders if total_orders else 0)
        avg_basket_size = float(df.groupby('order_id')['quantity'].sum().mean())

        # -------- DAILY --------
        daily = df.groupby(df['order_date'].dt.date)['total_price'].sum().reset_index()
        daily.columns = ['date', 'revenue']

        # -------- MONTHLY --------
        monthly = df.groupby(df['order_date'].dt.strftime('%Y-%m'))['total_price'].sum().reset_index()
        monthly.columns = ['month', 'revenue']

        # -------- CATEGORY --------
        cat = df.groupby('category')['total_price'].sum().reset_index()
        cat.columns = ['name', 'revenue']

        # -------- GEOGRAPHY --------
        geo = df.groupby('country').agg(
            revenue=('total_price', 'sum'),
            customers=('customer_name', 'nunique'),
            orders=('order_id', 'nunique')
        ).reset_index()

        geo['aov'] = geo['revenue'] / geo['orders']

        # -------- PRODUCT --------
        prod = df.groupby(['product_name', 'category']).agg(
            total_revenue=('total_price', 'sum'),
            total_quantity=('quantity', 'sum')
        ).reset_index()

        prod = prod.sort_values(by='total_revenue', ascending=False)

        # -------- WEEKLY --------
        weekly = df.groupby(df['order_date'].dt.day_name())['total_price'].sum().reset_index()
        weekly.columns = ['day', 'revenue']

        # -------- PAYMENT --------
        pay = df.groupby('payment_mode')['total_price'].sum().reset_index()
        pay.columns = ['method', 'revenue']

        # -------- CLV --------
        clv = df.groupby('customer_name').agg(
            lifetime_value=('total_price', 'sum'),
            orders=('order_id', 'nunique'),
            first_order=('order_date', 'min'),
            last_order=('order_date', 'max')
        ).reset_index()

        clv['avg_order'] = clv['lifetime_value'] / clv['orders']

        # -------- CUSTOMER SEGMENTS --------
        cust_grouped = df.groupby('customer_name').agg(
            orders=('order_id', 'nunique'),
            spend=('total_price', 'sum')
        )

        customer_segments = [
            {"name": "High Value", "count": int((cust_grouped['spend'] >= 50000).sum())},
            {"name": "VIP", "count": int(((cust_grouped['orders'] >= 5) & (cust_grouped['spend'] < 50000)).sum())},
            {"name": "Regular", "count": int(((cust_grouped['orders'] >= 2) & (cust_grouped['orders'] < 5)).sum())},
            {"name": "New", "count": int((cust_grouped['orders'] == 1).sum())}
        ]

        # -------- HOURLY --------
        hourly = df.groupby(df['order_date'].dt.hour).agg(
            revenue=('total_price', 'sum'),
            orders=('order_id', 'nunique')
        ).reset_index()
        hourly.columns = ['hour', 'revenue', 'orders']
        hourly['revenue'] = hourly['revenue'].astype(float)

        # -------- MONTH-OVER-MONTH GROWTH --------
        monthly_sorted = monthly.sort_values(by='month')
        growth_rate = 0.0
        predicted_revenue = total_revenue * 1.05 # Default if MoM not possible
        
        if len(monthly_sorted) >= 2:
            last_month_rev = monthly_sorted.iloc[-1]['revenue']
            prev_month_rev = monthly_sorted.iloc[-2]['revenue']
            if prev_month_rev > 0:
                growth_rate = ((last_month_rev - prev_month_rev) / prev_month_rev) * 100
            predicted_revenue = last_month_rev * (1 + (growth_rate / 100))
        elif len(monthly_sorted) == 1:
            predicted_revenue = monthly_sorted.iloc[0]['revenue'] * 1.05

        summary_text = f"Revenue is projected to {'grow' if growth_rate >= 0 else 'decrease'} by {abs(growth_rate):.1f}% next month based on MoM trajectory."
        if len(monthly_sorted) < 2:
            summary_text = "Insufficient historical data for MoM trajectory. Projecting a baseline 5% organic growth."

        return jsonify(convert_to_python_types({
            "status": "success",
            "revenue_metrics": {
                "total_revenue": total_revenue,
                "total_orders": total_orders,
                "total_customers": total_customers,
                "avg_order_value": avg_order_value,
                "avg_basket_size": avg_basket_size,
                "total_profit": total_revenue * 0.2,
                "avg_profit_margin": 20.0,
                "growth_rate": round(growth_rate, 1)
            },
            "trends": {
                "daily": daily.to_dict(orient='records'),
                "monthly": monthly.to_dict(orient='records'),
                "weekly": weekly.to_dict(orient='records'),
                "hourly": hourly.to_dict(orient='records')
            },
            "category_analysis": cat.to_dict(orient='records'),
            "geography_analysis": geo.to_dict(orient='records'),
            "product_analysis": prod.to_dict(orient='records'),
            "payment_methods": pay.to_dict(orient='records'),
            "clv_table": clv.to_dict(orient='records'),
            "customer_segments": customer_segments,
            "predictive": {
                "confidence_score": round(min(100.0, max(0.0, 70.0 + growth_rate)), 1),
                "growth_rate": round(growth_rate, 1),
                "forecast_revenue": predicted_revenue,
                "summary": summary_text
            }
        }))

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"status": "error", "message": str(e)}), 500

# -------------------- SEARCH API --------------------
@app.route('/api/search-sales')
def search_sales():
    try:
        search_term = request.args.get('q', '').strip()
        if not search_term:
            return jsonify({"status": "error", "message": "No search term provided"}), 400
        
        with get_db_connection() as conn:
            query = """
            SELECT * FROM sales 
            WHERE order_id LIKE ? 
               OR customer_name LIKE ? 
               OR product_name LIKE ?
            LIMIT 50
            """
            
            search_pattern = f"%{search_term}%"
            df = pd.read_sql(query, conn, params=(search_pattern, search_pattern, search_pattern))
        
        return jsonify({
            "status": "success",
            "count": len(df),
            "results": df.to_dict(orient='records')
        })
    except Exception as e:
        app.logger.error(f"Error in search_sales: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500

# -------------------- EXPORT ANALYTICS REPORT --------------------
@app.route('/export-analytics-report')
@login_required
def export_excel_report():


    try:
        with get_db_connection() as conn:
            df = get_filtered_df(conn)

        if df.empty:
            return "No data available for export with current filters", 400

        # Create Excel file in memory
        output = io.BytesIO()
        
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            # Summary sheet
            summary_data = {
                'Metric': ['Total Revenue', 'Total Orders', 'Total Customers', 
                          'Average Order Value', 'Total Profit', 'Average Profit Margin'],
                'Value': [
                    f"₹{df['total_price'].sum():,.2f}",
                    df['order_id'].nunique(),
                    df['customer_name'].nunique(),
                    f"₹{df['total_price'].sum() / df['order_id'].nunique() if df['order_id'].nunique() > 0 else 0:,.2f}",
                    f"₹{df['total_price'].sum() * 0.2:,.2f}",
                    "20%"
                ]
            }
            summary_df = pd.DataFrame(summary_data)
            summary_df.to_excel(writer, sheet_name='Summary', index=False)
            
            # Sales data sheet
            df.to_excel(writer, sheet_name='Sales Data', index=False)
            
            # Category analysis
            category_df = df.groupby('category')['total_price'].sum().reset_index()
            category_df.columns = ['Category', 'Total Revenue']
            category_df.to_excel(writer, sheet_name='Category Analysis', index=False)
            
            # Geography analysis
            geo_df = df.groupby('country').agg(
                total_revenue=('total_price', 'sum'),
                total_orders=('order_id', 'nunique'),
                total_customers=('customer_name', 'nunique')
            ).reset_index()
            geo_df['avg_order_value'] = geo_df['total_revenue'] / geo_df['total_orders']
            geo_df.to_excel(writer, sheet_name='Geography Analysis', index=False)

        output.seek(0)
        
        return send_file(
            output,
            download_name=f'analytics_report_{datetime.now().strftime("%Y%m%d_%H%M%S")}.xlsx',
            as_attachment=True,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
    except Exception as e:
        app.logger.error(f"Error in export_analytics_report: {str(e)}")
        return f"Error generating report: {str(e)}", 500

# -------------------- EXPORT CSV --------------------
@app.route('/export-csv')
@login_required
def export_csv():

    try:
        with get_db_connection() as conn:
            df = get_filtered_df(conn)

        if df.empty:
            return "No data available for export with current filters", 400

        # Create CSV in memory
        output = io.StringIO()
        df.to_csv(output, index=False)
        
        output.seek(0)
        
        return send_file(
            io.BytesIO(output.getvalue().encode('utf-8')),
            download_name=f'sales_data_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv',
            as_attachment=True,
            mimetype='text/csv'
        )
    except Exception as e:
        app.logger.error(f"Error in export_csv: {str(e)}")
        return f"Error generating CSV: {str(e)}", 500

# -------------------- EXPORT PDF REPORT --------------------
@app.route('/export-pdf-report')
@login_required
def export_pdf_report():
    try:
        with get_db_connection() as conn:
            df = get_filtered_df(conn)

        if df.empty:
            return "No data available for report with current filters", 400

        pdf_path = generate_pdf_report(df)

        return send_file(
            pdf_path,
            as_attachment=True,
            download_name="sales_analytics_report.pdf",
            mimetype='application/pdf'
        )

    except Exception as e:
        app.logger.error(f"Error in export_pdf_report: {str(e)}")
        return f"Error generating PDF: {str(e)}", 500


# -------------------- ADDITIONAL ANALYTICS APIs --------------------
@app.route('/api/customer-analysis')
@login_required
def customer_analysis():
    try:
        with get_db_connection() as conn:
            df = get_filtered_df(conn)
        
        if df.empty:
            return jsonify({
                "status": "success",
                "total_customers": 0,
                "top_customers": [],
                "metrics": {"retention_rate": 0, "loyalty_index": 0, "avg_customer_value": 0, "repeat_customers": 0},
                "segments": [{"name": "High Value", "count": 0}, {"name": "VIP", "count": 0}, {"name": "Regular", "count": 0}, {"name": "New", "count": 0}]
            })

        # Ensure order_date is datetime
        df['order_date'] = pd.to_datetime(df['order_date'], errors='coerce')
        df = df.dropna(subset=['order_date'])

        # Customer aggregation (Monetary, Frequency)
        customer_data = df.groupby('customer_name').agg(
            total_spent=('total_price', 'sum'),
            order_count=('order_id', 'nunique'),
            last_purchase=('order_date', 'max')
        ).reset_index()

        # Recency calculation relative to GLOBAL latest date
        with get_db_connection() as conn:
            global_latest_str = pd.read_sql("SELECT MAX(order_date) FROM sales", conn).iloc[0, 0]
            global_latest = pd.to_datetime(global_latest_str) if global_latest_str else df['order_date'].max()

        customer_data['recency'] = (global_latest - customer_data['last_purchase']).dt.days

        # Retention Calculation
        # A customer is "retained" if they bought in this slice AND either:
        # a) Bought more than once in this slice
        # b) Bought at least once before this slice
        min_slice_date = df['order_date'].min()
        with get_db_connection() as conn:
            prior_cust_df = pd.read_sql("SELECT DISTINCT customer_name FROM sales WHERE order_date < ?", 
                                       conn, params=(min_slice_date.strftime('%Y-%m-%d %H:%M:%S'),))
        prior_customers = set(prior_cust_df['customer_name'].tolist()) if not prior_cust_df.empty else set()

        def is_retained(row):
            return row['order_count'] > 1 or row['customer_name'] in prior_customers

        customer_data['is_retained'] = customer_data.apply(is_retained, axis=1)
        retention_count = int(customer_data['is_retained'].sum())
        total_customers = len(customer_data)
        retention_rate = (retention_count / total_customers * 100) if total_customers > 0 else 0

        # RFM Loyalty Index
        if total_customers > 0:
            # Recency Score (Inverse: shorter recency = higher score)
            r_max, r_min = customer_data['recency'].max(), customer_data['recency'].min()
            if r_max != r_min:
                r_score = (r_max - customer_data['recency']) / (r_max - r_min)
            else:
                r_score = 1.0
            
            # Frequency Score
            f_max, f_min = customer_data['order_count'].max(), customer_data['order_count'].min()
            if f_max != f_min:
                f_score = (customer_data['order_count'] - f_min) / (f_max - f_min)
            else:
                f_score = 1.0
            
            # Monetary Score
            m_max, m_min = customer_data['total_spent'].max(), customer_data['total_spent'].min()
            if m_max != m_min:
                m_score = (customer_data['total_spent'] - m_min) / (m_max - m_min)
            else:
                m_score = 1.0
            
            customer_data['loyalty'] = (r_score * 0.3 + f_score * 0.4 + m_score * 0.3) * 100
            avg_loyalty = float(customer_data['loyalty'].mean())
        else:
            avg_loyalty = 0

        # Segments (Using unified 'name' and realistic thresholds)
        segments = [
            {"name": "High Value", "count": int((customer_data['total_spent'] >= 50000).sum())},
            {"name": "VIP", "count": int(((customer_data['order_count'] >= 5) & (customer_data['total_spent'] < 50000)).sum())},
            {"name": "Regular", "count": int(((customer_data['order_count'] >= 2) & (customer_data['order_count'] < 5)).sum())},
            {"name": "New", "count": int((customer_data['order_count'] == 1).sum())}
        ]

        response_data = {
            "status": "success",
            "total_customers": total_customers,
            "top_customers": customer_data.nlargest(10, 'total_spent').to_dict(orient='records'),
            "metrics": {
                "retention_rate": round(retention_rate, 1),
                "loyalty_index": round(avg_loyalty, 1),
                "avg_customer_value": float(customer_data['total_spent'].mean()),
                "repeat_customers": retention_count
            },
            "segments": segments
        }
        
        return jsonify(convert_to_python_types(response_data))
    except Exception as e:
        import traceback
        app.logger.error(f"Error in customer_analysis: {str(e)}\n{traceback.format_exc()}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/product-analysis')
@login_required
def product_analysis():
    try:
        with get_db_connection() as conn:
            df = get_filtered_df(conn)

        if df.empty:
            return jsonify({
                "status": "success",
                "total_products": 0,
                "top_products": [],
                "category_summary": {},
                "geography": []
            })

        product_data = df.groupby(['product_name', 'category']).agg(
            total_revenue=('total_price', 'sum'),
            total_quantity=('quantity', 'sum'),
            avg_price=('unit_price', 'mean'),
            order_count=('order_id', 'nunique')
        ).reset_index()

        product_data['profit_margin'] = 20  # Assuming 20% margin
        product_data = product_data.sort_values(by='total_revenue', ascending=False)

        # Geography data preparation
        geo_data = df.groupby('country')['total_price'].sum().reset_index()
        geo_data.columns = ['country', 'revenue']
        geo_data = geo_data.sort_values(by='revenue', ascending=False)

        # Convert to Python types
        response_data = {
            "status": "success",
            "total_products": int(product_data.shape[0]),
            "top_products": product_data.nlargest(10, 'total_revenue').to_dict(orient='records'),
            "category_summary": df.groupby('category')['total_price'].sum().to_dict(),
            "geography": geo_data.to_dict(orient='records')
        }
        
        return jsonify(convert_to_python_types(response_data))
    except Exception as e:
        app.logger.error(f"Error in product_analysis: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/predictive-metrics')
@login_required
def predictive_metrics():
    try:
        with get_db_connection() as conn:
            df = get_filtered_df(conn)

        if df.empty:
            return jsonify({
                "status": "success",
                "confidence_score": 0,
                "growth_rate": 0,
                "forecast_revenue": 0,
                "summary": "No data available for trajectory analysis.",
                "recommendations": []
            })

        df['order_date'] = pd.to_datetime(df['order_date'], errors='coerce')
        df = df.dropna(subset=['order_date'])
        
        # Month-over-month growth
        monthly_rev = df.groupby(df['order_date'].dt.strftime('%Y-%m'))['total_price'].sum().sort_index()
        growth_rate = 0.0
        predicted_next = float(monthly_rev.iloc[-1]) if len(monthly_rev) > 0 else 0.0
        
        if len(monthly_rev) >= 2:
            last_month = float(monthly_rev.iloc[-1])
            prev_month = float(monthly_rev.iloc[-2])
            if prev_month > 0:
                growth_rate = ((last_month - prev_month) / prev_month) * 100
            predicted_next = last_month * (1 + growth_rate/100)
        elif len(monthly_rev) == 1:
            predicted_next = float(monthly_rev.iloc[0]) * 1.05

        confidence = min(100.0, max(0.0, 70.0 + growth_rate))

        # Dynamic Recommendations
        top_product = df.groupby('product_name')['total_price'].sum().idxmax() if not df.empty else "N/A"
        top_category = df.groupby('category')['total_price'].sum().idxmax() if not df.empty else "N/A"
        
        recommendations = [
            f"Focus on high-performing products like {top_product}",
            f"Capitalize on the {top_category} segment growth",
            "Implement re-engagement for 'New' customer segment"
        ]

        # Convert to Python types
        response_data = {
            "status": "success",
            "confidence_score": round(confidence, 1),
            "growth_rate": round(growth_rate, 1),
            "forecast_revenue": predicted_next,
            "summary": f"Trajectory indicates a {growth_rate:.1f}% period-over-period revenue shift.",
            "recommendations": recommendations
        }
        
        return jsonify(convert_to_python_types(response_data))
    except Exception as e:
        app.logger.error(f"Error in predictive_metrics: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500

# -------------------- UPLOAD --------------------
@app.route('/upload-analytics', methods=['GET', 'POST'])
@login_required
def upload_analytics():

    if request.method == 'POST':
        file = request.files['file']
        if file.filename == '':
            flash('No file selected')
            return redirect(request.url)
        
        try:
            # Validate file
            is_valid, message = validate_upload_file(file)
            if not is_valid:
                flash(message)
                return redirect(request.url)
            
            # Read file based on extension
            if file.filename.endswith(('.xlsx', '.xls')):
                df = pd.read_excel(file)
            elif file.filename.endswith('.csv'):
                df = pd.read_csv(file)
            
            # Show file columns for debugging
            app.logger.info(f"File columns: {df.columns.tolist()}")
            
            # Column name standardization
            df.columns = df.columns.str.strip().str.lower()
            
            # Handle different column name formats
            column_mapping = {
                'orderid': 'order_id',
                'order id': 'order_id',
                'orderid#': 'order_id',
                'order_no': 'order_id',
                'order no': 'order_id',
                'order#': 'order_id',
                'order': 'order_id',
                
                'orderdate': 'order_date',
                'order date': 'order_date',
                'date': 'order_date',
                'order_date': 'order_date',
                'order_date_time': 'order_date',
                
                'customername': 'customer_name',
                'customer name': 'customer_name',
                'customer': 'customer_name',
                'cust_name': 'customer_name',
                'client_name': 'customer_name',
                
                'productname': 'product_name',
                'product name': 'product_name',
                'product': 'product_name',
                'item': 'product_name',
                'item_name': 'product_name',
                
                'qty': 'quantity',
                'qty.': 'quantity',
                'quantity': 'quantity',
                'units': 'quantity',
                
                'unitprice': 'unit_price',
                'unit price': 'unit_price',
                'price': 'unit_price',
                'rate': 'unit_price',
                
                'totalprice': 'total_price',
                'total price': 'total_price',
                'total': 'total_price',
                'amount': 'total_price',
                'revenue': 'total_price',
                
                'category': 'category',
                'cat': 'category',
                'product_category': 'category',
                'type': 'category',
                
                'country': 'country',
                'location': 'country',
                'region': 'country',
                
                'paymentmode': 'payment_mode',
                'payment mode': 'payment_mode',
                'payment': 'payment_mode',
                'payment_method': 'payment_mode',
                'payment type': 'payment_mode'
            }
            
            # Apply column mapping
            df.columns = [column_mapping.get(col, col) for col in df.columns]
            
            # Now check for required columns
            required_columns = ['order_id', 'order_date', 'customer_name', 'product_name', 
                               'quantity', 'unit_price', 'total_price']
            
            missing_columns = [col for col in required_columns if col not in df.columns]
            
            if missing_columns:
                flash(f'Missing columns: {", ".join(missing_columns)}. Please check your file format.')
                return redirect(request.url)
            
            # Add missing optional columns with default values
            if 'category' not in df.columns:
                df['category'] = 'General'
            if 'country' not in df.columns:
                df['country'] = 'India'
            if 'payment_mode' not in df.columns:
                df['payment_mode'] = 'Unknown'
            
            # Convert date column - handle different date formats
            df['order_date'] = pd.to_datetime(df['order_date'], errors='coerce')
            
            # Fill missing dates with today's date
            df['order_date'] = df['order_date'].fillna(pd.Timestamp.today())
            
            # Calculate total_price if not provided but quantity and unit_price exist
            if 'total_price' not in df.columns and 'quantity' in df.columns and 'unit_price' in df.columns:
                df['total_price'] = df['quantity'] * df['unit_price']
            
            # Ensure numeric columns are numeric
            numeric_columns = ['quantity', 'unit_price', 'total_price']
            for col in numeric_columns:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors='coerce')
                    df[col] = df[col].fillna(0)
            
            # Connect to database and insert data
            with get_db_connection() as conn:
                # Insert data
                df.to_sql("sales", conn, if_exists="append", index=False)
            
            # Show success message with summary
            flash(f'✅ Successfully uploaded {len(df)} records!')
            flash(f'📊 Total Revenue: ₹{df["total_price"].sum():,.2f}')
            flash(f'👥 Unique Customers: {df["customer_name"].nunique()}')
            
            return redirect(url_for('dashboard'))
            
        except Exception as e:
            app.logger.error(f"Error in upload_analytics: {str(e)}")
            flash(f'❌ Error processing file: {str(e)}')
            return redirect(request.url)

    return render_template("upload.html")



# -------------------- DOWNLOAD TEMPLATE --------------------
@app.route('/download-template')
@login_required
def download_template():


    try:
        # Create a comprehensive template with all required columns
        template_data = {
            'order_id': ['ORD001', 'ORD002', 'ORD003', 'ORD004', 'ORD005'],
            'order_date': ['2024-01-01', '2024-01-02', '2024-01-03', '2024-01-04', '2024-01-05'],
            'customer_name': ['John Doe', 'Jane Smith', 'Bob Johnson', 'Alice Brown', 'Charlie Wilson'],
            'product_name': ['Laptop', 'Smartphone', 'Headphones', 'Keyboard', 'Mouse'],
            'category': ['Electronics', 'Electronics', 'Accessories', 'Accessories', 'Accessories'],
            'quantity': [1, 2, 3, 1, 2],
            'unit_price': [50000, 25000, 3000, 1500, 800],
            'total_price': [50000, 50000, 9000, 1500, 1600],
            'country': ['India', 'USA', 'UK', 'Canada', 'Australia'],
            'payment_mode': ['Credit Card', 'UPI', 'Debit Card', 'Net Banking', 'Cash']
        }
        
        df = pd.DataFrame(template_data)
        
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            # Template sheet
            df.to_excel(writer, sheet_name='Template', index=False)
            
            # Instructions sheet
            instructions_data = {
                'Column Name': [
                    'order_id',
                    'order_date', 
                    'customer_name',
                    'product_name',
                    'category',
                    'quantity',
                    'unit_price',
                    'total_price',
                    'country',
                    'payment_mode'
                ],
                'Required': ['Yes', 'Yes', 'Yes', 'Yes', 'No', 'Yes', 'Yes', 'Yes', 'No', 'No'],
                'Description': [
                    'Unique identifier for each order (e.g., ORD001)',
                    'Date of order in YYYY-MM-DD format',
                    'Name of the customer',
                    'Name of the product purchased',
                    'Product category (optional)',
                    'Number of units purchased',
                    'Price per unit',
                    'Total amount (quantity × unit_price)',
                    'Country of customer (optional)',
                    'Payment method used (optional)'
                ],
                'Example': [
                    'ORD001, ORD002, INV-1001',
                    '2024-01-15, 15/01/2024',
                    'John Doe, Jane Smith',
                    'Laptop, Smartphone, Headphones',
                    'Electronics, Clothing, Home',
                    '1, 2, 3.5',
                    '1000, 500.50, 299.99',
                    '1000, 1001, 1049.97',
                    'India, USA, UK',
                    'Credit Card, UPI, Cash'
                ]
            }
            
            instructions_df = pd.DataFrame(instructions_data)
            instructions_df.to_excel(writer, sheet_name='Instructions', index=False)
        
        output.seek(0)
        
        return send_file(
            output,
            download_name='sales_data_template.xlsx',
            as_attachment=True,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
    except Exception as e:
        app.logger.error(f"Error in download_template: {str(e)}")
        return f"Error generating template: {str(e)}", 500

# -------------------- SECURITY HEADERS --------------------
@app.after_request
def add_security_headers(response):
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['X-XSS-Protection'] = '1; mode=block'
    
    # For production, add CSP
    if not app.debug:
        response.headers['Content-Security-Policy'] = "default-src 'self'"
    
    return response

# -------------------- ERROR HANDLERS --------------------
@app.errorhandler(404)
def page_not_found(e):
    return render_template('404.html'), 404

@app.errorhandler(500)
def internal_server_error(e):
    app.logger.error(f"Internal Server Error: {str(e)}")
    return render_template('500.html'), 500

# -------------------- MAIN --------------------
if __name__ == '__main__':
    setup_logging()
    init_db()
    
    # Create backups directory if it doesn't exist
    os.makedirs('backups', exist_ok=True)
    
    app.run(debug=True, host='0.0.0.0', port=5000)