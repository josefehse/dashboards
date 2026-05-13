# Network Inspector

Azure network topology discovery, documentation, and analysis tool.

## Features

- **Discover** VNets, subnets, peerings, NSGs, UDRs, NAT Gateways, VPN Gateways, Public IPs, Private DNS Zones, ExpressRoute, Load Balancers, Application Gateways, and vWAN
- **Multi-subscription** support with auto-follow of cross-subscription peerings
- **Model** the network as a graph for analysis
- **Analyze** against CAF/WAF best practices (security, reliability, design, cost)
- **Export** topology as JSON snapshots, Markdown reports, HTML reports, and Mermaid diagrams
- **Query** connectivity and routing between subnets

## Installation

```bash
pip install -e .
```

## Prerequisites

- Python 3.10+
- Azure CLI installed and authenticated (`az login`)

## Running in Azure Cloud Shell

Azure Cloud Shell (Bash) comes with Python 3, Azure CLI, and a pre-authenticated identity, so you can run Network Inspector without any local setup.

1. Open [Azure Cloud Shell](https://shell.azure.com) and select **Bash**.

2. Clone the repository and navigate to the tool:

   ```bash
   git clone https://github.com/josefehse/dashboards.git
   cd dashboards/tools/netinspector
   ```

3. Install the package:

   ```bash
   pip install --user -e .
   ```

4. Ensure the `netinspect` CLI is on your PATH (Cloud Shell user-installed scripts path):

   ```bash
   export PATH="$HOME/.local/bin:$PATH"
   ```

5. Verify the installation:

   ```bash
   netinspect --help
   ```

6. Run a discovery (Cloud Shell inherits your portal identity—no `az login` needed):

   ```bash
   netinspect discover --subscription <subscription-id> --output topology.json --report report.html
   ```

7. Download results. In Cloud Shell click the **Upload/Download** button, choose **Download**, and enter the file path (e.g. `dashboards/tools/netinspector/topology.json`). Alternatively:

   ```bash
   download topology.json
   download report.html
   ```

> **Tip:** Cloud Shell sessions time out after 20 minutes of inactivity. For large environments, consider using `tmux` (pre-installed) to keep long-running discoveries alive.

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
# JSON snapshot + report in one command
netinspect discover -s <sub-id> --output topology.json --report report.md

# JSON snapshot + HTML topology report + DNS report
netinspect discover -s <sub-id> --output topology.json --report report.html --dns-report dns-report.html

# JSON snapshot only (default)
netinspect discover -s <sub-id> --output topology.json

# Generate topology report from existing JSON
netinspect report --input topology.json --output report.md

# Generate DNS report from existing JSON
netinspect dns-report --input topology.json --output dns-report.html
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
