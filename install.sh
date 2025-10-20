#!/bin/bash
# BioAnalyzer System Installation Script

set -e

echo "🧬 BioAnalyzer System Installation"
echo "=================================="

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

print_status() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check if running as root
if [[ $EUID -eq 0 ]]; then
    print_warning "Running as root. This will install BioAnalyzer system-wide."
    INSTALL_DIR="/usr/local/bin"
    SYSTEM_INSTALL=true
else
    print_status "Installing BioAnalyzer for current user."
    INSTALL_DIR="$HOME/.local/bin"
    SYSTEM_INSTALL=false
fi

# Create installation directory
print_status "Creating installation directory: $INSTALL_DIR"
mkdir -p "$INSTALL_DIR"

# Get the current directory (BioAnalyzer-Backend)
CURRENT_DIR=$(pwd)
print_status "BioAnalyzer backend directory: $CURRENT_DIR"

# Check if we're in the right directory
if [[ ! -f "cli.py" ]] || [[ ! -f "BioAnalyzer" ]]; then
    print_error "Please run this script from the BioAnalyzer-Backend directory"
    exit 1
fi

# Install the BioAnalyzer command
print_status "Installing BioAnalyzer command..."
cp BioAnalyzer "$INSTALL_DIR/"
chmod +x "$INSTALL_DIR/BioAnalyzer"

# Create a wrapper script that sets the correct path
cat > "$INSTALL_DIR/bioanalyzer" << EOF
#!/bin/bash
# BioAnalyzer wrapper script

export BIOANALYZER_PATH="$CURRENT_DIR"
exec "$INSTALL_DIR/BioAnalyzer" "\$@"
EOF

chmod +x "$INSTALL_DIR/bioanalyzer"

# Add to PATH if not already there
if [[ ":$PATH:" != *":$INSTALL_DIR:"* ]]; then
    print_status "Adding $INSTALL_DIR to PATH..."
    
    if [[ $SYSTEM_INSTALL == true ]]; then
        # System-wide installation
        echo "export PATH=\"\$PATH:$INSTALL_DIR\"" >> /etc/environment
        print_warning "Please log out and log back in for PATH changes to take effect"
    else
        # User installation
        SHELL_CONFIG=""
        if [[ -f "$HOME/.bashrc" ]]; then
            SHELL_CONFIG="$HOME/.bashrc"
        elif [[ -f "$HOME/.zshrc" ]]; then
            SHELL_CONFIG="$HOME/.zshrc"
        elif [[ -f "$HOME/.profile" ]]; then
            SHELL_CONFIG="$HOME/.profile"
        fi
        
        if [[ -n "$SHELL_CONFIG" ]]; then
            echo "export PATH=\"\$PATH:$INSTALL_DIR\"" >> "$SHELL_CONFIG"
            print_status "Added to PATH in $SHELL_CONFIG"
            print_warning "Please run 'source $SHELL_CONFIG' or restart your terminal"
        else
            print_warning "Could not find shell configuration file. Please add $INSTALL_DIR to your PATH manually."
        fi
    fi
fi

# Create desktop entry for GUI applications
if command -v xdg-desktop-menu &> /dev/null; then
    print_status "Creating desktop entry..."
    
    DESKTOP_DIR="$HOME/.local/share/applications"
    mkdir -p "$DESKTOP_DIR"
    
    cat > "$DESKTOP_DIR/bioanalyzer.desktop" << EOF
[Desktop Entry]
Version=1.0
Type=Application
Name=BioAnalyzer CLI
Comment=BugSigDB Field Analysis Tool
Exec=$INSTALL_DIR/BioAnalyzer fields
Icon=applications-science
Terminal=true
Categories=Science;Biology;
EOF
    
    chmod +x "$DESKTOP_DIR/bioanalyzer.desktop"
    print_success "Desktop entry created"
fi

# Test the installation
print_status "Testing installation..."
if "$INSTALL_DIR/BioAnalyzer" fields > /dev/null 2>&1; then
    print_success "BioAnalyzer command installed successfully!"
else
    print_warning "Installation completed but command test failed"
    print_warning "You may need to install Python dependencies:"
    print_warning "pip install -r $CURRENT_DIR/config/requirements.txt"
fi

echo ""
echo "🎉 Installation Complete!"
echo "========================"
echo ""
echo "BioAnalyzer is now available as:"
echo "  • BioAnalyzer (main command)"
echo "  • bioanalyzer (alternative command)"
echo ""
echo "Usage examples:"
echo "  BioAnalyzer fields"
echo "  BioAnalyzer analyze 12345678"
echo "  BioAnalyzer analyze --batch 12345678,87654321"
echo "  BioAnalyzer analyze --file pmids.txt"
echo ""
echo "Installation location: $INSTALL_DIR"
echo "Backend directory: $CURRENT_DIR"
echo ""

if [[ $SYSTEM_INSTALL == true ]]; then
    print_warning "System-wide installation completed."
    print_warning "All users can now use the BioAnalyzer command."
else
    print_status "User installation completed."
    print_status "Only the current user can use the BioAnalyzer command."
fi

print_success "BioAnalyzer is ready to use! 🧬"
