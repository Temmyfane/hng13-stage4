#!/bin/bash
# Comprehensive VPC testing script

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo "=========================================="
echo "VPC Project - Comprehensive Tests"
echo "=========================================="
echo ""

# Check if running as root
if [ "$EUID" -ne 0 ]; then 
    echo -e "${RED}Please run as root (sudo bash test-vpc.sh)${NC}"
    exit 1
fi

PASSED=0
FAILED=0

test_result() {
    if [ $1 -eq 0 ]; then
        echo -e "${GREEN}✓ PASSED${NC}: $2"
        ((PASSED++))
    else
        echo -e "${RED}✗ FAILED${NC}: $2"
        ((FAILED++))
    fi
    echo ""
}

# Setup test environment
echo "Setting up test environment..."
./vpcctl.py create test-vpc 10.0.0.0/16
./vpcctl.py add-subnet test-vpc public 10.0.1.0/24 public
./vpcctl.py add-subnet test-vpc private 10.0.2.0/24 private

# Detect primary network interface
PRIMARY_IF=$(ip route | grep default | awk '{print $5}' | head -n1)
./vpcctl enable-nat test-vpc "$PRIMARY_IF"

sleep 2

echo ""
echo "=========================================="
echo "Running Tests"
echo "=========================================="
echo ""

# Test 1: Bridge exists
echo "Test 1: VPC bridge created"
ip link show vpc-test-vpc > /dev/null 2>&1
test_result $? "VPC bridge (vpc-test-vpc) exists"

# Test 2: Namespaces exist
echo "Test 2: Network namespaces created"
ip netns list | grep -q "test-vpc-public"
result1=$?
ip netns list | grep -q "test-vpc-private"
result2=$?
[ $result1 -eq 0 ] && [ $result2 -eq 0 ]
test_result $? "Both namespaces (public and private) exist"

# Test 3: IP addressing
echo "Test 3: IP addresses assigned correctly"
ip netns exec test-vpc-public ip addr show eth0 | grep -q "10.0.1.10"
test_result $? "Public subnet has correct IP (10.0.1.10)"

# Test 4: Loopback in namespace
echo "Test 4: Loopback interface is up"
ip netns exec test-vpc-public ping -c 1 127.0.0.1 > /dev/null 2>&1
test_result $? "Loopback interface works in namespace"

# Test 5: Bridge connectivity
echo "Test 5: Namespace can reach bridge"
ip netns exec test-vpc-public ping -c 2 10.0.0.1 > /dev/null 2>&1
test_result $? "Public subnet can reach bridge gateway"

# Test 6: Inter-subnet communication
echo "Test 6: Inter-subnet communication"
ip netns exec test-vpc-public ping -c 2 10.0.2.10 > /dev/null 2>&1
test_result $? "Public subnet can communicate with private subnet"

# Test 7: Internet access (public subnet)
echo "Test 7: Public subnet internet access"
ip netns exec test-vpc-public ping -c 2 8.8.8.8 > /dev/null 2>&1
result=$?
if [ $result -eq 0 ]; then
    test_result 0 "Public subnet has internet access (NAT working)"
else
    echo -e "${YELLOW}⚠ SKIPPED${NC}: Internet access test (may fail in restricted environments)"
    echo ""
fi

# Test 8: Deploy web server
echo "Test 8: Web server deployment"
./vpcctl.py deploy-web test-vpc public 8000
sleep 2
ip netns exec test-vpc-public curl -s http://10.0.1.10:8000 | grep -q "Hello from public"
test_result $? "Web server deployed and accessible"

# Test 9: Create second VPC for isolation test
echo "Test 9: VPC isolation"
./vpcctl.py create test-vpc2 10.1.0.0/16
./vpcctl.py add-subnet test-vpc2 public2 10.1.1.0/24 public
sleep 1
ip netns exec test-vpc-public ping -c 1 -W 1 10.1.1.10 > /dev/null 2>&1
if [ $? -ne 0 ]; then
    test_result 0 "VPCs are properly isolated (cannot communicate)"
else
    test_result 1 "VPCs are NOT isolated (this is a problem)"
fi

# Test 10: Routing table
echo "Test 10: Routing table configuration"
ip netns exec test-vpc-public ip route | grep -q "default via 10.0.0.1"
test_result $? "Default route configured correctly"

# Test 11: VPC configuration saved
echo "Test 11: VPC configuration persistence"
[ -f ~/.vpcctl.py/test-vpc.json ]
test_result $? "VPC configuration file saved"

# Test 12: Firewall policy application
echo "Test 12: Firewall policy application"
cat > /tmp/test-policy.json << 'EOF'
{
  "subnet": "10.0.1.0/24",
  "ingress": [
    {"port": 9999, "protocol": "tcp", "action": "deny"}
  ]
}
EOF
./vpcctl.py apply-policy test-vpc /tmp/test-policy.json
ip netns exec test-vpc-public iptables -L INPUT -n | grep -q "9999"
test_result $? "Firewall policy applied correctly"

echo ""
echo "=========================================="
echo "Test Summary"
echo "=========================================="
echo -e "${GREEN}Passed: $PASSED${NC}"
echo -e "${RED}Failed: $FAILED${NC}"
echo ""

# Cleanup
echo "Cleaning up test environment..."
./vpcctl.py delete test-vpc
./vpcctl.py delete test-vpc2 2>/dev/null || true
rm -f /tmp/test-policy.json

if [ $FAILED -eq 0 ]; then
    echo -e "${GREEN}All tests passed! ✓${NC}"
    exit 0
else
    echo -e "${RED}Some tests failed. Please review.${NC}"
    exit 1
fi