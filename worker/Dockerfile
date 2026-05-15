# Vigile — Worker Node
# Multi-stage build: compile Go, then minimal runtime
#
# Simulation mode: mock scripts provide systemctl/journalctl for testing
# inside containers where these tools are not available.

# ── Stage 1: Build ──────────────────────────────────────────────────────
FROM golang:1.23-alpine AS builder

WORKDIR /build
COPY go.mod .
COPY *.go ./
RUN go build -o vigile-worker .

# ── Stage 2: Runtime ────────────────────────────────────────────────────
FROM alpine:3.20

RUN apk add --no-cache ca-certificates tzdata docker-cli util-linux

# ── Simulation layer: mock system commands ─────────────────────────────
# These scripts simulate systemd/journalctl so the Worker can be tested
# inside a container where these tools don't exist.

RUN mkdir -p /usr/local/vigile-sim

# mock systemctl — simulates systemd service management
RUN cat > /usr/local/bin/systemctl << 'SYSCTL'
#!/bin/sh
if [ "$1" = "list-units" ] && [ "$2" = "--type=service" ]; then
  cat /usr/local/vigile-sim/services.txt
elif [ "$1" = "is-active" ]; then
  grep -q "^${2} " /usr/local/vigile-sim/services.txt && echo "active" || echo "inactive"
elif [ "$1" = "is-enabled" ]; then
  grep -q "^${2} " /usr/local/vigile-sim/services.txt && echo "enabled" || echo "disabled"
elif [ "$1" = "restart" ]; then
  echo "Service ${2} restarted"
  exit 0
else
  echo "sim-systemctl: unknown command $*" >&2
  exit 1
fi
SYSCTL
RUN chmod +x /usr/local/bin/systemctl

# mock journalctl — simulates systemd journal log reading
RUN cat > /usr/local/bin/journalctl << 'JCTL'
#!/bin/sh
lines=50
service=""
while [ $# -gt 0 ]; do
  case "$1" in
    -u) service="$2"; shift 2 ;;
    -n) lines="$2"; shift 2 ;;
    --no-pager|--output|short) shift ;;
    *) shift ;;
  esac
done
if [ -f "/usr/local/vigile-sim/logs/${service}.log" ]; then
  tail -n "$lines" "/usr/local/vigile-sim/logs/${service}.log"
elif [ "$service" != "" ]; then
  echo "-- No entries --"
else
  tail -n "$lines" /var/log/syslog 2>/dev/null || echo "-- No entries --"
fi
JCTL
RUN chmod +x /usr/local/bin/journalctl

# ── Simulation data: realistic fixtures ────────────────────────────────

# Services list (matching a typical Linux server)
RUN cat > /usr/local/vigile-sim/services.txt << 'SVC'
  apparmor.service            loaded active exited  Load AppArmor profiles
  console-setup.service       loaded active exited  Set console font and keymap
  containerd.service          loaded active running containerd container runtime
  cron.service                loaded active running Regular background program processing daemon
  dbus.service                loaded active running D-Bus System Message Bus
  docker.service              loaded active running Docker Application Container Engine
  fail2ban.service            loaded active running Fail2Ban Service
  netdata.service             loaded active running Netdata, X-Ray Vision for your infrastructure!
  networking.service          loaded active exited  Raise network interfaces
  nginx.service               loaded active running Nginx Web Server
  ntpd.service                loaded active running NTP daemon
  postgresql.service          loaded active running PostgreSQL database server
  redis.service               loaded active running Redis key-value store
  rsyslog.service             loaded active running System Logging Service
  smartmontools.service       loaded active running S.M.A.R.T. monitoring daemon
  smbd.service                loaded active running Samba SMB Daemon
  ssh.service                 loaded active running OpenSSH Daemon
  systemd-journald.service    loaded active running Journal Service
  ufw.service                 loaded active exited  Uncomplicated firewall
  vigile-worker.service       loaded active running Vigile Fleet Manager Worker
SVC

