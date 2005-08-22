#!/bin/bash
# Copyright 1999-2004 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2
# $Header$

# Ping a single host and collect the round-trip time.  Unfortunately
# this measures latency, not bandwidth, but it's better than nothing.
pinghost() {
    local host result

    # Extract the hostname from the URL
    host="${1#*://}"; host="${host%%/*}"

    # Attempt to ping the host three times, with an overall timeout of
    # 10 seconds.
    result=`ping -q -c3 -w10 ${host} 2>/dev/null`

    # Extract average ping time, truncated to integer
    result="${result%.?/*}"
    result="${result##*/}"

    # Test for sensible $result and return.  If zero packets were
    # received, then $result will not be sensible since the above
    # extraction would have failed.
    if [ "$result" -gt 0 ] 2>/dev/null; then
	return $result
    else
	return 9999
    fi
}

# Ping all of the hosts in parallel, collate the output.
pingall() {
    local i output

    for i in $*
    do
	# Do this as a single echo so it happens as a single
	# "write".  This is so that the writes coming from the
	# multiple processes aren't mixed within a line.  It should
	# usually work.  :-)
	( pinghost $i; echo "$? $i" ) &
    done
    wait
}

pingall $1 | sort -n | awk '{print $NF}'
