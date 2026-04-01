#!/bin/bash

# 1. Ensure the script is being SOURCED, not executed.
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    echo "❌ Error: To activate the environment, this script must be sourced."
    echo "Please run it using: source ${0}"
    exit 1
fi

# 2. Dynamically find the directory (this is your 'scripts' folder)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="${SCRIPT_DIR}/venv"
REQ_FILE="${SCRIPT_DIR}/requirements.txt"
MARKER_FILE="${VENV_DIR}/.req_installed"

echo "Checking environment status..."

# 3. Check if the virtual environment needs to be created
if [ ! -d "$VENV_DIR" ]; then
    echo " -> Creating new virtual environment in ${VENV_DIR}..."
    python3 -m venv "$VENV_DIR"
fi

# 4. Activate the environment (This now happens in your CURRENT terminal)
source "${VENV_DIR}/bin/activate"
echo " -> Virtual environment activated."

# 5. Check if dependencies need to be installed
if [ ! -f "$MARKER_FILE" ] || [ "$REQ_FILE" -nt "$MARKER_FILE" ]; then
    if [ -f "$REQ_FILE" ]; then
        echo " -> Dependencies missing or outdated. Installing..."
        pip install --upgrade pip
        pip install -r "$REQ_FILE"
        touch "$MARKER_FILE"
    else
        echo " ⚠️ Notice: No requirements.txt found."
    fi
else
    echo " -> Dependencies are up-to-date."
fi

# 6. Make Python scripts executable and link them to the venv
echo " -> Linking development scripts to the virtual environment..."

# Make only the Python scripts executable so we don't mess with venv/txt files
chmod +x "${SCRIPT_DIR}"/*.py 2>/dev/null

# Symlink each Python script into the venv's bin/ directory
for script in "${SCRIPT_DIR}"/*.py; do
    # Check if the file actually exists (prevents loop errors if no .py files exist yet)
    if [ -f "$script" ]; then
        script_name=$(basename "$script")
        
        # Create the symlink
        #ln -sf "$script" "${VENV_DIR}/bin/${script_name}"
        
        # Create a command without the extension
        cmd_name="${script_name%.py}"
        ln -sf "$script" "${VENV_DIR}/bin/${cmd_name}"
    fi
done

# 7. Register autocompletions (checking if it exists first to avoid errors)
if command -v activate-global-python-argcomplete &> /dev/null; then
    eval "$(activate-global-python-argcomplete --dest=-)"
fi

echo ""
echo "================================================================"
echo " ✅ CATalyst Environment Ready! "
echo "================================================================"