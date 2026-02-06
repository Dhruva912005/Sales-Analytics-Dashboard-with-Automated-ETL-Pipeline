# analytics/explore_engine.py

import plotly.express as px

def get_explore_graphs(df):
    graphs = []

    numeric_cols = df.select_dtypes(include='number').columns
    cat_cols = df.select_dtypes(include='object').columns

    for cat in cat_cols:
        for num in numeric_cols:
            try:
                grp = df.groupby(cat)[num].sum().reset_index()
                fig = px.bar(grp, x=cat, y=num,
                             title=f"{num} by {cat}")
                graphs.append(fig)
            except:
                continue

    return graphs
