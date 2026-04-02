"""Generate small deterministic xlsx fixtures for eval scenarios."""

import os
import pandas as pd
import numpy as np

FIXTURES_DIR = os.path.dirname(__file__)


def generate_sales_fixture():
    """50-row sales dataset with known metrics for validation."""
    np.random.seed(42)
    n = 50
    products = ["Widget A", "Widget B", "Gadget X", "Gadget Y", "Tool Z"]
    categories = ["Electronics", "Electronics", "Home", "Home", "Industrial"]
    prod_cat = dict(zip(products, categories))

    df = pd.DataFrame({
        "InvoiceNo": [f"INV-{1000 + i}" for i in range(n)],
        "Date": pd.date_range("2024-01-01", periods=n, freq="D"),
        "Customer ID": np.random.choice([f"C{i:03d}" for i in range(1, 21)], n),
        "Product": np.random.choice(products, n),
        "Quantity": np.random.randint(1, 20, n),
        "Unit Price": np.random.choice([9.99, 19.99, 49.99, 99.99, 149.99], n),
    })
    df["Category"] = df["Product"].map(prod_cat)
    df["Revenue"] = df["Quantity"] * df["Unit Price"]

    path = os.path.join(FIXTURES_DIR, "sales_50.xlsx")
    df.to_excel(path, index=False, sheet_name="Sales")

    # Compute expected metrics for evaluators
    expected = {
        "total_rows": len(df),
        "total_revenue": float(df["Revenue"].sum()),
        "unique_customers": int(df["Customer ID"].nunique()),
        "unique_products": int(df["Product"].nunique()),
        "top_product_by_revenue": df.groupby("Product")["Revenue"].sum().idxmax(),
        "date_range": f"2024-01-01 to 2024-02-19",
    }
    print(f"✅ {path} ({len(df)} rows)")
    print(f"   Expected metrics: {expected}")
    return path, expected


def generate_multisheet_fixture():
    """2-sheet xlsx: Orders + Customers for join test."""
    np.random.seed(123)

    customers = pd.DataFrame({
        "Customer ID": [f"C{i:03d}" for i in range(1, 11)],
        "Name": [f"Customer {i}" for i in range(1, 11)],
        "City": np.random.choice(["Istanbul", "Ankara", "Izmir", "Bursa"], 10),
        "Segment": np.random.choice(["Premium", "Standard", "Basic"], 10),
    })

    orders = pd.DataFrame({
        "Order ID": [f"ORD-{i}" for i in range(1, 31)],
        "Customer ID": np.random.choice(customers["Customer ID"].tolist(), 30),
        "Amount": np.round(np.random.uniform(50, 500, 30), 2),
        "Date": pd.date_range("2024-03-01", periods=30, freq="2D"),
    })

    path = os.path.join(FIXTURES_DIR, "orders_customers.xlsx")
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        orders.to_excel(writer, sheet_name="Orders", index=False)
        customers.to_excel(writer, sheet_name="Customers", index=False)

    expected = {
        "total_orders": len(orders),
        "total_customers": int(customers["Customer ID"].nunique()),
        "sheet_count": 2,
        "total_amount": float(orders["Amount"].sum()),
    }
    print(f"✅ {path} (2 sheets: {len(orders)} orders, {len(customers)} customers)")
    print(f"   Expected metrics: {expected}")
    return path, expected


if __name__ == "__main__":
    generate_sales_fixture()
    generate_multisheet_fixture()
