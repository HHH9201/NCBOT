import os
import sys

PLUGINS_DIR = "/home/hjh/BOT/NCBOT/plugins"

def check_structure():
    print("Checking plugin structure...")
    errors = []
    if not os.path.exists(PLUGINS_DIR):
        print(f"Plugins directory not found: {PLUGINS_DIR}")
        return

    for plugin_name in os.listdir(PLUGINS_DIR):
        plugin_path = os.path.join(PLUGINS_DIR, plugin_name)
        if not os.path.isdir(plugin_path):
            continue
        
        # Skip __pycache__
        if plugin_name == "__pycache__":
            continue

        print(f"Checking plugin: {plugin_name}")
        
        # Check files in plugin directory
        allowed_items = {"main.py", "__init__.py", "tool"}
        found_items = set(os.listdir(plugin_path))
        
        # Ignore __pycache__
        if "__pycache__" in found_items:
            found_items.remove("__pycache__")
        
        # Check for unexpected items
        unexpected = found_items - allowed_items
        if unexpected:
            errors.append(f"[{plugin_name}] Unexpected files/dirs found: {unexpected}. Only main.py, __init__.py, and tool/ are allowed.")

        # Check absolute path comment
        for file_name in ["main.py", "__init__.py"]:
            file_path = os.path.join(plugin_path, file_name)
            if os.path.exists(file_path):
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        first_line = f.readline().strip()
                        if not first_line.startswith(f"# {file_path}"):
                             # Allow some flexibility, e.g. just path
                            if first_line != f"# {file_path}":
                                errors.append(f"[{plugin_name}] {file_name} first line must be absolute path comment. Found: {first_line}")
                except Exception as e:
                    errors.append(f"[{plugin_name}] Could not read {file_name}: {e}")
            else:
                if file_name == "main.py":
                     errors.append(f"[{plugin_name}] Missing main.py")
                # __init__.py is mandatory too
                if file_name == "__init__.py":
                     errors.append(f"[{plugin_name}] Missing __init__.py")

    if errors:
        print("\nFound Errors:")
        for e in errors:
            print(e)
    else:
        print("\nNo structure errors found.")

if __name__ == "__main__":
    check_structure()
