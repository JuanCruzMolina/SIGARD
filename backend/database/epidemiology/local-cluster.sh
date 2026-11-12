#!/usr/bin/env bash
# Manual private cluster. Does not register a service or touch port 5432.
set -euo pipefail
test "$(id -u)" != 0
EPIDIR="$HOME/.local/share/sigard-epi/cluster-v1"
PGBIN=/usr/lib/postgresql/16/bin
PORT=55439
MARKER=sigard-epi-local-v1
case "${1:-}" in
 init)
   test ! -e "$EPIDIR"
   test -f "${2:?Password file required}"
   mkdir -p "$EPIDIR"
   chmod 700 "$EPIDIR"
   "$PGBIN/initdb" -D "$EPIDIR/data" --username=sigard_epi_owner --auth=scram-sha-256 --pwfile="$2" --encoding=UTF8 --locale=C.UTF-8 > "$EPIDIR/init.log" 2>&1
   printf '%s\n' "$MARKER" > "$EPIDIR/ownership-marker"
   ;;
 start)
   test "$(cat "$EPIDIR/ownership-marker")" = "$MARKER"
   "$PGBIN/pg_ctl" -D "$EPIDIR/data" -l "$EPIDIR/server.log" -o "-h 127.0.0.1 -p $PORT -c cluster_name=$MARKER -c unix_socket_directories=$EPIDIR -c log_min_error_statement=panic -c log_error_verbosity=terse -c log_parameter_max_length_on_error=0" -w start
   ;;
 stop)
   test "$(cat "$EPIDIR/ownership-marker")" = "$MARKER"
   "$PGBIN/pg_ctl" -D "$EPIDIR/data" -m fast -w stop
   ;;
 status)
   test "$(cat "$EPIDIR/ownership-marker")" = "$MARKER"
   "$PGBIN/pg_ctl" -D "$EPIDIR/data" status
   ;;
 *) exit 2;;
esac
