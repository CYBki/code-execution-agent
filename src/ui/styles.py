"""Custom CSS for Claude-like appearance — dark code blocks, step timeline, tool cards."""

CUSTOM_CSS = """
<style>
/* ── Global ── */
.stApp {
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
}

/* ── Chat message styling ── */
.stChatMessage {
    padding: 1rem 1.25rem;
}

/* ── Dark code blocks ── */
.stCodeBlock {
    border-radius: 8px;
}

/* ── Tool call card ── */
.tool-card {
    background: #f7f7f8;
    border: 1px solid #e5e5e5;
    border-radius: 12px;
    padding: 0;
    margin: 0.5rem 0;
    overflow: hidden;
}

.tool-card-header {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 10px 14px;
    background: #f0f0f1;
    border-bottom: 1px solid #e5e5e5;
    font-weight: 600;
    font-size: 0.9rem;
    color: #333;
}

.tool-card-body {
    padding: 12px 14px;
    font-size: 0.85rem;
}

.tool-card-output {
    padding: 10px 14px;
    background: #fafafa;
    border-top: 1px solid #e5e5e5;
    font-family: 'SF Mono', 'Fira Code', monospace;
    font-size: 0.8rem;
    white-space: pre-wrap;
    color: #555;
}

.tool-card-error {
    color: #dc2626;
    background: #fef2f2;
}

/* ── Status badges (Modern color palette) ── */
.status-running {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    color: #0ea5e9;  /* sky blue */
    font-size: 0.8rem;
}

.status-complete {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    color: #10b981;  /* emerald */
    font-size: 0.8rem;
}

.status-error {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    color: #ef4444;  /* rose red */
    font-size: 0.8rem;
}

.status-warning {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    color: #f59e0b;  /* amber */
    font-size: 0.8rem;
}

/* ── Thinking / reasoning animation ── */
@keyframes pulse-thinking {
    0%, 100% { opacity: 0.6; }
    50% { opacity: 1; }
}

.thinking-indicator {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 8px 12px;
    color: #6b7280;
    font-size: 0.85rem;
    animation: pulse-thinking 1.5s ease-in-out infinite;
}

.thinking-dot {
    width: 6px;
    height: 6px;
    border-radius: 50%;
    background: #9ca3af;
}

/* ── Spinner rotation animation ── */
@keyframes spin {
    from { transform: rotate(0deg); }
    to { transform: rotate(360deg); }
}

/* ── Execute step animation (Modern pulse-glow) ── */
@keyframes pulse-exec {
    0%, 100% { transform: scale(1); opacity: 0.7; }
    50% { transform: scale(1.3); opacity: 1; }
}

@keyframes pulse-glow {
    0%, 100% {
        box-shadow: 0 0 0 0 rgba(14, 165, 233, 0.4);
        opacity: 0.8;
    }
    50% {
        box-shadow: 0 0 0 6px rgba(14, 165, 233, 0);
        opacity: 1;
    }
}

/* ── Rotate spinner emoji in custom status header ── */
.rotating-spinner {
    display: inline-block;
    animation: spin 1s linear infinite;
    transform-origin: center center;
    font-size: 1.1em;
    margin-right: 8px;
}

/* ── Custom execute status container ── */
.execute-status-container {
    background: #f8fafc;
    border: 1px solid #e2e8f0;
    border-radius: 8px;
    padding: 12px 16px;
    margin: 8px 0;
    transition: all 0.2s ease;
}

.execute-status-container:hover {
    background: #f1f5f9;
    border-color: #cbd5e1;
}

.execute-status-header {
    display: flex;
    align-items: center;
    gap: 8px;
    font-size: 0.95rem;
    font-weight: 500;
    color: #334155;
}

/* Running state styling */
.status-running {
    border-left: 3px solid #0ea5e9;
    background: linear-gradient(90deg, #f0f9ff 0%, #f8fafc 100%);
}

.status-running .execute-status-header {
    color: #0ea5e9;
}

/* Complete state styling */
.status-complete {
    border-left: 3px solid #10b981;
}

.status-complete .execute-status-header {
    color: #059669;
}

/* Error state styling */
.status-error {
    border-left: 3px solid #ef4444;
    background: linear-gradient(90deg, #fef2f2 0%, #f8fafc 100%);
}

.status-error .execute-status-header {
    color: #dc2626;
}

.exec-active-dot {
    width: 8px;
    height: 8px;
    border-radius: 50%;
    background: #0ea5e9;  /* sky blue */
    animation: pulse-glow 1.5s ease-in-out infinite;
    display: inline-block;
}

.execute-step-badge {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    padding: 2px 8px;
    background: #f0f9ff;  /* light sky */
    border: 1px solid #bae6fd;  /* sky 200 */
    border-radius: 12px;
    font-size: 0.75rem;
    color: #0ea5e9;  /* sky blue */
    font-weight: 600;
}

/* ── Step state colors ── */
.step-pending {
    color: #94a3b8;  /* slate gray */
    opacity: 0.6;
}

.step-active {
    color: #0ea5e9;  /* sky blue */
    animation: pulse-glow 1.5s ease-in-out infinite;
}

.step-done {
    color: #64748b;  /* dim gray */
}

.step-error {
    color: #ef4444;  /* rose red */
}

/* ── Container styling ── */
.execute-container {
    background: #f8fafc;  /* very light */
    border: 1px solid #e2e8f0;  /* light gray */
    border-radius: 8px;
}

.execute-container:hover {
    background: #f1f5f9;  /* hover effect */
}

/* ── Step timeline ── */
.step-timeline {
    border-left: 2px solid #e5e5e5;
    margin-left: 8px;
    padding-left: 16px;
}

.step-item {
    position: relative;
    padding: 4px 0;
    font-size: 0.85rem;
    color: #555;
}

.step-item::before {
    content: '';
    position: absolute;
    left: -21px;
    top: 50%;
    transform: translateY(-50%);
    width: 8px;
    height: 8px;
    border-radius: 50%;
    background: #d1d5db;
}

.step-item.active::before {
    background: #2563eb;
    box-shadow: 0 0 0 3px rgba(37, 99, 235, 0.2);
}

.step-item.done::before {
    background: #16a34a;
}

/* ── Inline artifact ── */
.artifact-container {
    border: 1px solid #e5e5e5;
    border-radius: 12px;
    margin: 0.75rem 0;
    overflow: hidden;
}

.artifact-header {
    padding: 8px 14px;
    background: #f7f7f8;
    border-bottom: 1px solid #e5e5e5;
    font-weight: 600;
    font-size: 0.85rem;
    color: #333;
}

/* ── File upload badge ── */
.file-badge {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    padding: 4px 10px;
    background: #eff6ff;
    border: 1px solid #bfdbfe;
    border-radius: 6px;
    font-size: 0.8rem;
    color: #1d4ed8;
    margin: 2px 0;
}

/* ── Sidebar styling ── */
section[data-testid="stSidebar"] {
    background: #fafafa;
}

/* Sidebar text visibility on light background */
section[data-testid="stSidebar"] .stMarkdown p,
section[data-testid="stSidebar"] .stMarkdown h3,
section[data-testid="stSidebar"] .stMarkdown h4,
section[data-testid="stSidebar"] .stMarkdown strong {
    color: #1e293b !important;
}

section[data-testid="stSidebar"] .stMarkdown small,
section[data-testid="stSidebar"] [data-testid="stCaptionContainer"],
section[data-testid="stSidebar"] [data-testid="stCaptionContainer"] p,
section[data-testid="stSidebar"] [data-testid="stCaptionContainer"] small {
    color: #475569 !important;
}

section[data-testid="stSidebar"] label,
section[data-testid="stSidebar"] .stFileUploader label,
section[data-testid="stSidebar"] [data-testid="stFileUploaderDropzone"] span,
section[data-testid="stSidebar"] .uploadedFileName {
    color: #334155 !important;
}

section[data-testid="stSidebar"] hr {
    border-color: #cbd5e1 !important;
}

section[data-testid="stSidebar"] .stButton > button {
    width: 100%;
    border-radius: 8px;
    color: #1e293b !important;
    border-color: #94a3b8 !important;
}

section[data-testid="stSidebar"] .stButton > button:hover {
    background: #e2e8f0 !important;
    border-color: #64748b !important;
}
</style>
"""

TOOL_ICONS = {
    "parse_file": "📄",
    "execute": "🐍",
    "generate_html": "🌐",
    "create_visualization": "📊",
    "download_file": "📥",
    "read_file": "📖",
    "write_file": "✏️",
    "edit_file": "✏️",
    "ls": "📂",
    "glob": "🔍",
    "grep": "🔎",
}

TOOL_LABELS = {
    "parse_file": "Parsing file",
    "execute": "Running code",
    "generate_html": "Generating HTML",
    "create_visualization": "Creating chart",
    "download_file": "Preparing download",
    "read_file": "Reading file",
    "write_file": "Writing file",
    "edit_file": "Editing file",
    "ls": "Listing directory",
    "glob": "Finding files",
    "grep": "Searching files",
}


def get_tool_icon(tool_name: str) -> str:
    """Get emoji icon for a tool."""
    return TOOL_ICONS.get(tool_name, "🔧")


def get_tool_label(tool_name: str) -> str:
    """Get human-readable label for a tool."""
    return TOOL_LABELS.get(tool_name, tool_name)
