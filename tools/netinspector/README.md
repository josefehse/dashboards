# Network Inspector

Azure network topology discovery, documentation, and analysis tool.

## Features

- **Discover** VNets, subnets, peerings, NSGs, UDRs, NAT Gateways, VPN Gateways, Public IPs, Private DNS Zones, ExpressRoute, Load Balancers, Application Gateways, and vWAN
- **Multi-subscription** support with auto-follow of cross-subscription peerings
- **Model** the network as a graph for analysis
- **Analyze** against CAF/WAF best practices (security, reliability, design, cost)
- **Export** topology as JSON snapshots, Markdown reports, and Mermaid diagrams
- **Query** connectivity and routing between subnets

## Installation

```bash
pip install -e .
```

## Prerequisites

- Python 3.10+
- Azure CLI installed and authenticated (`az login`)

## Usage

### Discover full subscription topology

```bash
# Single subscription
netinspect discover --subscription <subscription-id>

# Multiple subscriptions (comma-separated)
netinspect discover --subscription <sub-id-1>,<sub-id-2>

# Start from a specific VNet
netinspect discover --subscription <sub-id> --vnet <vnet-name> --resource-group <rg-name>

# Disable auto-follow of cross-subscription peerings
netinspect discover --subscription <sub-id> --no-follow-peerings
```

### Export options

```bash
# JSON snapshot + Markdown report in one command
netinspect discover -s <sub-id> --output topology.json --report report.md

# JSON snapshot only (default)
netinspect discover -s <sub-id> --output topology.json

# Generate report from existing JSON
netinspect report --input topology.json --output report.md
```

### Analysis

```bash
# Run CAF/WAF analysis on existing topology
netinspect analyze --input topology.json

# Filter by category or severity
netinspect analyze -i topology.json --category security --severity critical
```

### Connectivity queries

```bash
# Check reachability between subnets
netinspect query --from <subnet-name> --to <ip-or-subnet>
```

### Show topology summary

```bash
netinspect show --input topology.json
```

## Roadmap

- [x] Phase 1: Core discovery (VNets, peerings, UDRs, NSGs)
- [x] Phase 2: Routing & connectivity analysis, NAT/VPN Gateways
- [x] Phase 3: ExpressRoute, Local Gateways, BGP
- [x] Phase 4: vWAN support
- [x] CAF/WAF analysis engine
- [x] Load Balancers & Application Gateways
- [x] Multi-subscription discovery with auto-follow
- [ ] Phase 5: What-if simulation
