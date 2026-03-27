---
name: visualization
description: "Use when user asks for charts, plots, graphs, visualizations, dashboards, histograms, scatter plots, heatmaps, or any visual data representation"
---

# Visualization Expertise

You are an expert at creating clear, informative data visualizations.

## Chart Type Selection Guide

| Data Pattern | Best Chart | Library |
|-------------|-----------|---------|
| Compare categories | Bar chart | matplotlib / Plotly |
| Distribution of values | Histogram | matplotlib / Plotly |
| Trend over time | Line chart | matplotlib / Plotly |
| Relationship between 2 variables | Scatter plot | matplotlib / Plotly |
| Distribution + outliers | Box plot | matplotlib / seaborn |
| Correlation matrix | Heatmap | seaborn / Plotly |
| Proportions / composition | Pie / Donut chart | matplotlib / Plotly |
| Part-to-whole across categories | Stacked bar | matplotlib / Plotly |
| Multi-variable relationships | Pair plot | seaborn |
| Geographic data | Map / Choropleth | Plotly |

## Static Charts (matplotlib / seaborn)

Use `create_visualization` tool. Code MUST save to `/home/daytona/chart.png`.

> **Not:** Aşağıdaki örneklerde `/home/daytona/data.csv` yer tutucu. Gerçek dosya adını `parse_file` çıktısından al.

### Bar Chart

```python
import matplotlib.pyplot as plt
import pandas as pd

# Dosya adını parse_file çıktısından al
df = pd.read_csv('/home/daytona/data.csv')
top10 = df.groupby('category')['revenue'].sum().nlargest(10)

fig, ax = plt.subplots(figsize=(12, 6))
top10.plot(kind='barh', ax=ax, color='#2563eb')
ax.set_xlabel('Total Revenue ($)')
ax.set_title('Top 10 Categories by Revenue', fontweight='bold', fontsize=14)
ax.xaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f'${x:,.0f}'))
plt.tight_layout()
plt.savefig('/home/daytona/chart.png', dpi=150, bbox_inches='tight')
plt.close()
```

### Line Chart (Time Series)

```python
import matplotlib.pyplot as plt
import pandas as pd

df = pd.read_csv('/home/daytona/data.csv', parse_dates=['date'])
monthly = df.set_index('date').resample('M')['revenue'].sum()

fig, ax = plt.subplots(figsize=(12, 6))
monthly.plot(ax=ax, color='#2563eb', linewidth=2, marker='o', markersize=4)
ax.fill_between(monthly.index, monthly.values, alpha=0.1, color='#2563eb')
ax.set_title('Monthly Revenue Trend', fontweight='bold', fontsize=14)
ax.set_ylabel('Revenue ($)')
ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f'${x:,.0f}'))
ax.grid(True, alpha=0.3)
plt.tight_layout()
plt.savefig('/home/daytona/chart.png', dpi=150, bbox_inches='tight')
plt.close()
```

### Histogram

```python
import matplotlib.pyplot as plt
import pandas as pd

df = pd.read_csv('/home/daytona/data.csv')

fig, ax = plt.subplots(figsize=(10, 6))
ax.hist(df['revenue'], bins=30, color='#2563eb', edgecolor='white', alpha=0.8)
ax.axvline(df['revenue'].mean(), color='#dc2626', linestyle='--', label=f"Mean: ${df['revenue'].mean():,.0f}")
ax.axvline(df['revenue'].median(), color='#16a34a', linestyle='--', label=f"Median: ${df['revenue'].median():,.0f}")
ax.set_title('Revenue Distribution', fontweight='bold', fontsize=14)
ax.set_xlabel('Revenue ($)')
ax.set_ylabel('Frequency')
ax.legend()
plt.tight_layout()
plt.savefig('/home/daytona/chart.png', dpi=150, bbox_inches='tight')
plt.close()
```

### Heatmap (Correlation)

```python
import matplotlib.pyplot as plt
import seaborn as sns
import pandas as pd

df = pd.read_csv('/home/daytona/data.csv')
numeric_cols = df.select_dtypes(include='number')
corr = numeric_cols.corr()

fig, ax = plt.subplots(figsize=(10, 8))
sns.heatmap(corr, annot=True, fmt='.2f', cmap='RdBu_r', center=0,
            square=True, linewidths=0.5, ax=ax)
ax.set_title('Correlation Matrix', fontweight='bold', fontsize=14)
plt.tight_layout()
plt.savefig('/home/daytona/chart.png', dpi=150, bbox_inches='tight')
plt.close()
```

