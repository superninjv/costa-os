#!/bin/bash
# Costa OS — Default firewall rules
# Desktop-appropriate: deny unsolicited inbound, allow all outbound
# Run once during first-boot, idempotent (safe to re-run)

set -e

ufw --force reset

# Default policies
ufw default deny incoming
ufw default allow outgoing

# mDNS/Avahi — local network service discovery (printers, Chromecast, etc.)
ufw allow in 5353/udp comment "mDNS/Avahi"

# KDE Connect — local device integration
ufw allow in 1714:1764/tcp comment "KDE Connect TCP"
ufw allow in 1714:1764/udp comment "KDE Connect UDP"

# Ollama — local AI server (localhost + Docker bridge only)
ufw allow in from 127.0.0.0/8 to any port 11434 comment "Ollama local"
ufw allow in from 172.16.0.0/12 to any port 11434 comment "Ollama Docker"

# Firecrawl — local web scraping API (localhost only, Docker binds to 127.0.0.1)
ufw allow in from 127.0.0.0/8 to any port 3002 comment "Firecrawl local"

# Enable
ufw --force enable

echo "Firewall configured: deny incoming, allow outgoing"
