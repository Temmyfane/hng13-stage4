#!/usr/bin/env python3
"""
vpcctl - Virtual Private Cloud Control Tool
Simulates AWS VPC functionality using Linux networking primitives
"""

import subprocess
import json
import sys
import os
from pathlib import Path
import ipaddress

# Configuration directory
CONFIG_DIR = Path.home() / ".vpcctl"
CONFIG_DIR.mkdir(exist_ok=True)

class IPUtils:
    """Simple IP address utilities"""
    
    @staticmethod
    def get_gateway_ip(vpc_cidr):
        """Get gateway IP (first usable IP in VPC range)"""
        network = ipaddress.IPv4Network(vpc_cidr, strict=False)
        return str(network.network_address + 1)
    
    @staticmethod
    def get_subnet_ip(subnet_cidr):
        """Get subnet interface IP (first usable IP in subnet)"""
        network = ipaddress.IPv4Network(subnet_cidr, strict=False)
        return f"{network.network_address + 1}/{network.prefixlen}"

class Logger:
    """Simple logging utility"""
    @staticmethod
    def info(msg):
        print(f"[INFO] {msg}")
    
    @staticmethod
    def success(msg):
        print(f"[SUCCESS] ✓ {msg}")
    
    @staticmethod
    def error(msg):
        print(f"[ERROR] ✗ {msg}", file=sys.stderr)
    
    @staticmethod
    def warn(msg):
        print(f"[WARN] ⚠ {msg}")

def run_cmd(cmd, check=True, capture=True, ignore_exists=False, ignore_errors=False, capture_output=False):
    """Execute shell command with logging"""
    Logger.info(f"Executing: {cmd}")
    try:
        if capture_output:
            result = subprocess.run(cmd, shell=True, check=check, capture_output=True, text=True)
            return result
        else:
            result = subprocess.run(
                cmd, 
                shell=True, 
                check=check,
                capture_output=capture,
                text=True
            )
            return result.stdout if capture else None
    except subprocess.CalledProcessError as e:
        # Handle "already exists" or "not found" errors gracefully if requested
        if ignore_exists and (
            "File exists" in str(e.stderr) or 
            "RTNETLINK answers: File exists" in str(e.stderr) or
            "Address already assigned" in str(e.stderr) or
            "already exists" in str(e.stderr) or
            "Cannot find device" in str(e.stderr) or
            "Nexthop has invalid gateway" in str(e.stderr) or
            "Attribute failed policy validation" in str(e.stderr)
        ):
            Logger.warn(f"Resource already configured, continuing: {cmd}")
            return None
        
        # Ignore all errors if requested (for cleanup operations)
        if ignore_errors:
            Logger.warn(f"Command failed but ignoring: {cmd}")
            return None
        
        Logger.error(f"Command failed: {e}")
        if capture:
            Logger.error(f"Output: {e.stderr}")
        raise

