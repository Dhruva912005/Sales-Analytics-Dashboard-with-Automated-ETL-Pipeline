import pandas as pd
import io

def generate_excel_template():
    sample = {
        "Order ID": ["ORD001", "ORD002"],
        "Order Date": ["2024-01-10", "2024-01-11"],
        "Customer Name": ["John Doe", "Jane Doe"],
        "Product Name": ["Laptop", "Mouse"],
        "Category": ["Electronics", "Accessories"],
        "Quantity": [1, 2],
        "Unit Price": [50000, 1500],
        "Total Price": [50000, 3000],
        "Country": ["India", "India"],
        "Payment Mode": ["UPI", "Card"]
    }

    df = pd.DataFrame(sample)
    output = io.BytesIO()
    df.to_excel(output, index=False)
    output.seek(0)
    return output
