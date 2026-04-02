"""Test scenarios for agent evaluation.

Each scenario defines:
  - name: unique identifier
  - fixture: xlsx filename (in fixtures/ dir)
  - queries: list of user queries to send sequentially (multi-turn)
  - evaluators: which evaluators to run (defaults to DEFAULT_EVALUATORS)
  - expected_keywords: keywords expected in final response (for completeness eval)
  - expect_report: whether PDF/HTML artifact is expected
"""

SCENARIOS = [
    # ── Scenario 1: Basic single-question analysis ──────────────────────
    {
        "name": "basic_revenue_analysis",
        "fixture": "sales_50.xlsx",
        "queries": [
            "Bu dosyadaki toplam geliri ve en çok satan ürünü analiz et."
        ],
        "expected_keywords": ["gelir", "ürün"],
        "expect_report": False,
        "evaluators": [
            "no_pickle", "persistent_kernel", "no_shell_exploration",
            "validation_present", "execute_efficiency", "completeness",
        ],
    },

    # ── Scenario 2: Full report with PDF ────────────────────────────────
    {
        "name": "full_pdf_report",
        "fixture": "sales_50.xlsx",
        "queries": [
            "Bu verileri analiz et ve detaylı bir PDF rapor üret."
        ],
        "expected_keywords": ["rapor", "pdf"],
        "expect_report": True,
        "evaluators": [
            "no_pickle", "persistent_kernel", "no_hardcoded_metrics",
            "no_shell_exploration", "report_generated",
            "execute_efficiency", "completeness",
        ],
    },

    # ── Scenario 3: Multi-sheet join ────────────────────────────────────
    {
        "name": "multisheet_join",
        "fixture": "orders_customers.xlsx",
        "queries": [
            "Bu dosyadaki siparişleri müşteri segmentlerine göre analiz et."
        ],
        "expected_keywords": ["segment", "sipariş", "müşteri"],
        "expect_report": False,
        "evaluators": [
            "no_pickle", "persistent_kernel", "no_shell_exploration",
            "validation_present", "execute_efficiency", "completeness",
        ],
    },

    # ── Scenario 4: Multi-turn conversation ─────────────────────────────
    {
        "name": "multi_turn_followup",
        "fixture": "sales_50.xlsx",
        "queries": [
            "Bu dosyadaki verilerin genel özetini çıkar.",
            "Aylık gelir trendini göster."
        ],
        "expected_keywords": ["trend", "aylık"],
        "expect_report": False,
        "evaluators": [
            "no_pickle", "persistent_kernel", "no_shell_exploration",
            "execute_efficiency", "completeness",
        ],
    },

    # ── Scenario 5: Category breakdown ──────────────────────────────────
    {
        "name": "category_breakdown",
        "fixture": "sales_50.xlsx",
        "queries": [
            "Kategori bazında satış dağılımını analiz et ve dashboard oluştur."
        ],
        "expected_keywords": ["kategori", "electronics"],
        "expect_report": True,
        "evaluators": [
            "no_pickle", "persistent_kernel", "no_hardcoded_metrics",
            "no_shell_exploration", "report_generated",
            "execute_efficiency", "completeness",
        ],
    },
]