class VPC:
    """Represents a Virtual Private Cloud"""
    
    def __init__(self, name, cidr):
        self.name = name
        self.cidr = cidr
        self.bridge = f"vpc-{name}"
        self.subnets = {}
        self.config_file = CONFIG_DIR / f"{name}.json"
    
    def create(self):
        """Create VPC infrastructure"""
        Logger.info(f"Creating VPC: {self.name} with CIDR: {self.cidr}")
        
        # Create bridge (acts as VPC router)
        run_cmd(f"ip link add {self.bridge} type bridge", ignore_exists=True)
        run_cmd(f"ip link set {self.bridge} up")
        
        # Assign gateway IP to bridge (first IP in range)
        gateway_ip = IPUtils.get_gateway_ip(self.cidr)
        run_cmd(f"ip addr add {gateway_ip}/{self.cidr.split('/')[1]} dev {self.bridge}", ignore_exists=True)
        
        Logger.success(f"VPC {self.name} created with bridge {self.bridge}")
        self.save_config()
    
    def add_subnet(self, subnet_name, cidr, subnet_type="private"):
        """Add subnet (network namespace) to VPC"""
        Logger.info(f"Adding {subnet_type} subnet: {subnet_name} ({cidr})")
        
        ns_name = f"{self.name}-{subnet_name}"
        veth_host = f"veth-{subnet_name}"
        veth_ns = f"v{subnet_name[:10]}"  # Keep it short for Linux interface name limits
        
        # Create network namespace
        run_cmd(f"ip netns add {ns_name}", ignore_exists=True)
        
        # Create veth pair (virtual ethernet cable)
        run_cmd(f"ip link add {veth_host} type veth peer name {veth_ns}", ignore_exists=True)
        
        # Connect host end to bridge
        run_cmd(f"ip link set {veth_host} master {self.bridge}", ignore_exists=True)
        run_cmd(f"ip link set {veth_host} up", ignore_exists=True)
        
        # Move namespace end into namespace
        run_cmd(f"ip link set {veth_ns} netns {ns_name}", ignore_exists=True)
        
        # Configure namespace interface
        subnet_ip = IPUtils.get_subnet_ip(cidr)
        run_cmd(f"ip netns exec {ns_name} ip addr add {subnet_ip} dev {veth_ns}", ignore_exists=True)
        run_cmd(f"ip netns exec {ns_name} ip link set {veth_ns} up", ignore_exists=True)
        run_cmd(f"ip netns exec {ns_name} ip link set lo up", ignore_exists=True)
        
        # Add default route through bridge
        gateway_ip = IPUtils.get_gateway_ip(self.cidr)
        run_cmd(f"ip netns exec {ns_name} ip route add default via {gateway_ip}", ignore_exists=True)
        
        # Store subnet info
        self.subnets[subnet_name] = {
            "cidr": cidr,
            "type": subnet_type,
            "namespace": ns_name,
            "veth_host": veth_host,
            "ip": subnet_ip
        }
        
        Logger.success(f"Subnet {subnet_name} created in namespace {ns_name}")
        self.save_config()
    
    def enable_nat(self, internet_interface="eth0"):
        """Enable NAT for public subnets"""
        Logger.info(f"Enabling NAT gateway on interface {internet_interface}")
        
        # Enable IP forwarding
        run_cmd("sysctl -w net.ipv4.ip_forward=1")
        
        # Setup NAT using iptables
        run_cmd(f"iptables -t nat -A POSTROUTING -s {self.cidr} -o {internet_interface} -j MASQUERADE")
        run_cmd(f"iptables -A FORWARD -i {self.bridge} -o {internet_interface} -j ACCEPT")
        run_cmd(f"iptables -A FORWARD -i {internet_interface} -o {self.bridge} -m state --state RELATED,ESTABLISHED -j ACCEPT")
        
        Logger.success("NAT gateway enabled")
    
    def apply_firewall(self, policy_file):
        """Apply firewall rules from JSON policy"""
        Logger.info(f"Applying firewall policy from {policy_file}")
        
        with open(policy_file, 'r') as f:
            policy = json.load(f)
        
        subnet_cidr = policy.get("subnet")
        subnet_name = None
        
        # Find matching subnet
        for name, info in self.subnets.items():
            if info["cidr"] == subnet_cidr:
                subnet_name = name
                break
        
        if not subnet_name:
            Logger.error(f"Subnet {subnet_cidr} not found")
            return
        
        ns_name = self.subnets[subnet_name]["namespace"]
        
        # Apply ingress rules
        for rule in policy.get("ingress", []):
            port = rule["port"]
            protocol = rule["protocol"]
            action = rule["action"].upper()
            
            if action == "ALLOW":
                target = "ACCEPT"
            elif action == "DENY":
                target = "DROP"
            else:
                continue
            
            cmd = f"ip netns exec {ns_name} iptables -A INPUT -p {protocol} --dport {port} -j {target}"
            run_cmd(cmd)
            Logger.success(f"Rule applied: {protocol}/{port} -> {action}")
    
    def peer_with(self, other_vpc):
        """Establish VPC peering connection"""
        Logger.info(f"Peering VPC {self.name} with {other_vpc.name}")
        
        # Create veth pair between bridges
        peer_veth1 = f"peer-{self.name}-{other_vpc.name}"
        peer_veth2 = f"peer-{other_vpc.name}-{self.name}"
        
        run_cmd(f"ip link add {peer_veth1} type veth peer name {peer_veth2}")
        run_cmd(f"ip link set {peer_veth1} master {self.bridge}")
        run_cmd(f"ip link set {peer_veth2} master {other_vpc.bridge}")
        run_cmd(f"ip link set {peer_veth1} up")
        run_cmd(f"ip link set {peer_veth2} up")
        
        # Add routes
        run_cmd(f"ip route add {other_vpc.cidr} via {other_vpc.cidr.split('/')[0].rsplit('.', 1)[0]}.0.1 dev {self.bridge}")
        run_cmd(f"ip route add {self.cidr} via {self.cidr.split('/')[0].rsplit('.', 1)[0]}.0.1 dev {other_vpc.bridge}")
        
        Logger.success(f"VPC peering established between {self.name} and {other_vpc.name}")
    
    def deploy_webserver(self, subnet_name, port=8000):
        """Deploy simple Python HTTP server in subnet"""
        if subnet_name not in self.subnets:
            Logger.error(f"Subnet {subnet_name} not found")
            return
        
        ns_name = self.subnets[subnet_name]["namespace"]
        Logger.info(f"Deploying web server in {subnet_name} on port {port}")
        
        # Create a simple index.html and start server on all interfaces
        subnet_cidr = self.subnets[subnet_name]["cidr"]
        subnet_ip = IPUtils.get_subnet_ip(subnet_cidr).split('/')[0]
        cmd = f"""ip netns exec {ns_name} sh -c '
            mkdir -p /tmp/www
            echo "<h1>Hello from {subnet_name} in VPC {self.name}</h1>" > /tmp/www/index.html
            cd /tmp/www && python3 -m http.server {port} --bind {subnet_ip} > /tmp/webserver.log 2>&1 &
        '"""
        run_cmd(cmd)
        Logger.success(f"Web server deployed at http://{subnet_ip}:{port}")
    
    def delete(self):
        """Delete VPC and all resources"""
        Logger.info(f"Deleting VPC: {self.name}")
        
        # Delete subnets (namespaces)
        for subnet_name, info in self.subnets.items():
            ns_name = info["namespace"]
            Logger.info(f"Deleting subnet {subnet_name}")
            run_cmd(f"ip netns del {ns_name}", check=False)
        
        # Delete bridge
        run_cmd(f"ip link del {self.bridge}", check=False)
        
        # Clean up iptables rules
        cidr = self.cidr
        run_cmd(f"iptables -t nat -D POSTROUTING -s {cidr} -o eth0 -j MASQUERADE", check=False)
        
        # Remove config file
        if self.config_file.exists():
            self.config_file.unlink()
        
        Logger.success(f"VPC {self.name} deleted")
    
    def save_config(self):
        """Save VPC configuration to file"""
        config = {
            "name": self.name,
            "cidr": self.cidr,
            "bridge": self.bridge,
            "subnets": self.subnets
        }
        with open(self.config_file, 'w') as f:
            json.dump(config, f, indent=2)
    
    @classmethod
    def load(cls, name):
        """Load VPC from config file"""
        config_file = CONFIG_DIR / f"{name}.json"
        if not config_file.exists():
            raise FileNotFoundError(f"VPC {name} not found")
        
        with open(config_file, 'r') as f:
            config = json.load(f)
        
        vpc = cls(config["name"], config["cidr"])
        vpc.subnets = config["subnets"]
        return vpc
    
    def show(self):
        """Display VPC information"""
        print(f"\n{'='*50}")
        print(f"VPC: {self.name}")
        print(f"CIDR: {self.cidr}")
        print(f"Bridge: {self.bridge}")
        print(f"{'='*50}")
        
        if self.subnets:
            print("\nSubnets:")
            for name, info in self.subnets.items():
                print(f"  - {name} ({info['type']})")
                print(f"    CIDR: {info['cidr']}")
                print(f"    Namespace: {info['namespace']}")
                print(f"    IP: {info['ip']}")
        else:
            print("\nNo subnets configured")
        print()

