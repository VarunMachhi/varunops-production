VarunOps Agent RAM64 Hotfix 4.2.1

Use this on an EXISTING paired PC that shows Int32 overflow errors such as:
Cannot convert value "10xxxxxxxxx" to type "System.Int32".

Steps:
1. Extract this ZIP fully.
2. Right-click UPDATE_EXISTING_AGENT.bat and Run as administrator.
3. Do not delete the existing VarunOps employee/device registration.
4. The script preserves C:\ProgramData\VarunOps\agent.json and its device key.
5. Success is shown only after the cloud accepts fresh hardware + telemetry.
6. Refresh the employee portal after 10-20 seconds.

If it fails, run CHECK_AGENT.bat as Administrator and inspect:
C:\ProgramData\VarunOps\agent.log
