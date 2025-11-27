#!/bin/bash -e
base=$(dirname "$(dirname "$(readlink -f "$0")")")

if [ ${#} -ne 2 ]; then
    echo "requires 2 arguments; the sphinx mode, and where to put the output."
    exit 1;
fi
mode="$1"
output="$2"



# the point of this script is to capture sphinx output for extension
# failures, and also dump that log automatically.

# force US; sphinx errors are localized, and we're abusing grep.
export LANG=en_US.UTF-8 

# capture stderr
t=$(mktemp)
if python -m sphinx.cmd.build -a -b "$mode" "$base/doc" "$output" 2>$t; then
    exit $?
fi

# extract the traceback path
dump=$(grep -A1 'traceback has been saved in' "$t" | tail -n1)
cat < "$t"
echo
if [ -z "$dump" ]; then
    echo "FAILED auto extracting the traceback file.  you'll have to do it manually"
else
    echo
    echo "contents of $dump"
    echo
    cat < "$dump"
    rm "$t"
fi

exit 2