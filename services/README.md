# agmem Service Installation Guide

## macOS (launchd)

### Install

```bash
# Copy plist to LaunchAgents
cp services/com.agmem.daemon.plist ~/Library/LaunchAgents/

# Edit with your username
sed -i '' "s/YOUR_USERNAME/$(whoami)/g" ~/Library/LaunchAgents/com.agmem.daemon.plist

# Create log directory
sudo mkdir -p /usr/local/var/log/agmem
sudo chown $(whoami) /usr/local/var/log/agmem

# Load and start
launchctl load ~/Library/LaunchAgents/com.agmem.daemon.plist
```

### Manage

```bash
# Check status
launchctl list | grep agmem

# Stop
launchctl unload ~/Library/LaunchAgents/com.agmem.daemon.plist

# View logs
tail -f /usr/local/var/log/agmem/daemon.log
```

---

## Linux (systemd)

### Install

```bash
# Copy service file
sudo cp services/agmem-daemon@.service /etc/systemd/system/

# Reload systemd
sudo systemctl daemon-reload

# Enable and start for current user
sudo systemctl enable --now agmem-daemon@$USER
```

### Manage

```bash
# Check status
systemctl status agmem-daemon@$USER

# View logs
journalctl -u agmem-daemon@$USER -f

# Stop
sudo systemctl stop agmem-daemon@$USER
```

---

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `AGMEM_REPO_PATH` | `~/.agmem` | Repository path |
| `AGMEM_LOG_LEVEL` | `info` | Logging level |
| `AGMEM_WATCH_INTERVAL` | `1.0` | File watch interval (seconds) |
| `AGMEM_AUTO_COMMIT` | `true` | Enable auto-commit |
