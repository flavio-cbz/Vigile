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
# Columns: UNIT LOAD ACTIVE SUB DESCRIPTION
#   ACTIVE = active | inactive | failed
#   SUB    = running | exited | dead | failed
RUN cat > /usr/local/bin/systemctl << 'SYSCTL'
#!/bin/sh
get_col() { awk -v svc="$1" -v col="$2" '$1 == svc { print $col }' /usr/local/vigile-sim/services.txt; }
svc_name() {
  case "$1" in
    *.service) echo "$1" ;;
    *)         echo "$1.service" ;;
  esac
}
normalize() { echo "$1" | sed 's/\.service//'; }

if [ "$1" = "list-units" ] && [ "$2" = "--type=service" ]; then
  cat /usr/local/vigile-sim/services.txt
elif [ "$1" = "is-active" ]; then
  active=$(get_col "$(svc_name "$2")" 3)
  echo "${active:-inactive}"
elif [ "$1" = "is-enabled" ]; then
  res=$(get_col "$(svc_name "$2")" 3)
  if [ -n "$res" ]; then echo "enabled"; else echo "disabled"; fi
elif [ "$1" = "restart" ]; then
  s=$(svc_name "$2")
  active=$(get_col "$s" 3)
  if [ "$active" = "failed" ]; then
    sed -i "s/^ *${s}  *loaded  *failed  *failed/${s}  loaded  active  running/" /usr/local/vigile-sim/services.txt
    echo "Service ${2} restarted (recovered from failed state)"
  else
    echo "Service ${2} restarted"
  fi
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

# Services list — realistic production server with various states
# Format: UNIT LOAD ACTIVE SUB DESCRIPTION
#   ACTIVE = active | inactive | failed
#   SUB    = running | exited | dead | failed
RUN cat > /usr/local/vigile-sim/services.txt << 'SVC'
  accounts-daemon.service      loaded active running Accounts Service
  apparmor.service             loaded active exited  Load AppArmor profiles
  apache2.service              loaded inactive dead  Apache HTTP Server (disabled, nginx used)
  backup.service               loaded inactive dead  Daily backup job (nocturnal schedule)
  certbot.service              loaded inactive dead  Certbot automatic renewal (monthly)
  chrony.service               loaded active running NTP time synchronization
  console-setup.service        loaded active exited  Set console font and keymap
  containerd.service           loaded active running containerd container runtime
  cron.service                 loaded active running Regular background program processing daemon
  dbus.service                 loaded active running D-Bus System Message Bus
  docker.service               loaded active running Docker Application Container Engine
  fail2ban.service             loaded active running Fail2Ban Service
  getty@tty1.service           loaded active running Getty on tty1
  irqbalance.service           loaded active running IRQ balance daemon
  lvm2-monitor.service         loaded active exited  Monitoring of LVM2 mirrors
  mysql.service                loaded failed  failed MySQL Community Server (crashed: OOM killer)
  netdata.service              loaded active running Netdata, X-Ray Vision for your infrastructure!
  networking.service           loaded active exited  Raise network interfaces
  nginx.service                loaded active running Nginx Web Server
  nmbd.service                 loaded active running Samba NMB Daemon
  node_exporter.service        loaded active running Prometheus Node Exporter
  ntpd.service                 loaded active running NTP daemon (legacy)
  polkit.service               loaded active running Authorization Manager
  postgresql.service           loaded active running PostgreSQL database server
  prometheus.service           loaded failed  failed Prometheus Monitoring (disk full)
  redis-server.service         loaded active running Redis key-value store
  rpcbind.service              loaded active running RPC bind service
  rsyslog.service              loaded active running System Logging Service
  smartmontools.service        loaded active running S.M.A.R.T. monitoring daemon
  smbd.service                 loaded active running Samba SMB Daemon
  snapd.service                loaded active running Snap Daemon
  ssh.service                  loaded active running OpenSSH Daemon
  systemd-journald.service     loaded active running Journal Service
  systemd-logind.service       loaded active running Login Service
  systemd-udevd.service        loaded active running udev Kernel Device Manager
  ufw.service                  loaded active exited  Uncomplicated firewall
  unattended-upgrades.service  loaded inactive dead  Unattended upgrades (disabled manually)
  udisks2.service              loaded active running Disk Manager
  vigile-worker.service        loaded active running Vigile Fleet Manager Worker
