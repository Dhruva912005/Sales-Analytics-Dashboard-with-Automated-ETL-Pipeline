import pandas as pd

def get_chart_data(df):
    chart_data = {
        "revenue_category": {},
        "revenue_brand": {},
        "top_products_units": {},
        "country_revenue": {},
        "monthly_sales": {}
    }

    # Revenue by Category
    if {'category', 'total_price'}.issubset(df.columns):
        grp = df.groupby('category')['total_price'].sum()
        chart_data["revenue_category"] = grp.to_dict()

    # Revenue by Brand
    if {'brand', 'total_price'}.issubset(df.columns):
        grp = df.groupby('brand')['total_price'].sum()
        chart_data["revenue_brand"] = grp.to_dict()

    # Top Products by Units
    if {'product_name', 'quantity'}.issubset(df.columns):
        grp = df.groupby('product_name')['quantity'].sum().nlargest(10)
        chart_data["top_products_units"] = grp.to_dict()

    # Country Revenue Share
    if {'country', 'total_price'}.issubset(df.columns):
        grp = df.groupby('country')['total_price'].sum()
        chart_data["country_revenue"] = grp.to_dict()

    # Monthly Sales Trend
    if {'order_date', 'total_price'}.issubset(df.columns):
        df['order_date'] = pd.to_datetime(df['order_date'], errors='coerce')
        grp = df.dropna(subset=['order_date']) \
                .groupby(df['order_date'].dt.strftime('%b'))['total_price'].sum()

        # ensure Jan→Dec order
        months = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]
        chart_data["monthly_sales"] = {m: grp.get(m, 0) for m in months}

    return chart_data
