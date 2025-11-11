# VPC Control Tool (vpcctl)

A Linux-based Virtual Private Cloud (VPC) implementation using network namespaces, bridges, and iptables to simulate AWS VPC functionality.

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────┐
│              Physical Linux Host                 │
│                                                  │
│  ┌───────────────────────────────────────────┐ │
│  │         VPC (Linux Bridge)                 │ │
│  │         vpc-dev: 10.0.0.1/16              │ │
│  └────────┬──────────────────┬────────────────┘ │
│           │                  │                   │
│      ┌────▼──────┐      ┌────▼──────┐          │
│      │  Public    │      │  Private   │          │
│      │  Subnet    │      │  Subnet    │          │
│      │ (namespace)│      │ (namespace)│          │
│      │10.0.1.0/24 │      │10.0.2.0/24 │          │
│      │    NAT→    │      │ (isolated) │          │
│      └────────────┘      └────────────┘          │
│           │                                       │
│           └──────→ Internet (via NAT)            │
└─────────────────────────────────────────────────┘
```

## 📋 Prerequisites

- Linux system (Ubuntu 20.04+ recommended)
- Root/sudo access
- Python 3.6+
- Required tools: `ip`, `iptables`, `bridge`

```bash
# Install dependencies (Ubuntu/Debian)
sudo apt-get update
sudo apt-get install -y iproute2 iptables bridge-utils python3
```

## 🚀 Quick Start

### 1. Setup

```bash
# Clone the repository
git clone <your-repo-url>
cd vpc-project

# Make scripts executable
chmod +x vpcctl demo.sh cleanup.sh
```

### 2. Run Complete Demo

```bash
# Run the full demo (creates VPCs, subnets, web servers, tests)
sudo ./demo.sh
```

### 3. Manual Usage

#### Create a VPC

```bash
sudo ./vpcctl create dev 10.0.0.0/16
```

#### Add Subnets

```bash
# Public subnet (with internet access)
sudo ./vpcctl add-subnet dev public 10.0.1.0/24 public

# Private subnet (isolated)
sudo ./vpcctl add-subnet dev private 10.0.2.0/24 private
```

#### Enable NAT Gateway

```bash
# Enable internet access for public subnets
sudo ./vpcctl enable-nat dev eth0
```

#### Deploy Web Server

```bash
# Deploy in public subnet
sudo ./vpcctl deploy-web dev public 8000

# Deploy in private subnet
sudo ./vpcctl deploy-web dev private 8001
```

#### Apply Firewall Rules

```bash
# Create policy file (firewall-policy.json)
sudo ./vpcctl apply-policy dev firewall-policy.json
```

#### Show VPC Details

```bash
sudo ./vpcctl show dev
```

#### List All VPCs

```bash
sudo ./vpcctl list
```

#### Delete VPC

```bash
sudo ./vpcctl delete dev
```

## 🧪 Testing & Validation

### Test 1: Inter-Subnet Communication

```bash
# From public subnet, ping private subnet
sudo ip netns exec dev-public ping -c 3 10.0.2.10
```

### Test 2: Internet Access (Public Subnet)

```bash
# Public subnet should reach internet
sudo ip netns exec dev-public ping -c 3 8.8.8.8

# Private subnet should NOT reach internet
sudo ip netns exec dev-private ping -c 3 8.8.8.8
```

### Test 3: Web Server Access

```bash
# Access public subnet web server
curl http://10.0.1.10:8000

# Access from within namespace
sudo ip netns exec dev-public curl http://10.0.1.10:8000
```

### Test 4: VPC Isolation

```bash
# Create second VPC
sudo ./vpcctl create prod 10.1.0.0/16
sudo ./vpcctl add-subnet prod prod-public 10.1.1.0/24 public

# Try to reach from dev to prod (should fail)
sudo ip netns exec dev-public ping -c 2 10.1.1.10
```

### Test 5: VPC Peering (Advanced)

```bash
# To implement peering, modify vpcctl to add:
sudo ./vpcctl peer dev prod

