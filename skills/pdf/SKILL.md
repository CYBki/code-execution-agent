---
name: pdf
description: "Use when working with .pdf files, PDF documents, extracting tables from PDFs, reading text from documents, OCR on scanned pages, or merging/splitting PDF files"
---

# PDF Processing Expertise

You are an expert at extracting and analyzing data from PDF documents.

## Table Extraction with pdfplumber

```python
import pdfplumber

with pdfplumber.open('/home/sandbox/document.pdf') as pdf:
    print(f"Total pages: {len(pdf.pages)}")

    # Extract tables from first page
    page = pdf.pages[0]
    tables = page.extract_tables()
    print(f"Tables found on page 1: {len(tables)}")

    # Convert first table to DataFrame
    if tables:
        import pandas as pd
        df = pd.DataFrame(tables[0][1:], columns=tables[0][0])
        print(df)
```

### Extract Tables from All Pages

```python
import pdfplumber
import pandas as pd

all_tables = []
with pdfplumber.open('/home/sandbox/document.pdf') as pdf:
    for i, page in enumerate(pdf.pages):
        tables = page.extract_tables()
        for j, table in enumerate(tables):
            if table and len(table) > 1:
                df = pd.DataFrame(table[1:], columns=table[0])
                df['source_page'] = i + 1
                all_tables.append(df)
                print(f"Page {i+1}, Table {j+1}: {len(df)} rows")

if all_tables:
    combined = pd.concat(all_tables, ignore_index=True)
    print(f"\nTotal: {len(combined)} rows from {len(all_tables)} tables")
```

### Table Extraction Settings

```python
# Custom table extraction settings for complex layouts
table_settings = {
    "vertical_strategy": "lines",     # or "text", "explicit"
    "horizontal_strategy": "lines",   # or "text", "explicit"
    "snap_tolerance": 3,
    "join_tolerance": 3,
    "edge_min_length": 3,
    "min_words_vertical": 3,
    "min_words_horizontal": 1,
}

tables = page.extract_tables(table_settings)
```

## Text Extraction

```python
import pdfplumber

with pdfplumber.open('/home/sandbox/document.pdf') as pdf:
    # Extract text from all pages
    full_text = ""
    for page in pdf.pages:
        text = page.extract_text()
        if text:
            full_text += text + "\n\n"

print(full_text[:2000])
```

### Preserve Layout

```python
# Extract with layout preservation
text = page.extract_text(layout=True)
```

### Extract Specific Page Range

```python
# Pages 5-10 only (0-indexed)
for page in pdf.pages[4:10]:
    text = page.extract_text()
    print(f"--- Page {page.page_number} ---")
    print(text[:500])
```

## PDF Metadata

```python
import pdfplumber

with pdfplumber.open('/home/sandbox/document.pdf') as pdf:
    print(f"Pages: {len(pdf.pages)}")
    print(f"Metadata: {pdf.metadata}")

    # Page dimensions
    page = pdf.pages[0]
    print(f"Page size: {page.width} x {page.height}")
```

## Working with Scanned PDFs (OCR)

If pdfplumber returns empty text, the PDF likely contains scanned images:

```python
import pdfplumber

with pdfplumber.open('/home/sandbox/scanned.pdf') as pdf:
    page = pdf.pages[0]
    text = page.extract_text()

    if not text or len(text.strip()) < 10:
        print("PDF appears to be scanned — text extraction returned empty")
        print("Attempting image-based approach...")
        
        # Convert page to image for visual inspection
        im = page.to_image(resolution=150)
        im.save('/home/sandbox/page_preview.png')
        print("Page preview saved to /home/sandbox/page_preview.png")
```

## Multi-Page Processing Pattern

```python
import pdfplumber
import pandas as pd

def process_pdf(path):
    """Extract all data from a PDF — tables and text."""
    with pdfplumber.open(path) as pdf:
        results = {
            'tables': [],
            'text_pages': [],
            'page_count': len(pdf.pages),
        }
        
        for page in pdf.pages:
            # Try tables first
            tables = page.extract_tables()
            for table in tables:
                if table and len(table) > 1:
                    df = pd.DataFrame(table[1:], columns=table[0])
                    results['tables'].append({
                        'page': page.page_number,
                        'data': df,
                    })
            
            # Also extract text
            text = page.extract_text()
            if text:
                results['text_pages'].append({
                    'page': page.page_number,
                    'text': text,
                })
    
    return results

results = process_pdf('/home/sandbox/document.pdf')
print(f"Found {len(results['tables'])} tables across {results['page_count']} pages")
```

## Common Pitfalls

- [ ] **Empty tables**: Some PDFs use images instead of text — pdfplumber can't extract from images
- [ ] **Merged cells**: Table extraction may split merged cells into multiple rows
- [ ] **Header detection**: First row may not always be the header — inspect visually first
- [ ] **Encoding issues**: Some PDFs have non-standard encodings — check for garbled text
- [ ] **Rotated pages**: Use `page.rotation` to check and handle rotated content
- [ ] **Large PDFs**: Process page-by-page to avoid memory issues with 100+ page documents
