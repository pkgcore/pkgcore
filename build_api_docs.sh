#!/bin/bash -x
if [ -z "$2" ] || [ "$#" -lt 2 ]; then
    echo "need two args- [ html | pdf ], and the directory location to write the results to"
    exit 1
fi

if [ "$1" != "html" ] && [ "$1" != "pdf" ]; then
    echo "first arg must be either html, or pdf; $1 isn't valid."
    exit 2
fi

type="$1"
shift
out="$1"
shift

export SNAKEOIL_DEMANDLOAD_PROTECTION=n
export SNAKEOIL_DEMANDLOAD_DISABLED=y
epydoc --"${type}" --no-frames --no-frames -n pkgcore --graph=classtree -u \
    http://pkgcore.org/trac/pkgcore --show-imports --show-sourcecode --include-log --include-log \
    --inheritance=included --quiet --exclude='pkgcore\.test\..*' --exclude='snakeoil\.test\..*' --simple-term pkgcore snakeoil -o "${out}" "$@" 