SVC

# Log fixtures — realistic service logs with errors, attacks, failures
RUN mkdir -p /usr/local/vigile-sim/logs

# ── SSH: brute force attempts + legit access ────────────────────────
RUN cat > /usr/local/vigile-sim/logs/ssh.service.log << 'LOG'
May 15 06:12:01 server sshd[1123]: Failed password for root from 45.33.32.156 port 39504 ssh2
May 15 06:12:05 server sshd[1124]: Failed password for root from 45.33.32.156 port 39508 ssh2
May 15 06:12:09 server sshd[1125]: Failed password for root from 45.33.32.156 port 39512 ssh2
May 15 06:12:13 server sshd[1126]: Failed password for root from 45.33.32.156 port 39516 ssh2
May 15 06:12:17 server sshd[1127]: Failed password for root from 45.33.32.156 port 39520 ssh2
May 15 06:12:21 server sshd[1128]: Failed password for root from 45.33.32.156 port 39524 ssh2
May 15 06:12:25 server sshd[1129]: Failed password for root from 45.33.32.156 port 39528 ssh2
May 15 06:12:29 server sshd[1130]: Failed password for root from 45.33.32.156 port 39532 ssh2
May 15 06:12:30 server sshd[1131]: Connection closed by authenticating user root 45.33.32.156 port 39532
May 15 07:30:12 server sshd[1140]: Failed password for invalid user admin from 91.121.89.124 port 52134 ssh2
May 15 07:30:17 server sshd[1141]: Failed password for invalid user admin from 91.121.89.124 port 52138 ssh2
May 15 07:30:22 server sshd[1142]: Failed password for invalid user admin from 91.121.89.124 port 52142 ssh2
May 15 07:30:27 server sshd[1143]: Failed password for invalid user admin from 91.121.89.124 port 52146 ssh2
May 15 07:30:32 server sshd[1144]: Connection closed by invalid user admin 91.121.89.124 port 52146
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
May 15 11:20:01 server sshd[1300]: Failed password for invalid user oracle from 185.220.101.42 port 60123 ssh2
May 15 11:20:05 server sshd[1301]: Failed password for invalid user oracle from 185.220.101.42 port 60127 ssh2
May 15 11:20:10 server sshd[1302]: Failed password for invalid user oracle from 185.220.101.42 port 60131 ssh2
May 15 11:20:15 server sshd[1303]: Connection closed by invalid user oracle 185.220.101.42 port 60131
LOG

