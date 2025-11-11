#!/bin/bash
# Cleanup script to remove all VPC resources

set -e

echo "=========================================="
echo "Cleaning up VPC resources"
echo "=========================================="

if [ "$EUID" -ne 0 ]; then 
    echo "Please run as root (sudo bash cleanup.sh)"
    exit 1
fi

# Delete all configured VPCs
echo ""
echo "Deleting VPCs..."
./vpcctl list

for vpc in $(ls ~/.vpcctl/*.json 2>/dev/null | xargs -n1 basename | sed 's/.json//'); do
    echo "Deleting VPC: $vpc"
    ./vpcctl delete "$vpc" || echo "Failed to delete $vpc"
done

# Clean up any remaining namespaces
echo ""
echo "Cleaning up any remaining namespaces..."
for ns in $(ip netns list | awk '{print $1}'); do
    if [[ $ns == dev-* ]] || [[ $ns == prod-* ]]; then
        echo "Removing namespace: $ns"
        ip netns del "$ns" 2>/dev/null || true
    fi
done

# Clean up bridges
echo ""
echo "Cleaning up bridges..."
for br in $(ip link show type bridge | grep 'vpc-' | awk '{print $2}' | sed 's/:$//'); do
    echo "Removing bridge: $br"
    ip link del "$br" 2>/dev/null || true
done

# Flush iptables NAT rules (be careful in production!)
echo ""
echo "Flushing NAT rules..."
iptables -t nat -F POSTROUTING 2>/dev/null || true
iptables -F FORWARD 2>/dev/null || true

echo ""
echo "=========================================="
echo "Cleanup complete!"
echo "=========================================="
echo ""
echo "All VPC resources have been removed."
echo ""