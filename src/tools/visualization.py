"""Static visualization tool — matplotlib/seaborn charts via Daytona sandbox."""

from __future__ import annotations

from langchain_core.tools import tool
from langchain_daytona import DaytonaSandbox

from src.tools.artifact_store import get_store


def make_visualization_tool(backend: DaytonaSandbox, session_id: str = ""):
    """Factory: create the create_visualization tool bound to a Daytona backend."""

    @tool
    def create_visualization(code: str) -> str:
        """Generate a static chart (PNG) by running matplotlib/seaborn code in the sandbox.

        Use this for: matplotlib charts, seaborn plots, pandas plots — any static PNG output.
        For interactive charts (Plotly, D3, Chart.js), use generate_html instead.

        The code MUST save the figure to '/home/daytona/chart.png'. Example:
            import matplotlib.pyplot as plt
            plt.figure(figsize=(10, 6))
            plt.bar(['A', 'B', 'C'], [10, 20, 15])
            plt.title('My Chart')
            plt.savefig('/home/daytona/chart.png', dpi=150, bbox_inches='tight')
            plt.close()
            print('Chart saved')

        Args:
            code: Python code that generates and saves a chart to /home/daytona/chart.png
        """
        # Wrap code to ensure it saves and closes properly
        wrapped_code = code + "\nimport matplotlib; matplotlib.pyplot.close('all')"

        try:
            exec_result = backend.execute(wrapped_code)
            output_text = exec_result.output
        except Exception as e:
            return f"Error executing visualization code: {e}"

        # Download the generated chart
        try:
            responses = backend.download_files(["/home/daytona/chart.png"])
            resp = responses[0] if responses else None
            if resp and resp.content and not resp.error:
                # Thread-safe per-session store — no st.session_state access from agent thread
                get_store(session_id).add_chart(resp.content, code)

                return f"Chart generated successfully. Output: {output_text}"
            else:
                error_info = resp.error if resp else "no response"
                return (
                    f"Code executed but chart.png not found ({error_info}). "
                    f"Make sure code saves to '/home/daytona/chart.png'. Output: {output_text}"
                )
        except Exception as e:
            return f"Code executed but failed to download chart: {e}. Output: {output_text}"

    return create_visualization
