# this functionality is all related to saving/loading environmental dumps for ebuilds

escape_regex() {
    local f
    while [ -n "$1" ]; do
        f="${1//+/\+}"
        f="${f//.*/[A-Za-z0-9_-+./]*}"
        echo -n "$f"
        shift
    done
}

filter_env_func_filter() {
    while [ -n "$1" ]; do
        echo -n "$(escape_regex "$1")"
        [ "$#" != 1 ] && echo -n ','
        shift
    done
}

gen_regex_func_filter() {
    local f
    if [ "$#" == 1 ]; then
        echo -n "$(escape_regex "$1")"
        return
    fi
    echo -n "\($(escape_regex "$1")"
    shift
    while [ -n "$1" ]; do
        echo -n "\|$(escape_regex "$1")"
        shift
    done
    echo -n "\)"
}

filter_env_var_filter() {
    local _internal_var
    while [ -n "$1" ]; do
        echo -n "$1"
        [ "$#" != 1 ] && echo -n ','
        shift
    done
}

gen_regex_var_filter() {
    local _internal_var
    if [ "$#" == 1 ]; then
        echo -n "$1"
        return
    fi
    echo -n "\($1"
    shift
    while [ -n "$1" ]; do
        echo -n "\|$1"
        shift
    done
    echo -n '\)'
}

invoke_filter_env() {
    local opts
    [[ $PKGCORE_DEBUG -ge 3 ]] && opts="$opts --debug"
    PYTHONPATH="${PKGCORE_PYTHONPATH}" "${PKGCORE_PYTHON_BINARY}" \
        "${PKGCORE_BIN_PATH}/filter-env" "$@"
}

# selectively saves  the environ- specifically removes things that have been marked to not be exported.
# dump the environ to stdout.
dump_environ() {
    local x y;

    #env dump, if it doesn't match a var pattern, stop processing, else print only if
    #it doesn't match one of the filter lists.
    # vars, then funcs.

    declare | invoke_filter_env -f \
        "$(filter_env_func_filter ${DONT_EXPORT_FUNCS} )" -v \
        "$(filter_env_var_filter ${DONT_EXPORT_VARS} f x )" || die "internal error: filter-env returned non zero: $?"

    if ! has "--no-attributes" "$@"; then
        echo "# env attributes"
        # leave this form so that it's easier to add others in.
        for y in export ; do
            x=$(${y} | sed -n "/declare \(-[^ ]\+ \)*/!d; s:^declare \(-[^ ]\+ \)*\([A-Za-z0-9_+]\+\)\(=.*$\)\?$:\2:; /^$(gen_regex_var_filter ${DONT_EXPORT_VARS} x y)$/! p;")
            [ -n "$x" ] && echo "${y} $(echo $x);"
        done

        # if it's just declare -f some_func, filter it, else drop it if it's one of the filtered funcs
        declare -F | sed -n "/^declare -[^ ]\( \|[^ ]? $(gen_regex_func_filter ${DONT_EXPORT_FUNCS})$\)\?/d; s/^/    /;s/;*$/;/p;"

        shopt -p
    fi
}

# dump environ to $1, optionally piping it through $2 and redirecting $2's output to $1.
export_environ() {
    local temp_umask
    if [ "${1:-unset}" == "unset" ]; then
        die "export_environ requires at least one arguement"
    fi

    #the spaces on both sides are important- otherwise, the later ${DONT_EXPORT_VARS/ temp_umask /} won't match.
    #we use spaces on both sides, to ensure we don't remove part of a variable w/ the same name-
    # ex: temp_umask_for_some_app == _for_some_app.
    #Do it with spaces on both sides.

    DONT_EXPORT_VARS="${DONT_EXPORT_VARS} temp_umask "
    temp_umask=`umask`
    umask 0002

    if [ "${2:-unset}" == "unset" ]; then
        dump_environ > "$1"
    else
        dump_environ | $2 > "$1"
    fi
    chown portage:portage "$1" &>/dev/null
    chmod 0664 "$1" &>/dev/null

    DONT_EXPORT_VARS="${DONT_EXPORT_VARS/ temp_umask /}"

    umask $temp_umask
}

