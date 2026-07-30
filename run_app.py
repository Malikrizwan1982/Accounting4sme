import os
import sys
import streamlit.web.cli as stcli

# --- REDIRECT STDOUT/STDERR FOR STANDALONE RUNTIME ---
# Prevents Python from crashing silently when run without a command window
if sys.stdout is None:
    sys.stdout = open(os.devnull, "w")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w")

def resolve_path(relative_path):
    """ Get absolute path to resource, works for dev and for PyInstaller """
    if getattr(sys, 'frozen', False):
        # Running inside PyInstaller bundle (_internal)
        base_path = getattr(sys, '_MEIPASS', os.path.dirname(sys.executable))
    else:
        # Running directly in VS Code / Python
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

if __name__ == '__main__':
    # Locate app.py within the execution path
    app_path = resolve_path('app.py')
    
    # Configure Streamlit arguments to bypass prompts and launch automatically
    sys.argv = [
        "streamlit",
        "run",
        app_path,
        "--global.developmentMode=false",
        "--server.headless=true",
        "--browser.gatherUsageStats=false"
    ]
    
    sys.exit(stcli.main())