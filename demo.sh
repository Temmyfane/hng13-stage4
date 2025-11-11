#!/bin/bash
# Complete demo script for VPC project

set -e

echo "=========================================="
echo "VPC Project - Complete Demo"
echo "=========================================="
echo ""

# Check if running as root
if [ "$EUID" -ne 0 ]; then 
    echo "Please run as root (sudo bash demo.sh)"
    exit 1
fi

# Make vpcctl executable
chmod +x vpcctl.py

echo "Step 1: Creating VPC 'dev' with CIDR 10.0.0.0/16"
./vpcctl.py create dev 10.0.0.0/16
sleep 1

echo ""
echo "Step 2: Adding public subnet (10.0.1.0/24)"
./vpcctl.py add-subnet dev public 10.0.1.0/24 public
sleep 1

echo ""
echo "Step 3: Adding private subnet (10.0.2.0/24)"
./vpcctl.py add-subnet dev private 10.0.2.0/24 private
sleep 1

echo ""
echo "Step 4: Enabling NAT gateway"
# Detect primary network interface
PRIMARY_IF=$(ip route | grep default | awk '{print $5}' | head -n1)
echo "Using interface: $PRIMARY_IF"
./vpcctl.py enable-nat dev "$PRIMARY_IF"
sleep 1

echo ""
echo "Step 5: Deploying web server in public subnet"
./vpcctl.py deploy-web dev public 8000
sleep 2

echo ""
echo "Step 6: Deploying web server in private subnet"
./vpcctl.py deploy-web dev private 8001
sleep 2

echo ""
echo "Step 7: Creating second VPC 'prod' for isolation test"
./vpcctl.py create prod 10.1.0.0/16
./vpcctl.py add-subnet prod prod-public 10.1.1.0/24 public
./vpcctl.py deploy-web prod prod-public 8002
sleep 2

echo ""
echo "Step 8: Showing VPC configuration"
./vpcctl.py show dev
./vpcctl.py show prod

echo ""
echo "=========================================="
echo "Testing Connectivity"
echo "=========================================="

# Test 1: Public subnet can reach internet
echo ""
echo "Test 1: Public subnet internet access"
ip netns exec dev-public ping -c 3 8.8.8.8 || echo "Internet access test (may fail in restricted environments)"

# Test 2: Inter-subnet communication
echo ""
echo "Test 2: Communication between subnets in same VPC"
ip netns exec dev-public ping -c 3 10.0.2.10 && echo "✓ Public can reach Private" || echo "✗ Public cannot reach Private"

# Test 3: Test web servers
echo ""
echo "Test 3: Testing web servers"
echo "Public subnet web server:"
ip netns exec dev-public curl -s http://10.0.1.10:8000 || echo "Web server not responding yet"

echo ""
echo "Private subnet web server:"
ip netns exec dev-private curl -s http://10.0.2.10:8001 || echo "Web server not responding yet"

# Test 4: VPC isolation
echo ""
echo "Test 4: VPC Isolation (should fail)"
ip netns exec dev-public ping -c 2 10.1.1.10 && echo "✗ VPCs NOT isolated!" || echo "✓ VPCs are properly isolated"

echo ""
echo "=========================================="
echo "Demo Complete!"
echo "=========================================="
echo ""
echo "Your VPCs are running. You can:"
echo "1. List VPCs: ./vpcctl.py list"
echo "2. Show details: ./vpcctl.py show dev"
echo "3. Access web servers from host:"
echo "   - curl http://10.0.1.10:8000"
echo "   - curl http://10.0.2.10:8001"
echo ""
echo "To clean up: sudo bash cleanup.sh"
echo ""
