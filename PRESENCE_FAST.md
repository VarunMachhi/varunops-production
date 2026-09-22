# PresenceFast 4.4.3

The live policy GET now also refreshes endpoint presence, so no extra polling request is needed.
Online is based on an agent contact within 30 seconds. The server only writes last_seen at most once every 10 seconds per PC.
The agent scheduled task is repaired with a startup trigger plus a 1-minute watchdog trigger and IgnoreNew behavior.
Self-update restarts via Task Scheduler rather than leaving an untracked PowerShell child.