### Scatter Plot

```python
import matplotlib.pyplot as plt
import pandas as pd

df = pd.read_csv('/home/daytona/data.csv')

fig, ax = plt.subplots(figsize=(10, 8))
scatter = ax.scatter(df['x'], df['y'], c=df['category'].astype('category').cat.codes,
                     cmap='Set2', alpha=0.7, s=50)
ax.set_xlabel('X Variable')
ax.set_ylabel('Y Variable')
ax.set_title('X vs Y by Category', fontweight='bold', fontsize=14)
plt.colorbar(scatter, ax=ax, label='Category')
plt.tight_layout()
plt.savefig('/home/daytona/chart.png', dpi=150, bbox_inches='tight')
plt.close()
```

## Interactive Charts (HTML — Plotly.js)

Use `generate_html` tool. No file save needed — renders in browser iframe.

### Interactive Bar Chart

```html
<!DOCTYPE html>
<html>
<head>
    <script src="https://cdn.plot.ly/plotly-2.27.0.min.js"></script>
</head>
<body>
    <div id="chart" style="width:100%;height:500px;"></div>
    <script>
        var data = [{
            x: ['Product A', 'Product B', 'Product C', 'Product D'],
            y: [45000, 38000, 32000, 28000],
            type: 'bar',
            marker: { color: '#2563eb' },
            text: ['$45K', '$38K', '$32K', '$28K'],
            textposition: 'outside'
        }];
        var layout = {
            title: { text: 'Revenue by Product', font: { size: 18 } },
            yaxis: { title: 'Revenue ($)', tickformat: '$,.0f' },
            margin: { t: 60, b: 60 }
        };
        Plotly.newPlot('chart', data, layout, {responsive: true});
    </script>
</body>
</html>
```

### Interactive Line Chart with Hover

```html
<!DOCTYPE html>
<html>
<head>
    <script src="https://cdn.plot.ly/plotly-2.27.0.min.js"></script>
</head>
<body>
    <div id="chart" style="width:100%;height:500px;"></div>
    <script>
        var trace1 = {
            x: ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun'],
            y: [12000, 15000, 18000, 14000, 22000, 25000],
            mode: 'lines+markers',
            name: '2024',
            line: { color: '#2563eb', width: 3 }
        };
        var trace2 = {
            x: ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun'],
            y: [10000, 11000, 13000, 12000, 16000, 19000],
            mode: 'lines+markers',
            name: '2023',
            line: { color: '#9ca3af', width: 2, dash: 'dash' }
        };
        var layout = {
            title: 'Monthly Revenue Comparison',
            yaxis: { title: 'Revenue', tickformat: '$,.0f' },
            hovermode: 'x unified'
        };
        Plotly.newPlot('chart', [trace1, trace2], layout, {responsive: true});
    </script>
</body>
</html>
```

## Styling Best Practices

### Color Palettes

- **Sequential** (single metric, low→high): Blues, Greens, Oranges
- **Diverging** (centered metric, neg→pos): RdBu, RdYlGn
- **Categorical** (distinct groups): Set2, Tab10, Pastel

### Font and Layout

```python
# Set consistent style for all charts
import matplotlib.pyplot as plt
plt.rcParams.update({
    'font.family': 'sans-serif',
    'font.size': 11,
    'axes.titlesize': 14,
    'axes.titleweight': 'bold',
    'axes.labelsize': 12,
    'figure.facecolor': 'white',
    'axes.facecolor': 'white',
    'axes.grid': True,
    'grid.alpha': 0.3,
})
```

### Number Formatting

```python
# Currency
ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f'${x:,.0f}'))

# Percentage
ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f'{x:.1%}'))

# Thousands (K)
ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f'{x/1000:.0f}K'))
```

## When to Use Which Tool

| Need | Tool | Why |
|------|------|-----|
| Interactive chart (zoom, hover, filter) | `generate_html` + Plotly.js | Runs in browser, full interactivity |
| Publication-quality static chart | `create_visualization` + matplotlib | High DPI PNG, precise control |
| Quick exploration chart | `create_visualization` + seaborn | Clean defaults, fast |
| Dashboard with multiple panels | `generate_html` + CSS Grid + Plotly | Full layout control |
| Simple inline table | `generate_html` + HTML/CSS | Styled, sortable |
