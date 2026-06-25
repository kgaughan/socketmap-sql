#!/bin/sh

set -e

usage () {
	cat <<FIN
Usage:
  $0 [-P]
  $0 -h

Flags:
  -h  show this help
  -P  prompt for a passphrase; setting NFPM_PASSPHRASE makes this a no-op

FIN
}

while getopts "hP" opt; do
	case "$opt" in
		h)
			usage
			exit 0
			;;
		P)
			prompt=1
			;;
		*)
			usage 2>&1
			exit 1
			;;
	esac
done

if test "${prompt:-}" = "1" -a -z "${NFPM_PASSPHRASE:-}"; then
	orig_stty="$(stty -g)"
	trap 'stty "$orig_stty"' INT TERM EXIT
	stty -echo
	read -p "passphrase> " NFPM_PASSPHRASE
	stty "$orig_stty"
	trap - INT TERM EXIT
	echo
	export NFPM_PASSPHRASE
fi

export VERSION=$(git describe --tags --abbrev=0 || echo "v0.0.0")
export SOURCE_DATE_EPOCH=$(git log -1 --pretty=%ct)

nfpm package --packager rpm
