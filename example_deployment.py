#!/usr/bin/env python3
"""
Example AIX LPAR Deployment Script
Demonstrates how to use the AIX LPAR Deployer programmatically.

Author: AnthonyWong1216
"""

import sys
import os
from aix_lpar_deployer import AIXLPARDeployer

def main():
    """Example deployment scenarios"""
    
    # Initialize the deployer
    config_file = "lpar_profiles.yaml"
    deployer = AIXLPARDeployer(config_file)
    
    # Example 1: Deploy a single development LPAR
    print("=== Example 1: Deploy Single Development LPAR ===")
    
    # Connect to HMC (you'll need to provide password or key file)
    password = input("Enter HMC password: ")  # In production, use secure methods
    
    if not deployer.connect_hmc(password=password):
        print("Failed to connect to HMC")
        return
    
    try:
        # Deploy a single development LPAR
        success = deployer.deploy_lpar("dev_lpar", "MY-DEV-LPAR-01")
        if success:
            print("✓ Development LPAR deployed successfully")
        else:
            print("✗ Development LPAR deployment failed")
    
    except Exception as e:
        print(f"Error during deployment: {e}")
    
    finally:
        deployer.hmc.close()

def deploy_multiple_lpars():
    """Example: Deploy multiple LPARs"""
    print("\n=== Example 2: Deploy Multiple LPARs ===")
    
    config_file = "lpar_profiles.yaml"
    deployer = AIXLPARDeployer(config_file)
    
    password = input("Enter HMC password: ")
    
    if not deployer.connect_hmc(password=password):
        print("Failed to connect to HMC")
        return
    
    try:
        # Deploy 3 test LPARs
        success_count = 0
        for i in range(1, 4):
            lpar_name = f"TEST-LPAR-{i:02d}"
            if deployer.deploy_lpar("test_lpar", lpar_name):
                success_count += 1
                print(f"✓ Deployed {lpar_name}")
            else:
                print(f"✗ Failed to deploy {lpar_name}")
        
        print(f"\nDeployment Summary: {success_count}/3 LPARs deployed successfully")
    
    except Exception as e:
        print(f"Error during deployment: {e}")
    
    finally:
        deployer.hmc.close()

def deploy_using_template():
    """Example: Deploy using template"""
    print("\n=== Example 3: Deploy Using Template ===")
    
    config_file = "lpar_profiles.yaml"
    deployer = AIXLPARDeployer(config_file)
    
    password = input("Enter HMC password: ")
    
    if not deployer.connect_hmc(password=password):
        print("Failed to connect to HMC")
        return
    
    try:
        # Deploy using development template
        success = deployer.deploy_template("development")
        if success:
            print("✓ Template deployment completed successfully")
        else:
            print("✗ Template deployment failed")
    
    except Exception as e:
        print(f"Error during template deployment: {e}")
    
    finally:
        deployer.hmc.close()

def validate_configuration():
    """Example: Validate configuration without deploying"""
    print("\n=== Example 4: Validate Configuration ===")
    
    config_file = "lpar_profiles.yaml"
    deployer = AIXLPARDeployer(config_file)
    
    # Check if profiles exist
    profiles = deployer.config.get('lpar_profiles', {})
    print(f"Found {len(profiles)} LPAR profiles:")
    
    for profile_name, profile_config in profiles.items():
        print(f"  - {profile_name}: {profile_config.get('name', 'N/A')}")
    
    # Check if templates exist
    templates = deployer.config.get('deployment_templates', {})
    print(f"\nFound {len(templates)} deployment templates:")
    
    for template_name, template_config in templates.items():
        print(f"  - {template_name}")
        for deployment in template_config:
            print(f"    * {deployment.get('profile', 'N/A')} x{deployment.get('count', 1)}")

if __name__ == "__main__":
    print("AIX LPAR Deployment Examples")
    print("=" * 40)
    
    # Validate configuration first
    validate_configuration()
    
    # Ask user which example to run
    print("\nChoose an example to run:")
    print("1. Deploy single development LPAR")
    print("2. Deploy multiple test LPARs")
    print("3. Deploy using template")
    print("4. Exit")
    
    choice = input("\nEnter your choice (1-4): ")
    
    if choice == "1":
        main()
    elif choice == "2":
        deploy_multiple_lpars()
    elif choice == "3":
        deploy_using_template()
    elif choice == "4":
        print("Exiting...")
    else:
        print("Invalid choice. Exiting...") 