# Copyright 2011 Brian Harring <ferringb@gmail.com>
# license GPL2/BSD 3

use()
{
	# echo "the use function should not be used from global scope"
	# just return true, in this context the function has no meaning
	:
}

hasq()
{
    if has "$@"; then
        return 0
    fi
    return 1
}

hasv()
{
    if ! has "$@"; then
        return 1;
    fi
    echo "${1}"
    return 0
}

DONT_EXPORT_FUNCS="${DONT_EXPORT_FUNCS} use hasq hasv"

:
