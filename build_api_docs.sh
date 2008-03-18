#!/bin/bash -x
if [ -z "$2" ] || [ "$#" != 2 ]; then
    echo "need two args- [ html | pdf ], and the directory location to write the results to"
    exit 1
fi

if [ "$1" != "html" ] && [ "$1" != "pdf" ]; then
    echo "first arg must be either html, or pdf; $1 isn't valid."
    exit 2
fi

export SNAKEOIL_DEMANDLOAD_PROTECTION=n
epydoc --${1} --no-frames --no-frames --graph=all -n pkgcore -u \
    http://pkgcore.org/trac/pkgcore --show-imports --include-log \
    --inheritance=included --quiet --simple-term -o "$2" pkgcore --exclude='pkgcore\.test\.*'