def main():
    """Main CLI entry point"""
    if len(sys.argv) < 2:
        print("Usage: vpcctl <command> [options]")
        print("\nCommands:")
        print("  create <vpc-name> <cidr>          - Create new VPC")
        print("  add-subnet <vpc> <name> <cidr> <type>  - Add subnet (type: public/private)")
        print("  enable-nat <vpc> [interface]      - Enable NAT gateway")
        print("  apply-policy <vpc> <policy.json>  - Apply firewall policy")
        print("  deploy-web <vpc> <subnet> [port]  - Deploy web server")
        print("  show <vpc>                        - Show VPC details")
        print("  delete <vpc>                      - Delete VPC")
        print("  list                              - List all VPCs")
        print("  diagnose                          - Diagnose network state")
        print("  cleanup-orphans                   - Clean up orphaned resources")
        print("  recover                           - Recover VPC configs from existing infrastructure")
        print("  fix-connectivity <vpc>            - Fix network connectivity for VPC")
        sys.exit(1)
    
    command = sys.argv[1]
    
    try:
        if command == "create":
            vpc_name = sys.argv[2]
            cidr = sys.argv[3]
            vpc = VPC(vpc_name, cidr)
            vpc.create()
        
        elif command == "add-subnet":
            vpc_name = sys.argv[2]
            subnet_name = sys.argv[3]
            cidr = sys.argv[4]
            subnet_type = sys.argv[5] if len(sys.argv) > 5 else "private"
            vpc = VPC.load(vpc_name)
            vpc.add_subnet(subnet_name, cidr, subnet_type)
        
        elif command == "enable-nat":
            vpc_name = sys.argv[2]
            interface = sys.argv[3] if len(sys.argv) > 3 else "eth0"
            vpc = VPC.load(vpc_name)
            vpc.enable_nat(interface)
        
        elif command == "apply-policy":
            vpc_name = sys.argv[2]
            policy_file = sys.argv[3]
            vpc = VPC.load(vpc_name)
            vpc.apply_firewall(policy_file)
        
        elif command == "deploy-web":
            vpc_name = sys.argv[2]
            subnet_name = sys.argv[3]
            port = int(sys.argv[4]) if len(sys.argv) > 4 else 8000
            vpc = VPC.load(vpc_name)
            vpc.deploy_webserver(subnet_name, port)
        
        elif command == "show":
            vpc_name = sys.argv[2]
            vpc = VPC.load(vpc_name)
            vpc.show()
        
        elif command == "delete":
            vpc_name = sys.argv[2]
            vpc = VPC.load(vpc_name)
            vpc.delete()
        
        elif command == "list":
            vpcs = list(CONFIG_DIR.glob("*.json"))
            if vpcs:
                print("\nConfigured VPCs:")
                for vpc_file in vpcs:
                    print(f"  - {vpc_file.stem}")
            else:
                print("\nNo VPCs configured")
        
        elif command == "diagnose":
            # Diagnostic command to check orphaned namespaces
            print("\nDiagnosing network state...")
            result = run_cmd("ip netns list", capture_output=True)
            namespaces = result.stdout.strip().split('\n') if result.stdout.strip() else []
            
            print(f"\nFound {len(namespaces)} network namespaces:")
            for ns in namespaces:
                ns_name = ns.split()[0] if ns.strip() else ""
                if ns_name:
                    print(f"  - {ns_name}")
            
            # Check for VPC bridges
            result = run_cmd("ip link show type bridge", capture_output=True)
            bridges = []
            for line in result.stdout.split('\n'):
                if 'vpc-' in line:
                    bridge_name = line.split(':')[1].strip().split('@')[0]
                    bridges.append(bridge_name)
            
            print(f"\nFound {len(bridges)} VPC bridges:")
            for bridge in bridges:
                print(f"  - {bridge}")
            
            # Check VPC configs
            vpcs = list(CONFIG_DIR.glob("*.json")) if CONFIG_DIR.exists() else []
            
            # Suggest recovery
            if namespaces and not vpcs:
                print("\n⚠️  Found orphaned namespaces without VPC config!")
                print("   Run 'vpcctl cleanup-orphans' to clean up")
                print("   Or recreate VPCs to restore connectivity")
        
        elif command == "cleanup-orphans":
            # Clean up orphaned namespaces and bridges
            print("\nCleaning up orphaned network resources...")
            
            # Remove namespaces
            result = run_cmd("ip netns list", capture_output=True)
            namespaces = result.stdout.strip().split('\n') if result.stdout.strip() else []
            
            for ns in namespaces:
                ns_name = ns.split()[0] if ns.strip() else ""
                if ns_name and ('-public' in ns_name or '-private' in ns_name):
                    print(f"Removing namespace: {ns_name}")
                    run_cmd(f"ip netns delete {ns_name}", ignore_errors=True)
            
            # Remove VPC bridges
            result = run_cmd("ip link show type bridge", capture_output=True)
            for line in result.stdout.split('\n'):
                if 'vpc-' in line:
                    bridge_name = line.split(':')[1].strip().split('@')[0]
                    print(f"Removing bridge: {bridge_name}")
                    run_cmd(f"ip link delete {bridge_name}", ignore_errors=True)
            
            print("✓ Cleanup complete")
        
        elif command == "recover":
            # Recover VPC configurations from existing infrastructure
            print("\nRecovering VPC configurations from existing infrastructure...")
            
            # Get existing namespaces
            result = run_cmd("ip netns list", capture_output=True)
            namespaces = result.stdout.strip().split('\n') if result.stdout.strip() else []
            
            # Parse VPC structure from namespaces
            vpcs = {}
            for ns in namespaces:
                ns_name = ns.split()[0] if ns.strip() else ""
                if '-' in ns_name:
                    parts = ns_name.split('-')
                    if len(parts) >= 2:
                        vpc_name = parts[0]
                        subnet_name = '-'.join(parts[1:])
                        
                        if vpc_name not in vpcs:
                            vpcs[vpc_name] = []
                        vpcs[vpc_name].append((subnet_name, ns_name))
            
            print(f"Found {len(vpcs)} VPCs to recover:")
            for vpc_name, subnets in vpcs.items():
                print(f"  - {vpc_name}: {len(subnets)} subnets")
            
            # Recover each VPC
            for vpc_name, subnets in vpcs.items():
                print(f"\nRecovering VPC: {vpc_name}")
                
                # Determine CIDR based on VPC name (common patterns)
                if vpc_name == "dev":
                    cidr = "10.0.0.0/16"
                elif vpc_name == "prod":
                    cidr = "10.1.0.0/16"
                elif vpc_name == "test":
                    cidr = "10.2.0.0/16"
                else:
                    cidr = f"10.{hash(vpc_name) % 254}.0.0/16"
                
                # Create VPC config
                vpc_config = {
                    "name": vpc_name,
                    "cidr": cidr,
                    "subnets": {}
                }
                
                # Add subnets
                subnet_counter = 1
                for subnet_name, ns_name in subnets:
                    subnet_cidr = f"10.{0 if vpc_name == 'dev' else 1 if vpc_name == 'prod' else 2}.{subnet_counter}.0/24"
                    subnet_ip = f"10.{0 if vpc_name == 'dev' else 1 if vpc_name == 'prod' else 2}.{subnet_counter}.10/24"
                    
                    subnet_type = "public" if "public" in subnet_name else "private"
                    
                    vpc_config["subnets"][subnet_name] = {
                        "cidr": subnet_cidr,
                        "type": subnet_type,
                        "namespace": ns_name,
                        "ip": subnet_ip
                    }
                    subnet_counter += 1
                
                # Save config
                config_file = CONFIG_DIR / f"{vpc_name}.json"
                with open(config_file, 'w') as f:
                    json.dump(vpc_config, f, indent=2)
                
                print(f"✓ Recovered VPC {vpc_name} with {len(subnets)} subnets")
            
            print(f"\n✓ Recovery complete! Recovered {len(vpcs)} VPCs")
            print("You can now use 'vpcctl show <vpc-name>' to view configurations")
        
        elif command == "fix-connectivity":
            # Fix connectivity issues for recovered VPCs
            vpc_name = sys.argv[2] if len(sys.argv) > 2 else None
            if not vpc_name:
                print("Usage: vpcctl fix-connectivity <vpc-name>")
                sys.exit(1)
            
            print(f"\nFixing connectivity for VPC: {vpc_name}")
            vpc = VPC.load(vpc_name)
            
            # Ensure bridge is up and has gateway IP
            gateway_ip = IPUtils.get_gateway_ip(vpc.cidr)
            print(f"Setting up bridge {vpc.bridge} with gateway {gateway_ip}")
            
            run_cmd(f"ip link set {vpc.bridge} up", ignore_errors=True)
            run_cmd(f"ip addr add {gateway_ip} dev {vpc.bridge}", ignore_exists=True)
            
            # Fix each subnet's connectivity
            for subnet_name, subnet_info in vpc.subnets.items():
                ns_name = subnet_info["namespace"]
                subnet_cidr = subnet_info["cidr"]
                subnet_ip = subnet_info["ip"]
                
                print(f"Fixing connectivity for subnet {subnet_name} ({ns_name})")
                
                # Create veth pair if it doesn't exist
                veth_host = f"veth-{ns_name}"
                veth_ns = f"veth-{ns_name}-ns"
                
                # Try to create veth pair (ignore if exists)
                run_cmd(f"ip link add {veth_host} type veth peer name {veth_ns}", ignore_exists=True)
                
                # Move one end to namespace
                run_cmd(f"ip link set {veth_ns} netns {ns_name}", ignore_errors=True)
                
                # Configure host side
                run_cmd(f"ip link set {veth_host} master {vpc.bridge}", ignore_exists=True)
                run_cmd(f"ip link set {veth_host} up", ignore_errors=True)
                
                # Configure namespace side
                run_cmd(f"ip netns exec {ns_name} ip link set {veth_ns} up", ignore_errors=True)
                run_cmd(f"ip netns exec {ns_name} ip addr add {subnet_ip} dev {veth_ns}", ignore_exists=True)
                run_cmd(f"ip netns exec {ns_name} ip route add default via {gateway_ip.split('/')[0]}", ignore_exists=True)
                
                print(f"✓ Fixed connectivity for {subnet_name}")
            
            # Add host routes to subnets
            for subnet_name, subnet_info in vpc.subnets.items():
                subnet_cidr = subnet_info["cidr"]
                run_cmd(f"ip route add {subnet_cidr} dev {vpc.bridge}", ignore_exists=True)
            
            print(f"✓ Connectivity fixed for VPC {vpc_name}")
            print("Web servers should now be accessible from host")
        
        else:
            Logger.error(f"Unknown command: {command}")
            sys.exit(1)
    
    except Exception as e:
        Logger.error(f"Operation failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()