# After peering, cross-VPC communication works
sudo ip netns exec dev-public ping -c 2 10.1.1.10
```

## 📁 Project Structure

```
vpc-project/
├── vpcctl                    # Main CLI tool (Python)
├── demo.sh                   # Full demonstration script
├── cleanup.sh                # Resource cleanup script
├── firewall-policy.json      # Example firewall policy
├── README.md                 # This file
└── ~/.vpcctl/                # VPC configurations (auto-created)
    ├── dev.json
    └── prod.json
```

## 🔧 How It Works

### Network Namespaces
Each subnet is a **network namespace** - an isolated network stack with its own interfaces, routing table, and firewall rules.

### Linux Bridge
The VPC uses a **Linux bridge** that acts as a virtual switch/router, connecting all subnets within the VPC.

### Veth Pairs
**Virtual ethernet pairs** connect namespaces to the bridge, like virtual cables.

### NAT Gateway
Uses **iptables MASQUERADE** to provide internet access to public subnets while keeping private subnets isolated.

### Routing
Each namespace has a default route through the bridge, and the bridge forwards packets between subnets.

## 🎯 Key Features Demonstrated

✅ **VPC Creation** - Isolated virtual networks with custom CIDR blocks  
✅ **Multiple Subnets** - Public and private subnets with different access levels  
✅ **Inter-Subnet Routing** - Subnets within same VPC can communicate  
✅ **NAT Gateway** - Public subnets have internet access  
✅ **VPC Isolation** - Different VPCs cannot communicate by default  
✅ **Firewall Rules** - JSON-based security policies using iptables  
✅ **Web Server Deployment** - Simple HTTP servers for testing  
✅ **Clean Teardown** - Proper resource cleanup

## 🧹 Cleanup

```bash
# Remove all VPCs and resources
sudo ./cleanup.sh

# Or delete specific VPC
sudo ./vpcctl delete dev
```

## 📊 Expected Test Results

| Test | Expected Result |
|------|----------------|
| Create VPC | Bridge and routing configured |
| Add Subnet | Namespace created, veth connected |
| Inter-subnet ping | Success within same VPC |
| Public subnet internet | Success (with NAT) |
| Private subnet internet | Failure (blocked) |
| VPC isolation | Cannot reach other VPCs |
| Web server deployment | HTTP server accessible |
| Firewall rules | Traffic filtered as configured |
| Cleanup | All resources removed |

## 🐛 Troubleshooting

### Issue: "Operation not permitted"
**Solution:** Run with sudo/root access

### Issue: "Cannot find device"
**Solution:** Check if bridge/namespace exists: `ip link show` or `ip netns list`

### Issue: Internet access not working
**Solution:** 
- Check IP forwarding: `sysctl net.ipv4.ip_forward`
- Verify NAT rules: `iptables -t nat -L -n -v`
- Confirm correct interface: `ip route | grep default`

### Issue: Web server not responding
**Solution:** 
- Check if process running: `ip netns exec dev-public ps aux | grep python`
- View logs: `ip netns exec dev-public cat /tmp/webserver.log`

## 📝 Firewall Policy Example

```json
{
  "subnet": "10.0.1.0/24",
  "ingress": [
    {"port": 80, "protocol": "tcp", "action": "allow"},
    {"port": 443, "protocol": "tcp", "action": "allow"},
    {"port": 22, "protocol": "tcp", "action": "deny"}
  ]
}
```

## 🎓 Learning Outcomes

- Understanding Linux networking primitives
- Network isolation and segmentation
- Routing and NAT configuration
- Firewall rule management
- Infrastructure automation
- Cloud VPC concepts (AWS/Azure/GCP)

## 📚 Resources

- [Linux Network Namespaces](https://man7.org/linux/man-pages/man8/ip-netns.8.html)
- [Linux Bridge](https://wiki.linuxfoundation.org/networking/bridge)
- [iptables Tutorial](https://www.netfilter.org/documentation/HOWTO/packet-filtering-HOWTO.html)
- [AWS VPC Documentation](https://docs.aws.amazon.com/vpc/)

## 📄 License

MIT License - Feel free to use for learning and projects!

## 🤝 Contributing

This is a learning project. Feel free to enhance and share improvements!

---

**Created for DevOps Intern Stage 4 Task**