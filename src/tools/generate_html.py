"""HTML generation tool — agent writes raw HTML/CSS/JS for interactive output."""

from __future__ import annotations

from langchain_core.tools import tool

from src.tools.artifact_store import get_store

HEIGHT_SCRIPT = """
<script>
  // DOMContentLoaded fires earlier than 'load' and works even when
  // the script is appended outside </body> (agent may omit </body>).
  function _reportHeight() {
    const h = document.body.scrollHeight;
    window.parent.postMessage({type: 'streamlit:setFrameHeight', height: h}, '*');
  }
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', _reportHeight);
  } else {
    // DOM already ready (script injected late) — report immediately
    _reportHeight();
  }
</script>
"""


def inject_height_script(html: str) -> str:
    """Auto-inject dynamic height script into agent-generated HTML."""
    if "</body>" in html:
        return html.replace("</body>", HEIGHT_SCRIPT + "</body>")
    return html + HEIGHT_SCRIPT


def make_generate_html_tool(session_id: str = ""):
    """Factory: create the generate_html tool."""

    @tool
    def generate_html(html_code: str) -> str:
        """Render HTML/CSS/JS in the browser as an interactive artifact.

        Use this for: interactive Plotly charts, styled tables, custom dashboards,
        SVG graphics, D3.js visualizations, or any browser-renderable output.

        The HTML runs in a sandboxed iframe — no server-side execution needed.
        You have full access to CDN libraries (Plotly.js, Chart.js, D3.js, etc.).

        Args:
            html_code: Complete HTML document or fragment to render.
        """
        injected = inject_height_script(html_code)

        # Thread-safe per-session store — no st.session_state access from agent thread
        get_store(session_id).add_html(injected)

        return "HTML rendered successfully in browser iframe."

    return generate_html
