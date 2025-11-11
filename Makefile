.PHONY: help install demo test clean check-root

# Colors for output
GREEN := \033[0;32m
YELLOW := \033[1;33m
RED := \033[0;31m
NC := \033[0m # No Color

help:
	@echo "=========================================="
	@echo "VPC Project - Available Commands"
	@echo "=========================================="
	@echo ""
	@echo "  make install    - Install dependencies"
	@echo "  make demo       - Run full demonstration"
	@echo "  make test       - Run comprehensive tests"
	@echo "  make clean      - Clean up all VPC resources"
	@echo "  make check      - Check prerequisites"
	@echo ""
	@echo "Manual VPC commands:"
	@echo "  sudo ./vpcctl create <name> <cidr>"
	@echo "  sudo ./vpcctl add-subnet <vpc> <name> <cidr> <type>"
	@echo "  sudo ./vpcctl enable-nat <vpc> [interface]"
	@echo "  sudo ./vpcctl deploy-web <vpc> <subnet> [port]"
	@echo "  sudo ./vpcctl show <vpc>"
	@echo "  sudo ./vpcctl delete <vpc>"
	@echo ""

check-root:
	@if [ "$$(id -u)" -ne 0 ]; then \
		echo "$(RED)Error: This command requires root privileges$(NC)"; \
		echo "Please run: sudo make <command>"; \
		exit 1; \
	fi

check:
	@echo "Checking prerequisites..."
	@echo ""
	@command -v python3 >/dev/null 2>&1 || { echo "$(RED)✗ Python3 not found$(NC)"; exit 1; }
	@echo "$(GREEN)✓ Python3 installed$(NC)"
	@command -v ip >/dev/null 2>&1 || { echo "$(RED)✗ iproute2 not found$(NC)"; exit 1; }
	@echo "$(GREEN)✓ iproute2 installed$(NC)"
	@command -v iptables >/dev/null 2>&1 || { echo "$(RED)✗ iptables not found$(NC)"; exit 1; }
	@echo "$(GREEN)✓ iptables installed$(NC)"
	@if [ "$$(id -u)" -ne 0 ]; then \
		echo "$(YELLOW)⚠ Not running as root (sudo make check)$(NC)"; \
	else \
		echo "$(GREEN)✓ Running with root privileges$(NC)"; \
	fi
	@echo ""
	@echo "$(GREEN)All prerequisites satisfied!$(NC)"

install:
	@echo "Installing dependencies..."
	apt-get update
	apt-get install -y iproute2 iptables bridge-utils python3
	chmod +x vpcctl demo.sh cleanup.sh test-vpc.sh
	@echo ""
	@echo "$(GREEN)Installation complete!$(NC)"
	@echo "Run 'sudo make demo' to see it in action"

demo: check-root
	@echo "$(GREEN)Starting VPC demonstration...$(NC)"
	@echo ""
	./demo.sh
	@echo ""
	@echo "$(GREEN)Demo complete!$(NC)"
	@echo "VPCs are still running. Use 'sudo make clean' to remove them."

test: check-root
	@echo "$(GREEN)Running comprehensive tests...$(NC)"
	@echo ""
	./test-vpc.sh

clean: check-root
	@echo "$(YELLOW)Cleaning up VPC resources...$(NC)"
	@echo ""
	./cleanup.sh
	@echo ""
	@echo "$(GREEN)Cleanup complete!$(NC)"

# Quick examples
example-create: check-root
	@echo "Creating example VPC..."
	./vpcctl create example 10.0.0.0/16
	./vpcctl add-subnet example public 10.0.1.0/24 public
	./vpcctl add-subnet example private 10.0.2.0/24 private
	./vpcctl show example

example-delete: check-root
	@echo "Deleting example VPC..."
	./vpcctl delete example

# Development helpers
lint:
	@command -v pylint >/dev/null 2>&1 && pylint vpcctl || echo "Install pylint for code checking"

format:
	@command -v black >/dev/null 2>&1 && black vpcctl || echo "Install black for code formatting"

# Show current VPCs
status:
	@echo "Current VPCs:"
	@if [ -d ~/.vpcctl ] && [ "$$(ls -A ~/.vpcctl 2>/dev/null)" ]; then \
		ls ~/.vpcctl/*.json 2>/dev/null | xargs -n1 basename | sed 's/.json//' | sed 's/^/  - /'; \
	else \
		echo "  No VPCs configured"; \
	fi
	@echo ""
	@echo "Active namespaces:"
	@ip netns list 2>/dev/null | grep -E "(dev-|prod-|test-)" || echo "  None"
	@echo ""
	@echo "Active bridges:"
	@ip link show type bridge 2>/dev/null | grep vpc- | awk '{print "  - " $$2}' | sed 's/:$$//' || echo "  None"