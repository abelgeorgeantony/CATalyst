#!/bin/bash

# 1. Ensure the script is being SOURCED, not executed.
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    echo "❌ Error: To activate the environment, this script must be sourced."
    echo "Please run it using: source ${0}"
    exit 1
fi

# 2. Dynamically find the directory (using BASH_SOURCE is required when sourcing)
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
    echo " -> Dependencies missing or outdated. Installing..."
    pip install --upgrade pip
    pip install -r "$REQ_FILE"
    touch "$MARKER_FILE"
else
    echo " -> Dependencies are up-to-date."
fi

# 6. Make all Python scripts executable
chmod +x "${SCRIPT_DIR}"/*.py

# 7. Register autocompletions for the exact commands you will type
eval "$(activate-global-python-argcomplete --dest=-)"

echo ""
echo "================================================================"
echo " ✅ CATalyst Environment Ready! "
echo "================================================================"