# ── NGINX: mix of legit traffic + attacks ───────────────────────────
RUN cat > /usr/local/vigile-sim/logs/nginx.service.log << 'LOG'
May 15 06:00:00 server nginx[2346]: Starting nginx 1.24.0
May 15 06:00:00 server nginx[2346]: nginx: using the epoll event loop
May 15 06:00:00 server nginx[2346]: nginx: listening on 0.0.0.0:80
May 15 06:00:00 server nginx[2346]: nginx: listening on 0.0.0.0:443
May 15 06:30:15 server nginx[2346]: 45.33.32.156 - - [15/May/2026:06:30:15 +0000] "GET /wp-login.php HTTP/1.1" 404 498 "-" "python-requests"
May 15 06:30:17 server nginx[2346]: 45.33.32.156 - - [15/May/2026:06:30:17 +0000] "POST /xmlrpc.php HTTP/1.1" 404 498 "-" "python-requests"
May 15 06:30:20 server nginx[2346]: 45.33.32.156 - - [15/May/2026:06:30:20 +0000] "GET /.env HTTP/1.1" 404 162 "-" "Mozilla/5.0"
May 15 06:30:22 server nginx[2346]: 45.33.32.156 - - [15/May/2026:06:30:22 +0000] "GET /vendor/phpunit/phpunit/README.md HTTP/1.1" 404 162 "-" "Mozilla/5.0"
May 15 06:30:25 server nginx[2346]: 45.33.32.156 - - [15/May/2026:06:30:25 +0000] "GET /debug/default/view?panel=config HTTP/1.1" 404 162 "-" "python-requests"
May 15 07:00:00 server nginx[2346]: 192.168.1.100 - - [15/May/2026:07:00:00 +0000] "GET / HTTP/1.1" 200 5678 "-" "Mozilla/5.0"
May 15 08:00:00 server nginx[2346]: 192.168.1.100 - - [15/May/2026:08:00:00 +0000] "GET /api/stats HTTP/1.1" 200 234 "-" "curl/8.14"
May 15 09:00:00 server nginx[2346]: 81.49.190.197 - - [15/May/2026:09:00:00 +0000] "GET / HTTP/1.1" 200 5678 "-" "Mozilla/5.0"
May 15 09:15:30 server nginx[2346]: 81.49.190.197 - - [15/May/2026:09:15:30 +0000] "GET /api/health HTTP/1.1" 200 45 "-" "python-requests"
May 15 09:30:00 server nginx[2346]: 10.0.0.50 - - [15/May/2026:09:30:00 +0000] "POST /wp-login.php HTTP/1.1" 403 234 "-" "python-requests"
May 15 09:45:00 server nginx[2346]: 203.0.113.42 - - [15/May/2026:09:45:00 +0000] "GET /.env HTTP/1.1" 404 162 "-" "Mozilla/5.0"
May 15 10:00:00 server nginx[2346]: 203.0.113.42 - - [15/May/2026:10:00:00 +0000] "GET /../../etc/passwd HTTP/1.1" 400 156 "-" "python-requests"
May 15 10:00:02 server nginx[2346]: 203.0.113.42 - - [15/May/2026:10:00:02 +0000] "GET /admin/ HTTP/1.1" 403 178 "-" "Mozilla/5.0"
May 15 10:00:05 server nginx[2346]: 203.0.113.42 - - [15/May/2026:10:00:05 +0000] "POST /admin/login.php HTTP/1.1" 403 178 "-" "Mozilla/5.0"
May 15 11:00:00 server nginx[2346]: 192.168.1.200 - - [15/May/2026:11:00:00 +0000] "GET / HTTP/1.1" 200 5678 "-" "curl/8.14"
LOG

# ── POSTGRESQL: normal operation ──────────────────────────────────
RUN cat > /usr/local/vigile-sim/logs/postgresql.service.log << 'LOG'
May 15 06:00:05 server postgres[3456]: LOG:  starting PostgreSQL 16.2
May 15 06:00:05 server postgres[3457]: LOG:  database system was shut down at 2026-05-14 23:59:59 UTC
May 15 06:00:05 server postgres[3457]: LOG:  database system is ready to accept connections
May 15 06:00:05 server postgres[3458]: LOG:  autovacuum launcher started
May 15 06:00:06 server postgres[3458]: LOG:  logical replication launcher started
May 15 07:00:00 server postgres[3458]: LOG:  checkpoint starting: time
May 15 07:00:05 server postgres[3458]: LOG:  checkpoint complete: wrote 42 buffers in 4.2s
May 15 08:00:00 server postgres[3458]: LOG:  checkpoint starting: time
May 15 08:00:04 server postgres[3458]: LOG:  checkpoint complete: wrote 38 buffers in 3.8s
May 15 08:15:00 server postgres[3458]: LOG:  duration: 15.432 ms  statement: SELECT * FROM users WHERE last_login > now() - interval '24h'
May 15 09:00:00 server postgres[3458]: LOG:  checkpoint starting: time
May 15 09:00:06 server postgres[3458]: LOG:  checkpoint complete: wrote 156 buffers in 5.7s
May 15 09:30:00 server postgres[3458]: LOG:  duration: 2431.567 ms  statement: VACUUM ANALYZE;
May 15 10:00:00 server postgres[3458]: LOG:  checkpoint starting: time
May 15 10:00:03 server postgres[3458]: LOG:  checkpoint complete: wrote 44 buffers in 2.9s
LOG