# reload a saved env, applying usual filters to the env prior to eval'ing it.
load_environ() {
    local src e ret EXISTING_PATH
    # localize these so the reload doesn't have the ability to change them
    local DONT_EXPORT_VARS="${DONT_EXPORT_VARS} src e ret"
    local DONT_EXPORT_FUNCS="${DONT_EXPORT_FUNCS} load_file declare"
    local SANDBOX_STATE=$SANDBOX_ON
    local EBUILD_PHASE=$EBUILD_PHASE
    local PKGCORE_EBUILD_PHASE=$PKGCORE_EBUILD_PHASE
    local reload_failure=0
    SANDBOX_ON=0

    SANDBOX_READ="/bin:${SANDBOX_READ}:/dev/urandom:/dev/random:$PKGCORE_BIN_PATH"
    SANDBOX_ON=$SANDBOX_STATE

    [ ! -f "$1" ] && die "load_environ called with a nonexist env: $1"

    if [ -z "$1" ]; then
        die "load_environ called with no args, need args"
    fi
    src="$1"

    EXISTING_PATH=$PATH
    PKGCORE_ATTRS_EXPORTED=
    PKGCORE_ATTRS_READONLY=
    PKGCORE_SHOPTS_SET=
    PKGCORE_SHOPTS_UNSET=
    if [ -f "$src" ]; then
        # other managers shove the export/declares inline; we store it in a
        # func so that the var attrs can be dropped if needed.
        # thus we define these temporarily, to intercept the inlined statements
        # and push them into a func.
        function declare() {
            local r e vars
            while [ "${1:0:1}" == "-" ]; do
                if [ "${1/r}" != "$1" ]; then
                    r=1
                fi
                if [ "${1/x}" != "$1" ]; then
                    e=1
                fi
                shift
            done
            if [ -z "$r" ] && [ -z "$e" ]; then
                return
            fi
            while [ -n "$1" ]; do
                vars="${vars} ${1/=*}"
                shift
            done
            if [ -n "$r" ]; then
                PKGCORE_ATTRS_READONLY="${PKGCORE_ATTRS_READONLY} ${vars}"
            fi
            if [ -n "$e" ]; then
                PKGCORE_ATTRS_EXPORTED="${PKGCORE_ATTRS_EXPORTED} ${vars}"
            fi
        };
        function export() {
            declare -x "$@"
        };
        function readonly() {
            declare -r "$@"
        };
        function shopt() {
            if [ "$1" == "-s" ]; then
                shift
                PKGCORE_SHOPTS_SET="${PKGCORE_SHOPTS_SET} $*"
            elif [ "$1" == "-u" ]; then
                shift
                PKGCORE_SHOPTS_UNSET="${PKGCORE_SHOPTS_UNSET} $*"
            else
                echo "ignoring unexpected shopt arg in env dump- $*" >&2
            fi
        }

        # run the filtered env.
        eval "$(invoke_filter_env \
            -f "$(filter_env_func_filter ${DONT_EXPORT_FUNCS} )" \
            -v "$(filter_env_var_filter ${DONT_EXPORT_VARS} f x EXISTING_PATH)" -i "$src")"
        ret=$?

        # if reinstate_loaded_env_attributes exists, run it to add to the vars.
        type reinstate_loaded_env_attributes &> /dev/null && \
            reinstate_loaded_env_attributes
        unset -f declare readonly export reinstate_loaded_env_attributes shopt

        # do not export/readonly an attr that is filtered- those vars are internal/protected,
        # thus their state is guranteed
        # additionally, if the var *was* nonexistant, export'ing it serves to create it

        pkgcore_tmp_func() {
            while [ -n "$1" ]; do
                echo "$1"
                shift
            done
        }

        filter="^$(gen_regex_var_filter $DONT_EXPORT_VARS XARGS)$"
        # yes we're intentionally ignoring PKGCORE_ATTRS_READONLY.  readonly isn't currently used.
        PKGCORE_ATTRS_EXPORTED=$(echo $(pkgcore_tmp_func $PKGCORE_ATTRS_EXPORTED | grep -v "$filter"))
        unset pkgcore_tmp_func filter

        # rebuild the func.
        local body=
        [ -n "$PKGCORE_ATTRS_EXPORTED" ] && body="export $PKGCORE_ATTRS_EXPORTED;"
        [ -n "$PKGCORE_SHOPTS_SET" ]     && body="${body} shopt -s ${PKGCORE_SHOPTS_SET};"
        [ -n "$PKGCORE_SHOPTS_UNSET" ]   && body="${body} shopt -u ${PKGCORE_SHOPTS_UNSET};"
        unset PKGCORE_ATTRS_READONLY PKGCORE_ATTRS_EXPORTED PKGCORE_SHOPTS_UNSET PKGCORE_SHOPTS_SET

        # and... finally make the func.
        eval "reinstate_loaded_env_attributes() { ${body:-:;} };"
    else
        echo "ebuild=${EBUILD}, phase $EBUILD_PHASE" >&2
        ret=1
    fi
    pkgcore_ensure_PATH "$EXISTING_PATH"
    return $(( $ret ))
}
