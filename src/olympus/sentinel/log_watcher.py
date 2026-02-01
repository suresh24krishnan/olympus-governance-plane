import time
import os
from olympus.sentinel.health_monitor import SentinelHealthMonitor

class SentinelLogWatcher:
    def __init__(self, log_path="system.log"):
        self.log_path = log_path
        self.monitor = SentinelHealthMonitor()
        print(f"🕵️ Sentinel Tier 0 Monitor Active... Watching {log_path}")

    def start_polling(self):
        # Move to the end of the file
        file = open(self.log_path, "r")
        file.seek(0, os.SEEK_END)

        while True:
            line = file.readline()
            if not line:
                time.sleep(1) # Wait for new logs
                continue
            
            if "ERROR" in line or "CRITICAL" in line:
                print(f"🚨 ALERT DETECTED: {line.strip()}")
                # Trigger the AI-driven Jira escalation
                self.monitor.run_security_audit(f"System Error Detected: {line}. Explain this error and suggest a fix.")

if __name__ == "__main__":
    watcher = SentinelLogWatcher()
    watcher.start_polling()