# ── MYSQL: crash log (service failed) ──────────────────────────────
RUN cat > /usr/local/vigile-sim/logs/mysql.service.log << 'LOG'
May 15 05:30:01 server mysqld[4567]: InnoDB: Database was not shut down normally!
May 15 05:30:01 server mysqld[4567]: InnoDB: Starting recovery...
May 15 05:30:05 server mysqld[4567]: InnoDB: Recovery completed
May 15 05:30:05 server mysqld[4567]: InnoDB: Log scan progressed past the checkpoint lsn
May 15 05:30:10 server mysqld[4567]: Initializing buffer pool, total size = 128M
May 15 05:30:12 server mysqld[4567]: Completed initialization of buffer pool
May 15 05:31:00 server mysqld[4567]: [ERROR] InnoDB: mmap(137438953472 bytes) failed; errno 12
May 15 05:31:00 server mysqld[4567]: [ERROR] InnoDB: Cannot allocate memory for the buffer pool
May 15 05:31:00 server mysqld[4567]: [ERROR] InnoDB: Plugin initialization aborted; error: Cannot allocate memory
May 15 05:31:00 server mysqld[4567]: [ERROR] Plugin 'InnoDB' init function returned error.
May 15 05:31:00 server mysqld[4567]: [ERROR] Plugin 'InnoDB' registration as a Storage Engine failed.
May 15 05:31:00 server mysqld[4567]: [ERROR] Failed to initialize plugins.
May 15 05:31:00 server mysqld[4567]: [ERROR] Aborting
May 15 05:31:01 server systemd[1]: mysql.service: Main process exited, code=exited, status=1/FAILURE
May 15 05:31:01 server systemd[1]: mysql.service: Failed with result 'exit-code'.
May 15 05:31:10 server systemd[1]: mysql.service: Scheduled restart job, restart counter is at 3.
May 15 05:31:11 server mysqld[4580]: [ERROR] InnoDB: mmap(137438953472 bytes) failed; errno 12
May 15 05:31:11 server mysqld[4580]: [ERROR] InnoDB: Cannot allocate memory for the buffer pool
May 15 05:31:11 server mysqld[4580]: [ERROR] Aborting
May 15 05:31:12 server systemd[1]: mysql.service: Failed with result 'exit-code'.
May 15 05:31:15 server systemd[1]: mysql.service: start request repeated too quickly
May 15 05:31:15 server systemd[1]: mysql.service: Failed with result 'exit-code'.
May 15 05:31:16 server systemd[1]: Failed to start MySQL Community Server.
LOG

# ── PROMETHEUS: disk full crash log ────────────────────────────────
RUN cat > /usr/local/vigile-sim/logs/prometheus.service.log << 'LOG'
May 15 04:00:00 server prometheus[5678]: ts=2026-05-15T04:00:00Z caller=main.go:128 level=info msg="Starting Prometheus" version=2.45.0
May 15 04:00:00 server prometheus[5678]: ts=2026-05-15T04:00:00Z caller=main.go:129 level=info build_context="(go=1.21)"
May 15 04:00:01 server prometheus[5678]: ts=2026-05-15T04:00:01Z caller=web.go:542 level=info component=web msg="Start listening for connections" address=0.0.0.0:9090
May 15 04:00:02 server prometheus[5678]: ts=2026-05-15T04:00:02Z caller=head.go:618 level=info component=tsdb msg="WAL was corrupted" path=/var/lib/prometheus/wal
May 15 04:00:02 server prometheus[5678]: ts=2026-05-15T04:00:02Z caller=head.go:622 level=info component=tsdb msg="WAL truncation failed" err="write /var/lib/prometheus/wal/00001234: no space left on device"
May 15 04:00:03 server prometheus[5678]: ts=2026-05-15T04:00:03Z caller=main.go:545 level=error msg="Unable to create storage" err="open /var/lib/prometheus: no space left on device"
May 15 04:00:03 server prometheus[5678]: ts=2026-05-15T04:00:03Z caller=main.go:600 level=info msg="Prometheus stopped"
May 15 04:00:04 server systemd[1]: prometheus.service: Main process exited, code=exited, status=1/FAILURE
May 15 04:00:04 server systemd[1]: prometheus.service: Failed with result 'exit-code'.
LOG

