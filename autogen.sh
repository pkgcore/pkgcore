#!/bin/sh

autoheader || exit 1
aclocal || exit 1
autoconf || exit 1
automake -a -c || exit 1

if [ -x ./test.sh ] ; then
	exec ./test.sh "$@"
fi
