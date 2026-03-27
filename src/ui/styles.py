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

/* ── Status badges ── */
.status-running {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    color: #2563eb;
    font-size: 0.8rem;
}

.status-complete {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    color: #16a34a;
    font-size: 0.8rem;
}

.status-error {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    color: #dc2626;
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

section[data-testid="stSidebar"] .stButton > button {
    width: 100%;
    border-radius: 8px;
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