# ── Realistic syslog: kernel, system events, errors ────────────────
RUN cat > /var/log/syslog << 'LOG'
May 15 06:00:00 server kernel: [    0.000000] Linux version 6.8.0-45-generic (buildd@lcy02-amd64)
May 15 06:00:00 server kernel: [    0.000000] Command line: BOOT_IMAGE=/vmlinuz-6.8.0-45-generic root=/dev/sda2 ro quiet
May 15 06:00:00 server kernel: [    0.000000] CPU: Intel(R) Xeon(R) E-2236 CPU @ 3.40GHz (6 cores, 12 threads)
May 15 06:00:01 server kernel: [    0.123456] Memory: 32140872K/32768124K available
May 15 06:00:02 server kernel: [    1.234567] sd 0:0:0:0: [sda] 976773168 512-byte logical blocks (500 GB)
May 15 06:00:03 server kernel: [    2.345678] md: raid1: sda1 sdb1 as active raid1
May 15 06:00:05 server kernel: [    4.567890] EXT4-fs (sda2): mounted filesystem with ordered data mode
May 15 06:00:10 server rsyslogd: [origin software="rsyslogd"] start, running in compatibility mode
May 15 06:00:12 server systemd[1]: Starting Journal Service...
May 15 06:00:13 server systemd[1]: Started Journal Service.
May 15 06:00:14 server systemd[1]: Starting Vigile Worker...
May 15 06:00:15 server vigile-worker[101]: Worker started, connecting to master http://master:8000
May 15 06:00:16 server vigile-worker[101]: Enrollment successful as node abc123-def456
May 15 06:00:17 server vigile-worker[101]: Operational phase started
May 15 06:30:00 server systemd[1]: Starting daily dpkg database backup...
May 15 06:30:05 server systemd[1]: Finished daily dpkg database backup.
May 15 07:00:00 server CRON[789]: pam_unix(cron:session): session opened for user root
May 15 07:00:01 server CRON[789]: (root) CMD (test -x /usr/sbin/anacron || ( cd / && run-parts --report /etc/cron.hourly ))
May 15 07:00:01 server CRON[789]: pam_unix(cron:session): session closed for user root
May 15 07:30:00 server kernel: [ 5432] oom-kill: constraint=CONSTRAINT_NONE, process=mysqld, pid=4567, total-vm=1400000kB, anon-rss=1200000kB
May 15 07:30:01 server kernel: [ 5432] oom_reaper: reaped process 4567 (mysqld), now anon-rss=0kB
May 15 07:30:02 server systemd[1]: mysql.service: Main process exited, code=killed, status=9/OOM
May 15 08:00:00 server systemd[1]: Starting daily apt upgrade...
May 15 08:00:30 server systemd[1]: Finished daily apt upgrade.
May 15 09:00:00 server systemd[1]: Starting system activity accounting tool...
May 15 09:00:01 server systemd[1]: Started system activity accounting tool.
May 15 10:00:00 server systemd[1]: prometheus.service: Disk usage grew to 98%, checking...
May 15 10:00:01 server prometheus[5678]: Error: write /var/lib/prometheus/wal: no space left on device
May 15 10:00:02 server systemd[1]: prometheus.service: Main process exited, code=exited, status=1/FAILURE
May 15 10:15:00 server kernel: [ 12345] XFS (sda2): disk space warnings: 95% full
May 15 10:15:00 server kernel: [ 12345] XFS (sda2): 434762752 blocks, 412345678 used, 22417074 free
May 15 10:15:00 server kernel: [ 12345] XFS (sda2): WARNING: 95% disk space used
May 15 11:00:00 server systemd[1]: Started Vigile Worker healthcheck
LOG

# ── Final image setup ─────────────────────────────────────────────────

RUN mkdir -p /etc/vigile /var/log

COPY --from=builder /build/vigile-worker /usr/local/bin/vigile-worker

# Run as root for /proc and Docker socket access in test environment.
# Hardening (non-root + docker group) will be done before production.

ENTRYPOINT ["/usr/local/bin/vigile-worker"]
