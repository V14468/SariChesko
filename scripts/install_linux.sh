#!/usr/bin/env bash
set -e

# SariChesko Linux Setup Script
# Creates a virtual environment and installs dependencies to run from source.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

echo "Setting up SariChesko in $PROJECT_ROOT..."

# 1. Create virtual environment if it does not exist
VENV_DIR="$PROJECT_ROOT/.venv"
if [ ! -d "$VENV_DIR" ]; then
    echo "Creating virtual environment at $VENV_DIR..."
    python3 -m venv "$VENV_DIR"
else
    echo "Virtual environment already exists at $VENV_DIR."
fi

# 2. Activate virtual environment
echo "Activating virtual environment..."
source "$VENV_DIR/bin/activate"

# 3. Upgrade pip and install requirements
echo "Installing dependencies from requirements.txt..."
pip install --upgrade pip
pip install -r "$PROJECT_ROOT/requirements.txt"
pip install -e "$PROJECT_ROOT"

# 4. Optional desktop menu entry installation
echo ""
read -r -p "Do you want to install the desktop menu entry (sarichesko.desktop)? [y/N]: " response
case "$response" in
    [yY][eE][sS]|[yY])
        APPS_DIR="$HOME/.local/share/applications"
        mkdir -p "$APPS_DIR"
        DESKTOP_SRC="$PROJECT_ROOT/packaging/linux/sarichesko.desktop"
        if [ -f "$DESKTOP_SRC" ]; then
            cp "$DESKTOP_SRC" "$APPS_DIR/"
            echo "Copied $DESKTOP_SRC to $APPS_DIR/"
        else
            echo "Warning: $DESKTOP_SRC not found, skipping desktop entry installation."
        fi
        ;;
    *)
        echo "Skipping desktop menu entry installation."
        ;;
esac

echo ""
echo "=========================================="
echo " Setup complete!"
echo "=========================================="
echo "To run SariChesko, run:"
echo "  source .venv/bin/activate"
echo "  python -m sarichesko.app"
echo "  or: sarichesko"
echo ""
