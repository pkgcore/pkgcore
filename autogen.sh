#!/bin/sh

autoheader || exit 1
aclocal-1.8 || exit 1
libtoolize --automake -c -f || exit 1
autoconf || exit 1
automake-1.8 -a -c || exit 1

if [ -x ./test.sh ] ; then
	exec ./test.sh "$@"
fi
