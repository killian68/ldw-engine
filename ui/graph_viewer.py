import os
import sys
import subprocess
import webview

def main():
    # args: <python_exe> <auttho_tool.py> <xml_path> <out_dir>
    if len(sys.argv) < 5:
        print("Usage: graph_viewer.py <python_exe> <auttho_tool.py> <xml_path> <out_dir>")
        return 2

    py = sys.argv[1]
    tool = sys.argv[2]
    xml = sys.argv[3]
    out_dir = sys.argv[4]

    dot_path = os.path.join(out_dir, "graph.dot")
    svg_path = os.path.join(out_dir, "graph.svg")
    html_path = os.path.join(out_dir, "viewer.html")

    class Api:
        def refresh(self):
            # calls: python auttho_tool.py --export-graph --xml ... --dot ... --svg ...
            try:
                subprocess.run(
                    [py, tool, "--export-graph", "--xml", xml, "--dot", dot_path, "--svg", svg_path],
                    check=True
                )
                return True
            except Exception as e:
                return str(e)

    api = Api()

    w = webview.create_window(
        "LDW Graph Viewer",
        url=html_path,
        js_api=api,
        width=1200,
        height=800
    )
    webview.start(debug=False)
    return 0

if __name__ == "__main__":
    raise SystemExit(main())