# Log fixtures
RUN mkdir -p /usr/local/vigile-sim/logs
RUN cat > /usr/local/vigile-sim/logs/ssh.service.log << 'LOG'
May 15 08:15:01 server sshd[1234]: Accepted publickey for admin from 192.168.1.100 port 54123 ssh2: ED25519 SHA256:abc123
May 15 08:20:35 server sshd[1235]: Connection closed by authenticating user admin 192.168.1.100 port 54123
May 15 08:45:12 server sshd[1240]: Failed password for invalid user root from 10.0.0.50 port 39821 ssh2
May 15 09:00:00 server sshd[1250]: Accepted publickey for flavio from 81.49.190.197 port 65217 ssh2: ED25519 SHA256:xyz789
May 15 09:00:00 server sshd[1250]: pam_unix(sshd:session): session opened for user flavio(uid=1000) by flavio(uid=0)
May 15 09:15:22 server sshd[1260]: Received disconnect from 10.0.0.50 port 39821: 11: Bye Bye
May 15 09:30:45 server sshd[1270]: Server listening on 0.0.0.0 port 22.
May 15 09:45:10 server sshd[1280]: Connection closed by invalid user admin 203.0.113.42 port 51234
May 15 10:00:00 server sshd[1290]: Accepted publickey for deploy from 192.168.1.200 port 44123 ssh2: ED25519 SHA256:def456
May 15 10:05:30 server sshd[1295]: subsystem request for sftp by user deploy
LOG

RUN cat > /usr/local/vigile-sim/logs/nginx.service.log << 'LOG'
May 15 08:10:01 server nginx[2345]: Starting nginx
May 15 08:10:01 server nginx[2346]: nginx: using the epoll event loop
May 15 08:10:01 server nginx[2346]: nginx: listening on 0.0.0.0:80
May 15 08:10:01 server nginx[2346]: nginx: listening on 0.0.0.0:443
May 15 09:00:00 server nginx[2346]: 192.168.1.100 - - [15/May/2026:09:00:00 +0000] "GET / HTTP/1.1" 200 1234 "-" "curl/8.14"
May 15 09:15:30 server nginx[2346]: 81.49.190.197 - - [15/May/2026:09:15:30 +0000] "GET /api/health HTTP/1.1" 200 45 "-" "python-requests"
May 15 09:30:00 server nginx[2346]: 10.0.0.50 - - [15/May/2026:09:30:00 +0000] "POST /wp-login.php HTTP/1.1" 403 234 "-" "python-requests"
May 15 09:45:00 server nginx[2346]: 203.0.113.42 - - [15/May/2026:09:45:00 +0000] "GET /.env HTTP/1.1" 404 162 "-" "Mozilla/5.0"
LOG

RUN cat > /usr/local/vigile-sim/logs/postgresql.service.log << 'LOG'
May 15 08:10:05 server postgres[3456]: LOG:  starting PostgreSQL 16.2
May 15 08:10:05 server postgres[3457]: LOG:  database system was shut down at 2026-05-14 23:59:59 UTC
May 15 08:10:05 server postgres[3457]: LOG:  database system is ready to accept connections
May 15 08:10:05 server postgres[3458]: LOG:  autovacuum launcher started
May 15 09:00:00 server postgres[3458]: LOG:  checkpoint starting: time
May 15 09:00:05 server postgres[3458]: LOG:  checkpoint complete: wrote 42 buffers
May 15 09:15:00 server postgres[3458]: LOG:  duration: 15.432 ms  statement: SELECT * FROM users WHERE last_login > now() - interval '24h'
LOG

# Realistic syslog
RUN cat > /var/log/syslog << 'LOG'
May 15 08:00:00 server kernel: [    0.000000] Linux version 6.8.0-45-generic
May 15 08:00:01 server kernel: [    0.123456] CPU: Intel(R) Xeon(R) E-2236
May 15 08:00:05 server kernel: [    4.567890] sd 0:0:0:0: [sda] 976773168 512-byte logical blocks
May 15 08:00:10 server rsyslogd: [origin software="rsyslogd"] start
May 15 08:00:15 server systemd[1]: Starting Vigile Worker...
May 15 08:00:16 server vigile-worker[101]: Worker started, connecting to master
May 15 08:00:17 server vigile-worker[101]: Enrollment successful as node abc123
May 15 08:15:01 server CRON[567]: pam_unix(cron:session): session opened for user root
May 15 08:15:01 server CRON[567]: pam_unix(cron:session): session closed for user root
May 15 09:00:00 server systemd[1]: Starting daily apt upgrade...
May 15 09:00:30 server systemd[1]: Finished daily apt upgrade.
LOG

# ── Final image setup ─────────────────────────────────────────────────

RUN mkdir -p /etc/vigile /var/log

COPY --from=builder /build/vigile-worker /usr/local/bin/vigile-worker

# Run as root for /proc and Docker socket access in test environment.
# Hardening (non-root + docker group) will be done before production.

ENTRYPOINT ["/usr/local/bin/vigile-worker"]
