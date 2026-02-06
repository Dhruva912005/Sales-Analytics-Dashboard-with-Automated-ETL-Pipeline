import streamlit as st
import pandas as pd
import sqlite3
import plotly.graph_objects as go
from analytics.dashboard_engine import get_dashboard_graphs

st.set_page_config(layout="wide")

DB = "sales.db"


@st.cache_data
def get_df():
    conn = sqlite3.connect(DB)
    df = pd.read_sql("SELECT * FROM sales_master", conn)
    conn.close()
    df['order_date'] = pd.to_datetime(df['order_date'], errors='coerce')
    return df


df = get_df()

st.title("📊 Sales Analytics Dashboard")

# ------------------ FILTERS ------------------
st.sidebar.header("Filters")

categories = st.sidebar.multiselect(
    "Category", df['category'].dropna().unique()
)

countries = st.sidebar.multiselect(
    "Country", df['country'].dropna().unique()
)

payment = st.sidebar.multiselect(
    "Payment Mode", df['payment_mode'].dropna().unique()
)

if categories:
    df = df[df['category'].isin(categories)]

if countries:
    df = df[df['country'].isin(countries)]

if payment:
    df = df[df['payment_mode'].isin(payment)]

# ------------------ KPIs ------------------
col1, col2, col3, col4 = st.columns(4)

col1.metric("Total Revenue", f"₹ {int(df['total_price'].sum()):,}")
col2.metric("Total Quantity", int(df['quantity'].sum()))
col3.metric("Avg Rating", round(df['rating'].mean(), 2))
col4.metric("Total Orders", df['order_id'].nunique())

st.markdown("---")

# ------------------ GRAPHS ------------------
graphs = get_dashboard_graphs()

for g in graphs:
    st.subheader(g["title"])
    st.caption(g["desc"])

    fig = go.Figure()

    if g["type"] == "bar":
        fig.add_bar(x=g["x"], y=g["y"])

    elif g["type"] == "line":
        fig.add_scatter(x=g["x"], y=g["y"], mode='lines+markers')

    elif g["type"] == "pie":
        fig.add_pie(labels=g["labels"], values=g["values"])

    elif g["type"] == "scatter":
        fig.add_scatter(x=g["x"], y=g["y"], mode='markers')

    elif g["type"] == "histogram":
        fig.add_histogram(x=g["x"])

    st.plotly_chart(fig, use_container_width=True)
