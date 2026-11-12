#!/usr/bin/env bash
# Explicit setup only, as root in Ubuntu. No Docker or persistent cluster startup.
set -euo pipefail
test "$(id -u)" = 0
test ! -d /etc/postgresql || test -z "$(find /etc/postgresql -mindepth 2 -name postgresql.conf -print -quit)"
# Refuse to replace host service policies. Installation is for an empty distro.
test ! -e /usr/sbin/policy-rc.d
test ! -e /etc/postgresql-common/createcluster.conf
mkdir -p /etc/postgresql-common
printf '#!/bin/sh\nexit 101\n' > /usr/sbin/policy-rc.d
chmod 755 /usr/sbin/policy-rc.d
printf 'create_main_cluster = false\n' > /etc/postgresql-common/createcluster.conf
cleanup() { rm -f /usr/sbin/policy-rc.d; }
trap cleanup EXIT
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get -y -qq -o Dpkg::Options::=--force-confold install --no-install-recommends postgresql-16 postgresql-16-postgis-3
test -z "$(pg_lsclusters --no-header)"
/usr/lib/postgresql/16/bin/postgres --version
test -f /usr/share/postgresql/16/extension/postgis.control
