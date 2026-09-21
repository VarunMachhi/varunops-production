# Asset Inventory Field Mapping

The build was aligned to the uploaded `Asset_Inventory (2).xlsx` structure.

## Automatic where Windows exposes it

- Hostname
- Employee (server-side assignment)
- Designation (employee profile)
- Branch
- Device Type
- Status / Last Seen / Last Sync
- IP Address
- MAC Address
- OS / Windows build / architecture
- System Brand / System Model
- CPU / Processor ID / CPU Manufacturer / Cores / Threads / Clock Speed
- Motherboard / Motherboard Serial
- BIOS Serial
- RAM Total / RAM Modules
- Storage / disk serials
- Monitor manufacturer/model/serial/size/resolution/manufacture week-year when EDID exposes it
- Mouse / Keyboard device name/manufacturer/PNP ID when Windows exposes it
- Registered / Active

## Manual / override fields

These are provided because Windows often cannot reliably identify them:

- Asset Tag
- PIN / Inventory number
- Vendor
- Purchase Date
- Desk / physical location
- Monitor brand/model/serial/size override
- Mouse brand/model/serial
- Keyboard brand/model/serial
- UPS brand/model/serial
- Notes

The Admin Devices page exports a CSV using the corresponding asset-register columns.
