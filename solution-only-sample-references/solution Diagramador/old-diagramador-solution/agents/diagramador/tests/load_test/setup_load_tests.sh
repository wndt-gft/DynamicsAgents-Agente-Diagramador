#!/bin/bash

# Setup script for load testing environment
# Author: Djalma Saraiva
# Version: 1.0.0

echo "=========================================="
echo "🚀 ARCHITECT AGENT LOAD TEST SETUP"
echo "=========================================="

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Function to check if command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# Function to install packages
install_packages() {
    echo -e "${YELLOW}📦 Installing required packages...${NC}"

    # Create virtual environment if it doesn't exist
    if [ ! -d ".venv_load_test" ]; then
        echo -e "${GREEN}Creating virtual environment...${NC}"
        python3 -m venv .venv_load_test
    fi

    # Activate virtual environment
    echo -e "${GREEN}Activating virtual environment...${NC}"
    source .venv_load_test/bin/activate

    # Upgrade pip
    echo -e "${GREEN}Upgrading pip...${NC}"
    pip install --upgrade pip

    # Install required packages
    echo -e "${GREEN}Installing Locust and dependencies...${NC}"
    pip install locust==2.31.1
    pip install psutil==5.9.8
    pip install requests==2.31.0

    echo -e "${GREEN}✅ Packages installed successfully!${NC}"
}

# Function to verify installation
verify_installation() {
    echo -e "${YELLOW}🔍 Verifying installation...${NC}"

    source .venv_load_test/bin/activate

    # Check Locust
    if python -c "import locust" 2>/dev/null; then
        echo -e "${GREEN}✅ Locust installed successfully${NC}"
        locust --version
    else
        echo -e "${RED}❌ Locust installation failed${NC}"
        return 1
    fi

    # Check psutil
    if python -c "import psutil" 2>/dev/null; then
        echo -e "${GREEN}✅ psutil installed successfully${NC}"
    else
        echo -e "${RED}❌ psutil installation failed${NC}"
        return 1
    fi

    return 0
}

# Function to create requirements file
create_requirements() {
    echo -e "${YELLOW}📝 Creating requirements file...${NC}"

    cat > tests/load_test/requirements.txt << EOF
# Load Testing Requirements
locust==2.31.1
psutil==5.9.8
requests==2.31.0
EOF

    echo -e "${GREEN}✅ Requirements file created${NC}"
}

# Function to create run script
create_run_script() {
    echo -e "${YELLOW}📝 Creating run script...${NC}"

    cat > tests/load_test/run_load_test.sh << 'EOF'
#!/bin/bash

# Activate virtual environment
source .venv_load_test/bin/activate

# Default parameters
DURATION=${1:-60}
USERS=${2:-10}
SPAWN_RATE=${3:-2}
HOST=${4:-"http://localhost:8000"}

echo "Starting load test with:"
echo "  Duration: ${DURATION}s"
echo "  Users: ${USERS}"
echo "  Spawn Rate: ${SPAWN_RATE}"
echo "  Host: ${HOST}"

# Run locust
locust -f tests/load_test/load_test.py \
    --headless \
    -t ${DURATION}s \
    -u ${USERS} \
    -r ${SPAWN_RATE} \
    --host ${HOST} \
    --csv=tests/load_test/.results/results \
    --html=tests/load_test/.results/report.html

echo "Load test completed! Check tests/load_test/.results/ for reports."
EOF

    chmod +x tests/load_test/run_load_test.sh
    echo -e "${GREEN}✅ Run script created${NC}"
}

# Main execution
main() {
    echo -e "${YELLOW}🔧 Starting setup process...${NC}"

    # Check Python
    if ! command_exists python3; then
        echo -e "${RED}❌ Python 3 is not installed. Please install Python 3.8 or higher.${NC}"
        exit 1
    fi

    # Install packages
    install_packages

    # Verify installation
    if verify_installation; then
        echo -e "${GREEN}✅ Installation verified successfully!${NC}"
    else
        echo -e "${RED}❌ Installation verification failed!${NC}"
        exit 1
    fi

    # Create additional files
    create_requirements
    create_run_script

    # Create results directory
    mkdir -p tests/load_test/.results

    echo ""
    echo -e "${GREEN}=========================================="
    echo -e "✅ SETUP COMPLETED SUCCESSFULLY!"
    echo -e "=========================================="
    echo ""
    echo -e "To run load tests:"
    echo -e "  1. Activate virtual environment: ${YELLOW}source .venv_load_test/bin/activate${NC}"
    echo -e "  2. Run tests: ${YELLOW}./tests/load_test/run_load_test.sh [duration] [users] [spawn_rate] [host]${NC}"
    echo ""
    echo -e "Or use Locust directly:"
    echo -e "  ${YELLOW}locust -f tests/load_test/load_test.py${NC}"
    echo ""
    echo -e "For web interface:"
    echo -e "  ${YELLOW}locust -f tests/load_test/load_test.py --host http://localhost:8000${NC}"
    echo -e "  Then open: ${YELLOW}http://localhost:8089${NC}"
    echo ""
}

# Run main function
main