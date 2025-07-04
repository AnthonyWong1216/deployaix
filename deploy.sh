#!/bin/bash

# AIX LPAR Deployment Script for Mac
# This script provides an easy way to run the AIX deployment tool

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Function to print colored output
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

# Function to check if Python is installed
check_python() {
    if ! command -v python3 &> /dev/null; then
        print_error "Python 3 is not installed. Please install Python 3.8 or higher."
        exit 1
    fi
    
    PYTHON_VERSION=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
    print_status "Python version: $PYTHON_VERSION"
}

# Function to check if required packages are installed
check_dependencies() {
    print_status "Checking dependencies..."
    
    if ! python3 -c "import yaml" &> /dev/null; then
        print_warning "PyYAML not found. Installing dependencies..."
        pip3 install -r "$SCRIPT_DIR/requirements.txt"
    fi
    
    if ! python3 -c "import paramiko" &> /dev/null; then
        print_warning "Paramiko not found. Installing dependencies..."
        pip3 install -r "$SCRIPT_DIR/requirements.txt"
    fi
    
    print_success "Dependencies check completed"
}

# Function to show usage
show_usage() {
    echo "AIX LPAR Deployment Tool"
    echo "========================"
    echo ""
    echo "Usage: $0 [OPTIONS]"
    echo ""
    echo "Options:"
    echo "  --profile PROFILE     Deploy LPAR using specified profile"
    echo "  --template TEMPLATE   Deploy using template"
    echo "  --name NAME           Custom LPAR name"
    echo "  --count NUMBER        Number of LPARs to deploy (default: 1)"
    echo "  --password PASSWORD   HMC password"
    echo "  --key-file FILE       SSH key file path"
    echo "  --config FILE         Configuration file (default: lpar_profiles.yaml)"
    echo "  --help                Show this help message"
    echo ""
    echo "Examples:"
    echo "  $0 --profile dev_lpar --password mypassword"
    echo "  $0 --template development --password mypassword"
    echo "  $0 --profile test_lpar --count 3 --password mypassword"
    echo "  $0 --profile prod_lpar --name MY-PROD-SERVER --key-file ~/.ssh/id_rsa"
    echo ""
}

# Function to validate arguments
validate_args() {
    if [[ $# -eq 0 ]]; then
        show_usage
        exit 1
    fi
    
    # Check if --help is requested
    for arg in "$@"; do
        if [[ "$arg" == "--help" ]]; then
            show_usage
            exit 0
        fi
    done
    
    # Check if either --profile or --template is provided
    has_profile=false
    has_template=false
    
    for arg in "$@"; do
        if [[ "$arg" == "--profile" ]]; then
            has_profile=true
        elif [[ "$arg" == "--template" ]]; then
            has_template=true
        fi
    done
    
    if [[ "$has_profile" == false && "$has_template" == false ]]; then
        print_error "Either --profile or --template must be specified"
        show_usage
        exit 1
    fi
}

# Function to check configuration file
check_config() {
    local config_file="$1"
    
    if [[ ! -f "$config_file" ]]; then
        print_error "Configuration file not found: $config_file"
        print_status "Please create or update the configuration file"
        exit 1
    fi
    
    print_success "Configuration file found: $config_file"
}

# Function to run deployment
run_deployment() {
    local python_script="$SCRIPT_DIR/aix_lpar_deployer.py"
    
    if [[ ! -f "$python_script" ]]; then
        print_error "Deployment script not found: $python_script"
        exit 1
    fi
    
    print_status "Starting AIX LPAR deployment..."
    print_status "Script: $python_script"
    print_status "Arguments: $*"
    echo ""
    
    # Run the Python script with all arguments
    python3 "$python_script" "$@"
    
    local exit_code=$?
    
    if [[ $exit_code -eq 0 ]]; then
        print_success "Deployment completed successfully"
    else
        print_error "Deployment failed with exit code: $exit_code"
        exit $exit_code
    fi
}

# Main execution
main() {
    print_status "AIX LPAR Deployment Tool for Mac"
    print_status "================================="
    echo ""
    
    # Check Python installation
    check_python
    
    # Check dependencies
    check_dependencies
    
    # Validate arguments
    validate_args "$@"
    
    # Find configuration file
    config_file="lpar_profiles.yaml"
    for i in "$@"; do
        if [[ "$i" == "--config" ]]; then
            config_file="$2"
            break
        fi
    done
    
    # Check configuration file
    check_config "$config_file"
    
    # Run deployment
    run_deployment "$@"
}

# Execute main function with all arguments
main "$@" 