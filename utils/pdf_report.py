from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import inch
from datetime import datetime
import tempfile


def generate_pdf_report(df):
    temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
    temp_path = temp_file.name
    temp_file.close() 
    
    doc = SimpleDocTemplate(
        temp_path, 
        pagesize=A4,
        rightMargin=50, leftMargin=50,
        topMargin=50, bottomMargin=50
    )

    styles = getSampleStyleSheet()
    
    # Custom Styles
    title_style = ParagraphStyle(
        'MainTitle',
        parent=styles['Title'],
        fontSize=24,
        textColor=colors.HexColor("#4f46e5"),
        spaceAfter=30,
        fontName='Helvetica-Bold'
    )
    
    section_style = ParagraphStyle(
        'SectionHeader',
        parent=styles['Heading2'],
        fontSize=16,
        textColor=colors.HexColor("#1e293b"),
        spaceBefore=20,
        spaceAfter=15,
        borderPadding=(5, 5, 5, 5),
        fontName='Helvetica-Bold'
    )
    
    kpi_style = ParagraphStyle(
        'KPIStyle',
        parent=styles['Normal'],
        fontSize=12,
        leading=18,
        textColor=colors.HexColor("#475569")
    )

    elements = []

    # ---------- HEADER ----------
    elements.append(Paragraph("Automatic Dashboard", title_style))
    elements.append(Paragraph(f"Commercial Intelligence Report • {datetime.now().strftime('%B %d, %Y')}", styles['Normal']))
    elements.append(Spacer(1, 0.5 * inch))

    # ---------- KPI SUMMARY SECTION ----------
    total_revenue = df['total_price'].sum()
    total_orders = df['order_id'].nunique()
    total_customers = df['customer_name'].nunique()
    avg_order = total_revenue / total_orders if total_orders else 0
    
    kpi_data = [
        [
            Paragraph(f"<b>Total Revenue</b><br/>₹{total_revenue:,.2f}", kpi_style),
            Paragraph(f"<b>Total Orders</b><br/>{total_orders}", kpi_style),
            Paragraph(f"<b>Avg. Order Value</b><br/>₹{avg_order:,.2f}", kpi_style)
        ]
    ]
    
    kpi_table = Table(kpi_data, colWidths=[2 * inch, 2 * inch, 2 * inch])
    kpi_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor("#f8fafc")),
        ('BOX', (0, 0), (-1, -1), 1, colors.HexColor("#e2e8f0")),
        ('INNERGRID', (0, 0), (-1, -1), 1, colors.HexColor("#e2e8f0")),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 15),
        ('TOPPADDING', (0, 0), (-1, -1), 15),
    ]))
    
    elements.append(Paragraph("Executive Performance Summary", section_style))
    elements.append(kpi_table)
    elements.append(Spacer(1, 0.4 * inch))

    # ---------- DATA VISUALIZATION TABLES ----------
    
    # 1. Top Products
    top_products = (
        df.groupby(['product_name', 'category'])['total_price']
        .sum()
        .sort_values(ascending=False)
        .head(10)
        .reset_index()
    )
    top_products.columns = ['Product Name', 'Category', 'Revenue (₹)']
    
    elements.append(Paragraph("Top 10 Commercial Items by Revenue", section_style))
    
    table_data = [top_products.columns.tolist()]
    for _, row in top_products.iterrows():
        table_data.append([row[0], row[1], f"₹{row[2]:,.2f}"])
        
    p_table = Table(table_data, colWidths=[2.5 * inch, 1.5 * inch, 1.5 * inch])
    p_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#4f46e5")),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('ALIGN', (2, 0), (2, -1), 'RIGHT'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 11),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 10),
        ('TOPPADDING', (0, 0), (-1, 0), 10),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor("#f1f5f9")]),
    ]))
    elements.append(p_table)
    
    # 2. Category Share
    elements.append(Spacer(1, 0.4 * inch))
    categories = (
        df.groupby('category')['total_price']
        .sum()
        .sort_values(ascending=False)
        .reset_index()
    )
    categories.columns = ['Category Sector', 'Contribution (₹)']
    
    elements.append(Paragraph("Category Revenue Contribution", section_style))
    
    cat_data = [categories.columns.tolist()]
    for _, row in categories.iterrows():
        cat_data.append([row[0], f"₹{row[1]:,.2f}"])
        
    c_table = Table(cat_data, colWidths=[3 * inch, 2.5 * inch])
    c_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#6366f1")),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (0, -1), 'LEFT'),
        ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor("#f1f5f9")]),
    ]))
    elements.append(c_table)

    # ---------- INSIGHTS SECTION ----------
    elements.append(PageBreak())
    elements.append(Paragraph("Strategic Analytical Insights", section_style))
    
    top_product = top_products.iloc[0]['Product Name']
    top_category = categories.iloc[0]['Category Sector']
    
    insight_text = f"""
    The commercial analysis identifies <b>{top_product}</b> as the primary value driver within the <b>{top_category}</b> sector. 
    With an average transaction value of ₹{avg_order:,.2f}, the current market trajectory remains favorable. 
    Optimization of inventory for high-velocity items in the {top_category} category is recommended to capture additional market share.
    """
    
    elements.append(Paragraph(insight_text, kpi_style))
    
    # ---------- FOOTER (Simplistic) ----------
    elements.append(Spacer(1, 2 * inch))
    footer_text = "CONFIDENTIAL BUSINESS INTELLIGENCE REPORT • Generated by Automatic Dashboard System"
    elements.append(Paragraph(f"<font color='#94a3b8' size='8'>{footer_text}</font>", styles['Normal']))

    doc.build(elements)
    return temp_path
