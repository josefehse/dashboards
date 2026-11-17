# Microsoft Azure Network Adapter (MANA) Assessment Workbook

An Azure Monitor Workbook for identifying VMs that need MANA follow-up using Azure Resource Graph inventory. It combines VM size-family classification, OS/image metadata, and Accelerated Networking (AN) configuration. It is an assessment aid, not proof that a VM is running on MANA hardware or using the accelerated datapath.

## Files and deployment

- [manadashboard.json](./manadashboard.json): Azure Workbook definition.

1. In **Azure Portal > Monitor > Workbooks**, select **New**.
2. Open the **Advanced Editor** (`</>`) and replace its contents with the workbook JSON.
3. Select **Apply**, then **Save**.
4. Choose the scope and review **MANA Support Status**.

### Prerequisites

- Azure VMs and read access to each VM and every attached NIC. Missing NIC visibility produces incomplete evidence.
- Permission to create/save a workbook in the destination resource group.
- Guest access for the manual checks below. These checks are not executed by the workbook and do not require a Log Analytics workspace.

## Dashboard details

The table includes VM identity, size, MANA candidate status, OS/image details, Accelerated Networking state, and a link to the VM resource. It supports filtering and Excel export, with a 5,000-row display limit.

### Parameters and scope

- **Subscriptions** populates the resource-group and VM selectors.
- **Resource groups** and **Virtual machines** filter the status table.
- **Target region** is currently informational; it is not used by the status query and does not check regional availability.

**Scope limitation:** The main status query uses tenant scope, rather than the Subscription parameter. With resource groups and VMs set to **All**, it can include VMs from all accessible subscriptions. Selecting a resource group filters by its name, which may be shared across subscriptions. Select explicit VMs when an exact scope is required.

### How to interpret the results

| Field | Meaning |
|-------|---------|
| `MANACandidateStatus` | A static VM-family classification: **MANA candidate now**, **Timeline under review**, or **UNKNOWN**. It does not detect host hardware. |
| `MANAOSSupported` | A match against OS/image metadata patterns in the query, not an inspection of installed drivers or kernel capabilities. Only rows matching `TRUE` are displayed. |
| `AcceleratedNetworking` | **Enabled** if any NIC reports AN enabled; **Disabled** only when all expected NICs are visible and explicitly disabled; otherwise **UNKNOWN**. |
| `RequiresAction` | **TRUE** for a current MANA candidate with AN enabled or incomplete NIC evidence. **FALSE** means no action under this rule, not verified readiness. |

Current candidate families are Dv5/Dsv5/Ddv5/Ddsv5/Dlsv5/Dldsv5, Ev5/Esv5/Edv5/Edsv5, Dpsv6/Dpdsv6/Dplsv6/Dpldsv6, and Epsv6/Epdsv6.

Families marked **Timeline under review** are Dv4/Dsv4/Ddv4/Ddsv4, Ev4/Esv4/Edv4/Edsv4, Dv3/Dsv3/Ev3/Esv3, Bsv2, Dv2/Dsv2/Av2, F/Fs/Fsv2, G/GS, and Ls. Other sizes are **UNKNOWN**, not necessarily unsupported.

The OS patterns recognize specific Windows, Azure Linux/CBL-Mariner, AlmaLinux, Debian, Oracle Linux, Rocky Linux, RHEL, SUSE, and Ubuntu versions. These are static heuristics: missing metadata, custom images, backports, or newer releases can be missed. Excluded VMs are not assessed by this view; an empty table does not prove fleet readiness. Review the current Microsoft support documentation and the actual guest before making changes.

## Next steps: check the OS, host, and traffic

For each flagged VM, resolve **UNKNOWN** NIC state first by checking permissions and every attached NIC. Identify which NICs have AN enabled; do not assume that one enabled NIC means all NICs are accelerated. If AN is disabled on all NICs, the VM uses the synthetic path; this does not establish MANA compatibility. Assess guest readiness before any planned enablement.

Run the following checks **inside the target VM**, not on your workstation. Use an appropriately privileged shell if required. Missing commands or permission errors mean the check is incomplete, not that hardware or drivers are absent.

### 1. Linux: verify the actual OS and driver

```sh
uname -r
cat /etc/os-release
grep -E '/mana\.ko$' "/lib/modules/$(uname -r)/modules.builtin"
find "/lib/modules/$(uname -r)/kernel" -name 'mana*.ko*'
```

