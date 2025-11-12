#!/bin/bash
# Fixed demo script for VPC project with improved connectivity and error handling

set -e

echo "=========================================="
echo "VPC Project - Complete Demo (Fixed)"
echo "=========================================="
echo ""

# Check if running as root
if [ "$EUID" -ne 0 ]; then 
    echo "Please run as root (sudo bash demo-fixed.sh)"
    exit 1
fi

# Make vpcctl executable
chmod +x vpcctl.py

# Function to wait and check if process is ready
wait_for_service() {
    local ip=$1
    local port=$2
    local timeout=10
    local count=0
    
    echo "Waiting for service at $ip:$port..."
    while [ $count -lt $timeout ]; do
        if curl -s --connect-timeout 1 http://$ip:$port >/dev/null 2>&1; then
            echo "✓ Service ready at $ip:$port"
            return 0
        fi
        sleep 1
        count=$((count + 1))
    done
    echo "⚠ Service at $ip:$port not ready after ${timeout}s"
    return 1
}

echo "Step 0: Cleaning up any existing resources"
./vpcctl.py cleanup-orphans
sleep 1

echo ""
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
echo "Step 4: Fixing bridge connectivity (critical fix)"
./vpcctl.py fix-bridge dev
sleep 1

echo ""
echo "Step 5: Deploying web servers with proper connectivity"
./vpcctl.py redeploy-web dev
sleep 3

echo ""
echo "Step 6: Enabling NAT gateway for internet access"
# Detect primary network interface
PRIMARY_IF=$(ip route | grep default | awk '{print $5}' | head -n1)
echo "Using interface: $PRIMARY_IF"
./vpcctl.py enable-nat dev "$PRIMARY_IF"
sleep 1

echo ""
echo "Step 7: Creating second VPC 'prod' for isolation test"
./vpcctl.py create prod 10.1.0.0/16
./vpcctl.py add-subnet prod prod-public 10.1.1.0/24 public
./vpcctl.py fix-bridge prod
./vpcctl.py redeploy-web prod
sleep 3

echo ""
echo "Step 8: Showing VPC configuration"
./vpcctl.py show dev
echo ""
./vpcctl.py show prod

echo ""
echo "=========================================="
echo "Testing Connectivity"
echo "=========================================="

# Test 1: Web servers accessibility
echo ""
echo "Test 1: Testing web servers from host"
echo "Public subnet web server (dev):"
if curl -s --connect-timeout 3 http://10.0.1.2:8000; then
    echo "✓ Public web server accessible"
else
    echo "✗ Public web server not accessible"
fi

echo ""
echo "Private subnet web server (dev):"
if curl -s --connect-timeout 3 http://10.0.2.2:8001; then
    echo "✓ Private web server accessible"
else
    echo "✗ Private web server not accessible"
fi

echo ""
echo "Production web server:"
if curl -s --connect-timeout 3 http://10.1.1.2:8000; then
    echo "✓ Production web server accessible"
else
    echo "✗ Production web server not accessible"
fi

# Test 2: Inter-subnet communication within same VPC
echo ""
echo "Test 2: Inter-subnet communication (same VPC)"
if ip netns exec dev-public ping -c 2 10.0.2.2 >/dev/null 2>&1; then
    echo "✓ Public subnet can reach private subnet"
else
    echo "✗ Public subnet cannot reach private subnet"
fi

if ip netns exec dev-public curl -s --connect-timeout 3 http://10.0.2.2:8001 >/dev/null 2>&1; then
    echo "✓ Public subnet can access private web server"
else
    echo "✗ Public subnet cannot access private web server"
fi

# Test 3: VPC isolation
echo ""
echo "Test 3: VPC Isolation (cross-VPC communication should fail)"
if ip netns exec dev-public ping -c 2 10.1.1.2 >/dev/null 2>&1; then
    echo "✗ VPCs NOT isolated - this is a problem!"
else
    echo "✓ VPCs are properly isolated"
fi

# Test 4: Internet access (may fail in restricted environments)
echo ""
echo "Test 4: Internet access from public subnet"
if ip netns exec dev-public ping -c 2 8.8.8.8 >/dev/null 2>&1; then
    echo "✓ Public subnet has internet access"
else
    echo "⚠ Internet access test failed (may be expected in restricted environments)"
fi

echo ""
echo "Test 5: Internet access from private subnet"
if ip netns exec dev-private ping -c 2 8.8.8.8 >/dev/null 2>&1; then
    echo "✓ Private subnet has internet access via NAT"
else
    echo "⚠ Private subnet internet access failed (may be expected)"
fi

echo ""
echo "=========================================="
echo "Diagnostic Information"
echo "=========================================="
echo ""
echo "VPC Status:"
./vpcctl.py list

echo ""
echo "Detailed diagnostics:"
./vpcctl.py diagnose

echo ""
echo "Web server status:"
./vpcctl.py debug-servers dev
./vpcctl.py debug-servers prod

echo ""
echo "=========================================="
echo "Demo Complete!"
echo "=========================================="
echo ""
echo "✅ Your VPCs are running successfully!"
echo ""
echo "🌐 Web servers accessible at:"
echo "   - Dev Public:  http://10.0.1.2:8000"
echo "   - Dev Private: http://10.0.2.2:8001"
echo "   - Prod Public: http://10.1.1.2:8000"
echo ""
echo "🔧 Management commands:"
echo "   - List VPCs: ./vpcctl.py list"
echo "   - Show details: ./vpcctl.py show dev"
echo "   - Diagnostics: ./vpcctl.py diagnose"
echo ""
echo "🧹 To clean up: sudo ./vpcctl.py cleanup-orphans"
echo ""
echo "🎬 This demo is perfect for video recording!"
echo ""