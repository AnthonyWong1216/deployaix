#!/usr/bin/env python3
"""
AIX LPAR Deployment Script
Deploys AIX LPARs using HMC commands based on YAML configuration files.

Author: AnthonyWong1216
Usage: python aix_lpar_deployer.py --profile dev_lpar --count 2
"""

import argparse
import yaml
import paramiko
import time
import logging
import sys
from typing import Dict, List, Any
from pathlib import Path

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('aix_deployment.log'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

class HMCSession:
    """HMC SSH session handler"""
    
    def __init__(self, hostname: str, username: str, password: str | None = None, key_file: str | None = None, port: int = 22):
        self.hostname = hostname
        self.username = username
        self.password = password
        self.key_file = key_file
        self.port = port
        self.client: paramiko.SSHClient | None = None
        self.shell = None
        
    def connect(self) -> bool:
        """Establish SSH connection to HMC"""
        try:
            self.client = paramiko.SSHClient()
            self.client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            
            if self.key_file:
                self.client.connect(
                    hostname=self.hostname,
                    username=self.username,
                    key_filename=self.key_file,
                    port=self.port,
                    timeout=30
                )
            else:
                self.client.connect(
                    hostname=self.hostname,
                    username=self.username,
                    password=self.password,
                    port=self.port,
                    timeout=30
                )
            
            self.shell = self.client.invoke_shell()
            logger.info(f"Successfully connected to HMC: {self.hostname}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to connect to HMC: {e}")
            return False
    
    def execute_command(self, command: str) -> tuple:
        """Execute HMC command and return output"""
        try:
            if self.client is None:
                raise Exception("SSH client not connected")
                
            logger.info(f"Executing command: {command}")
            stdin, stdout, stderr = self.client.exec_command(command)
            
            output = stdout.read().decode('utf-8')
            error = stderr.read().decode('utf-8')
            exit_code = stdout.channel.recv_exit_status()
            
            if exit_code != 0:
                logger.warning(f"Command returned exit code {exit_code}: {error}")
            
            return output, error, exit_code
            
        except Exception as e:
            logger.error(f"Error executing command: {e}")
            return "", str(e), -1
    
    def close(self):
        """Close SSH connection"""
        if self.client:
            self.client.close()
            logger.info("HMC connection closed")

class AIXLPARDeployer:
    """AIX LPAR Deployment Manager"""
    
    def __init__(self, config_file: str):
        self.config_file = config_file
        self.config = self.load_config()
        self.hmc = None
        
    def load_config(self) -> Dict[str, Any]:
        """Load YAML configuration file"""
        try:
            with open(self.config_file, 'r') as file:
                config = yaml.safe_load(file)
            logger.info(f"Configuration loaded from {self.config_file}")
            return config
        except Exception as e:
            logger.error(f"Failed to load configuration: {e}")
            sys.exit(1)
    
    def connect_hmc(self, password: str | None = None, key_file: str | None = None) -> bool:
        """Connect to HMC using configuration"""
        hmc_config = self.config['hmc_config']
        
        self.hmc = HMCSession(
            hostname=hmc_config['hostname'],
            username=hmc_config['username'],
            password=password,
            key_file=key_file,
            port=hmc_config.get('port', 22)
        )
        
        return self.hmc.connect()
    
    def get_managed_system(self, system_name: str) -> Dict[str, Any]:
        """Get managed system configuration"""
        for system in self.config['managed_systems']:
            if system['name'] == system_name:
                return system
        raise ValueError(f"Managed system '{system_name}' not found in configuration")
    
    def create_lpar_profile(self, profile_name: str, lpar_config: Dict[str, Any]) -> bool:
        """Create LPAR profile using HMC commands"""
        try:
            managed_system = self.get_managed_system(lpar_config['managed_system'])
            frame = managed_system['frame']
            
            # Build HMC command for LPAR creation
            cmd = f"mksyscfg -r lpar -m {frame} -i name={lpar_config['name']},"
            cmd += f"profile_name={lpar_config['profile_name']},"
            cmd += f"lpar_id={lpar_config['partition_id']},"
            cmd += f"proc_mode={lpar_config['processor_mode']},"
            cmd += f"min_proc_units={lpar_config['min_proc_units']},"
            cmd += f"desired_proc_units={lpar_config['desired_proc_units']},"
            cmd += f"max_proc_units={lpar_config['max_proc_units']},"
            cmd += f"min_procs={lpar_config['min_procs']},"
            cmd += f"desired_procs={lpar_config['desired_procs']},"
            cmd += f"max_procs={lpar_config['max_procs']},"
            cmd += f"min_mem={lpar_config['min_mem']},"
            cmd += f"desired_mem={lpar_config['desired_mem']},"
            cmd += f"max_mem={lpar_config['max_mem']}"
            
            output, error, exit_code = self.hmc.execute_command(cmd)
            
            if exit_code == 0:
                logger.info(f"Successfully created LPAR profile: {lpar_config['name']}")
                return True
            else:
                logger.error(f"Failed to create LPAR profile: {error}")
                return False
                
        except Exception as e:
            logger.error(f"Error creating LPAR profile: {e}")
            return False
    
    def configure_virtual_adapters(self, lpar_name: str, managed_system: str, adapters: List[Dict[str, Any]]) -> bool:
        """Configure virtual adapters for LPAR"""
        try:
            frame = self.get_managed_system(managed_system)['frame']
            
            for adapter in adapters:
                cmd = f"chsyscfg -r prof -m {frame} -i lpar_name={lpar_name},"
                cmd += f"name=default,"
                cmd += f"virtual_eth_adapters={adapter['slot_id']}/0/{adapter['port_vlan_id']}/"
                cmd += f"{adapter['default_vlan_id']}/1/1"
                
                output, error, exit_code = self.hmc.execute_command(cmd)
                
                if exit_code != 0:
                    logger.error(f"Failed to configure virtual adapter: {error}")
                    return False
            
            logger.info(f"Successfully configured virtual adapters for {lpar_name}")
            return True
            
        except Exception as e:
            logger.error(f"Error configuring virtual adapters: {e}")
            return False
    
    def allocate_storage(self, lpar_name: str, managed_system: str, storage_config: List[Dict[str, Any]]) -> bool:
        """Allocate storage for LPAR"""
        try:
            frame = self.get_managed_system(managed_system)['frame']
            
            for storage in storage_config:
                # This would need to be customized based on your VIOS setup
                cmd = f"chsyscfg -r prof -m {frame} -i lpar_name={lpar_name},"
                cmd += f"name=default,"
                cmd += f"virtual_scsi_adapters=4/client/{storage['vios_name']}/0"
                
                output, error, exit_code = self.hmc.execute_command(cmd)
                
                if exit_code != 0:
                    logger.error(f"Failed to allocate storage: {error}")
                    return False
            
            logger.info(f"Successfully allocated storage for {lpar_name}")
            return True
            
        except Exception as e:
            logger.error(f"Error allocating storage: {e}")
            return False
    
    def start_lpar(self, lpar_name: str, managed_system: str) -> bool:
        """Start the LPAR"""
        try:
            frame = self.get_managed_system(managed_system)['frame']
            cmd = f"chsysstate -r lpar -m {frame} -o on -n {lpar_name} -f default"
            
            output, error, exit_code = self.hmc.execute_command(cmd)
            
            if exit_code == 0:
                logger.info(f"Successfully started LPAR: {lpar_name}")
                return True
            else:
                logger.error(f"Failed to start LPAR: {error}")
                return False
                
        except Exception as e:
            logger.error(f"Error starting LPAR: {e}")
            return False
    
    def deploy_lpar(self, profile_name: str, lpar_name: str = None) -> bool:
        """Deploy a single LPAR based on profile"""
        try:
            if profile_name not in self.config['lpar_profiles']:
                logger.error(f"Profile '{profile_name}' not found in configuration")
                return False
            
            lpar_config = self.config['lpar_profiles'][profile_name].copy()
            
            # Override name if provided
            if lpar_name:
                lpar_config['name'] = lpar_name
            
            logger.info(f"Starting deployment of LPAR: {lpar_config['name']}")
            
            # Step 1: Create LPAR profile
            if not self.create_lpar_profile(profile_name, lpar_config):
                return False
            
            # Step 2: Configure virtual adapters
            if 'virtual_adapters' in lpar_config:
                if not self.configure_virtual_adapters(
                    lpar_config['name'], 
                    lpar_config['managed_system'], 
                    lpar_config['virtual_adapters']
                ):
                    return False
            
            # Step 3: Allocate storage
            if 'storage' in lpar_config:
                if not self.allocate_storage(
                    lpar_config['name'],
                    lpar_config['managed_system'],
                    lpar_config['storage']
                ):
                    return False
            
            # Step 4: Start LPAR
            if not self.start_lpar(lpar_config['name'], lpar_config['managed_system']):
                return False
            
            logger.info(f"Successfully deployed LPAR: {lpar_config['name']}")
            return True
            
        except Exception as e:
            logger.error(f"Error deploying LPAR: {e}")
            return False
    
    def deploy_template(self, template_name: str) -> bool:
        """Deploy multiple LPARs using a template"""
        try:
            if template_name not in self.config['deployment_templates']:
                logger.error(f"Template '{template_name}' not found in configuration")
                return False
            
            template = self.config['deployment_templates'][template_name]
            success_count = 0
            
            for deployment in template:
                profile_name = deployment['profile']
                count = deployment['count']
                naming_pattern = deployment['naming_pattern']
                
                for i in range(1, count + 1):
                    lpar_name = naming_pattern.format(index=i)
                    
                    if self.deploy_lpar(profile_name, lpar_name):
                        success_count += 1
                    else:
                        logger.error(f"Failed to deploy LPAR: {lpar_name}")
            
            logger.info(f"Template deployment completed: {success_count} LPARs deployed successfully")
            return success_count > 0
            
        except Exception as e:
            logger.error(f"Error deploying template: {e}")
            return False

def main():
    parser = argparse.ArgumentParser(description='AIX LPAR Deployment Script')
    parser.add_argument('--config', default='lpar_profiles.yaml', help='Configuration file path')
    parser.add_argument('--profile', help='LPAR profile name to deploy')
    parser.add_argument('--template', help='Deployment template name')
    parser.add_argument('--name', help='Custom LPAR name (overrides profile name)')
    parser.add_argument('--count', type=int, default=1, help='Number of LPARs to deploy')
    parser.add_argument('--password', help='HMC password')
    parser.add_argument('--key-file', help='SSH key file path')
    
    args = parser.parse_args()
    
    # Initialize deployer
    deployer = AIXLPARDeployer(args.config)
    
    # Connect to HMC
    if not deployer.connect_hmc(args.password, args.key_file):
        logger.error("Failed to connect to HMC")
        sys.exit(1)
    
    try:
        if args.template:
            # Deploy using template
            success = deployer.deploy_template(args.template)
        elif args.profile:
            # Deploy single profile
            if args.count > 1:
                # Deploy multiple instances
                success_count = 0
                for i in range(args.count):
                    lpar_name = f"{args.profile}-{i+1:02d}" if not args.name else f"{args.name}-{i+1:02d}"
                    if deployer.deploy_lpar(args.profile, lpar_name):
                        success_count += 1
                success = success_count > 0
            else:
                # Deploy single instance
                success = deployer.deploy_lpar(args.profile, args.name)
        else:
            logger.error("Either --profile or --template must be specified")
            sys.exit(1)
        
        if success:
            logger.info("Deployment completed successfully")
            sys.exit(0)
        else:
            logger.error("Deployment failed")
            sys.exit(1)
            
    finally:
        deployer.hmc.close()

if __name__ == "__main__":
    main() 