Look for `kernel/drivers/net/ethernet/microsoft/mana/mana.ko` in the built-in list or a corresponding module file, including compressed modules. No grep match alone is not a failure; check both outputs.

The Ethernet driver entered upstream Linux in 5.15; 6.2 added further RDMA/DPDK-related capabilities. Vendor kernels can backport support. Determine readiness from the distribution, kernel, actual driver availability, and current support guidance together, not a kernel-number-only pass/fail rule.

### 2. Check whether MANA hardware is presented

Linux:

```sh
lspci -nn -d 1414:00ba
```

Windows PowerShell:

```powershell
Get-PnpDevice -PresentOnly |
    Where-Object { $_.InstanceId -match '^PCI\\VEN_1414&DEV_00BA&' }
```

With AN enabled and a successful hardware check, PCI vendor/device `1414:00ba` identifies MANA. No matching device suggests current placement on different networking hardware, not automatically a compatibility failure. A VM-family candidate label does not guarantee current MANA host placement.

### 3. Verify driver binding and interface state

Linux:

```sh
lspci -nnk -d 1414:00ba
lsmod | grep -w mana
ip link
```

Confirm the MANA device is bound to the driver and its VF interface is initialized and associated with the synthetic interface. A built-in driver does not appear in `lsmod`; do not treat that alone as a failure. Interface names vary; Microsoft examples use synthetic `eth0` and a MANA VF such as `enP30832p0s0`.

Windows PowerShell:

```powershell
Get-NetAdapter |
    Format-Table Name, InterfaceDescription, Status, LinkSpeed
```

Look for **Microsoft Azure Network Adapter** with status **Up**, alongside the synthetic **Microsoft Hyper-V Network Adapter**. A MANA PCI device without a corresponding MANA adapter indicates missing or nonfunctional guest driver support. Check Device Manager and install/update the supported driver using Microsoft's instructions.

### 4. Verify real traffic through MANA

Capture counters, generate known traffic to another Azure VM using an approved workload/test, then capture counters again.

Linux (replace `eth0` with the relevant synthetic interface):

```sh
ip -s link
ethtool -S eth0 | grep -E '^[[:space:]]+vf'
```

Confirm increasing VF packet/byte counters on the interface associated with the MANA device. Synthetic-interface traffic alone is not proof of MANA use.

Windows PowerShell:

```powershell
Get-NetAdapter |
    Where-Object { $_.InterfaceDescription -like '*Microsoft Azure Network Adapter*' } |
    Get-NetAdapterStatistics
```

Confirm MANA packet/byte counters increase. An adapter that is merely present or Up does not prove workload traffic is using it. If counters remain unchanged during known traffic, investigate driver binding, interface association, and datapath use.

### Assessment and remediation

| Evidence | Interpretation / next step |
|----------|----------------------------|
| AN disabled on all NICs | Synthetic path; assess guest compatibility before planned AN enablement. |
| AN enabled, no MANA PCI device | Likely different host networking hardware. Assess OS/driver readiness independently; absence alone is not a failure. |
| AN enabled, MANA PCI device present, driver missing/nonfunctional | Compatibility/remediation candidate. Update the supported guest kernel/driver and recheck. |
| MANA driver bound and interface operational, traffic unverified | Continue with before/after VF traffic counters. |
| MANA counters increase during known traffic | Observed MANA datapath use for the tested NIC/workload at that time. |
| Permissions, tools, or metadata missing | Incomplete evidence; resolve the missing check before assigning a result. |

Record one assessment per VM with VM/SKU, actual OS/image/kernel, candidate status, AN per NIC, MANA PCI presence, driver availability/binding, interface state, traffic evidence, and the next action. For example, PCI present but driver missing is a remediation case; no PCI device with a supported guest is not itself a failure, and datapath use remains unverified. Revalidate after relevant guest updates or host-placement changes.

## References

- [MANA overview](https://learn.microsoft.com/en-us/azure/virtual-network/accelerated-networking-mana-overview)
- [Accelerated Networking support requirements](https://learn.microsoft.com/en-us/azure/virtual-network/accelerated-networking-overview)
- [Linux MANA checks and traffic validation](https://learn.microsoft.com/en-us/azure/virtual-network/accelerated-networking-mana-linux)
- [Windows MANA checks, driver installation, and traffic validation](https://learn.microsoft.com/en-us/azure/virtual-network/accelerated-networking-mana-windows)
