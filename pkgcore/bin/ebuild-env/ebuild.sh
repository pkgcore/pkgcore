#!/bin/bash
# ebuild.sh; ebuild phase processing, env handling
# Copyright 2005-2006 Brian Harring <ferringb@gmail.com>
# Copyright 2004-2005 Gentoo Foundation

# general phase execution path-
# execute_phases is called, which sets EBUILD_PHASE, and then depending on the phase, 
# loads or initializes.  Env is init'd for non src based stages if the env isn't found- otherwise
# it loads the environ via load_environ call.  In cases where env isn't found for phases setup -> merge,
# it bails (theres no way the env should be missing- exemption is setup phase).
# 
# for env filtering for restoration and reloading, note the updates to DONT_EXPORT_(VARS|FUNCS).
# those vars are basically used to track what shouldn't be saved/restored.  Whitespace seperated,
# those vars can support posix (think egrep) regex.  They should hold all vars/funcs that are internal
# ebuild.sh vars.  Basically, filter all vars/funcs that are specific to ebuild.sh, not the ebuild.
# 
# after loading the env, user defined pre hooks are executed, dyn_${EBUILD_PHASE} is executed, 
# and the post hooks are executed.  If the env needs to be flushed to disk, MUST_EXPORT_ENV is set to 
# "yes", and execute_phases will dump it to ${T}/environment.
#
# few notes on general env stuff- if it's not ebuild specific or a user option, it's typically marked
# readonly.  This limits users, but also helps to ensure that reloaded envs from older portages don't
# overwrite an internal ebd.sh function that has since changed.

ORIG_VARS=`declare | egrep '^[^[:space:]{}()]+=' | cut -s -d '=' -f 1`
ORIG_FUNCS=`declare -F | cut -s -d ' ' -f 3`

DONT_EXPORT_FUNCS='portageq speak'

DONT_EXPORT_VARS="ORIG_VARS GROUPS ORIG_FUNCS FUNCNAME DAEMONIZED CCACHE.* DISTCC.* AUTOCLEAN CLEAN_DELAY SYNC
\(TMP\|\)DIR FEATURES CONFIG_PROTECT.* P\?WORKDIR \(FETCH\|RESUME\) COMMAND RSYNC_.* GENTOO_MIRRORS 
\(DIST\|FILES\|RPM\|ECLASS\)DIR HOME MUST_EXPORT_ENV QA_CONTROLLED_EXTERNALLY COLORTERM COLS ROWS HOSTNAME
myarg SANDBOX_.* BASH.* EUID PPID SHELLOPTS UID ACCEPT_\(KEYWORDS\|LICENSE\) BUILD\(_PREFIX\|DIR\) T DIRSTACK
DISPLAY \(EBUILD\)\?_PHASE PORTAGE_.* RC_.* SUDO_.* IFS PATH LD_PRELOAD ret line phases D EMERGE_FROM
PORT\(_LOGDIR\|DIR\(_OVERLAY\)\?\) ROOT TERM _ done e ENDCOLS PROFILE_.* BRACKET BAD WARN GOOD NORMAL EBUILD ECLASS LINENO
HILITE IMAGE TMP"

# flip this on to enable extra noisy output for debugging.
#DEBUGGING="yes"

# XXX: required for migration from .51 to this.
if [ -z "$PORTAGE_BIN_PATH" ]; then
    declare -rx PORTAGE_BIN_PATH="/usr/lib/portage/bin"
fi

# knock the sandbox vars back to the pkgs defaults.
reset_sandbox() {
    export SANDBOX_ON="1"
    export SANDBOX_PREDICT="${SANDBOX_PREDICT:+${SANDBOX_PREDICT}:}/proc/self/maps:/dev/console:/dev/random:${PORTAGE_TMPDIR}"
    export SANDBOX_WRITE="${SANDBOX_WRITE:+${SANDBOX_WRITE}:}/dev/shm:${PORTAGE_TMPDIR}"
    export SANDBOX_READ="${SANDBOX_READ:+${SANDBOX_READ}:}/dev/shm:${PORTAGE_TMPDIR}"
    local s
    for x in CCACHE_DIR DISTCC_DIR D WORKDIR T; do
        if [ -n "${!x}" ]; then
            addread  "${!x}"
            addwrite "${!x}"
        fi
    done
}

# Prevent aliases from causing portage to act inappropriately.
# Make sure it's before everything so we don't mess aliases that follow.
unalias -a

# We need this next line for "die" and "assert". It expands 
# It _must_ preceed all the calls to die and assert.
shopt -s expand_aliases

# Unset some variables that break things.
unset GZIP BZIP BZIP2 CDPATH GREP_OPTIONS GREP_COLOR GLOB_IGNORE

alias die='diefunc "$FUNCNAME" "$LINENO" "$?"'
alias assert='_pipestatus="${PIPESTATUS[*]}"; [[ "${_pipestatus// /}" -eq 0 ]] || diefunc "$FUNCNAME" "$LINENO" "$_pipestatus"'
alias save_IFS='[ "${IFS:-unset}" != "unset" ] && portage_old_IFS="${IFS}"'
alias restore_IFS='if [ "${portage_old_IFS:-unset}" != "unset" ]; then IFS="${portage_old_IFS}"; unset portage_old_IFS; else unset IFS; fi'

diefunc() {
    set +x
    # if we were signaled to die...
    if [[ -n $EBD_DISABLE_DIEFUNC ]]; then
        return
    fi
    local funcname="$1" lineno="$2" exitcode="$3"
    shift 3
    echo >&2
    echo "!!! ERROR: $CATEGORY/$PF failed." >&2
    dump_trace 2 >&2
    echo "!!! ${*:-(no error message)}" >&2
    echo "!!! If you need support, post the topmost build error, NOT this status message." >&2
    if [ "${EBUILD_PHASE/depend}" == "${EBUILD_PHASE}" ]; then
        for x in ${EBUILD_DEATH_HOOKS}; do
            ${x} ${1} ${2} ${3} "${@}" >&2 1>&2 
        done
    fi
    echo >&2
    exit 1
}


shopt -s extdebug &> /dev/null

# usage- first arg is the number of funcs on the stack to ignore.
# defaults to 1 (ignoring dump_trace)
dump_trace() {
    local funcname="" sourcefile="" lineno="" n e s="yes"

    declare -i strip=1

    if [[ -n $1 ]]; then
        strip=$(( $1 ))
    fi

    echo "Call stack:"
    for (( n = ${#FUNCNAME[@]} - 1, p = ${#BASH_ARGV[@]} ; n > $strip ; n-- )) ; do
        funcname=${FUNCNAME[${n} - 1]}
        sourcefile=$(basename ${BASH_SOURCE[${n}]})
        lineno=${BASH_LINENO[${n} - 1]}
        # Display function arguments
        args=
        if [[ -n "${BASH_ARGV[@]}" ]]; then
            for (( j = 0 ; j < ${BASH_ARGC[${n} - 1]} ; ++j )); do
                newarg=${BASH_ARGV[$(( p - j - 1 ))]}
                args="${args:+${args} }'${newarg}'"
            done
            (( p -= ${BASH_ARGC[${n} - 1]} ))
        fi
        echo "  ${sourcefile}, line ${lineno}:   Called ${funcname}${args:+ ${args}}"
    done
}

hasq() {
    local x

    local me=$1
    shift

    # All the TTY checks really only help out depend. Which is nice.
    # Logging kills all this anyway. Everything becomes a pipe. --NJ
    for x in "$@"; do
        if [ "${x}" == "${me}" ]; then
            return 0
        fi
    done
    return 1
}

hasv() {
    if hasq "$@"; then
        echo "${1}"
        return 0
    fi
    return 1
}

#if no perms are specified, dirs/files will have decent defaults
#(not secretive, but not stupid)
umask 022

# the sandbox is disabled by default except when overridden in the relevant stages
export SANDBOX_ON="0"

escape_regex() {
    local f
    while [ -n "$1" ]; do
        f="${1//+/\+}"
        f="${f//.*/[A-Za-z0-9_-+./]*}"
        echo -n "$f"
        shift
    done
}

gen_func_filter() {
    while [ -n "$1" ]; do
        echo -n "$(escape_regex "$1")"
        [ "$#" != 1 ] && echo -n ','
        shift
    done
}

gen_regex_func_filter() {
    local f
    if [ "$1" == 1 ]; then
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

gen_var_filter() {
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

# func for beeping and delaying a defined period of time.
sleepbeep() {
    if [ ! "$#" -lt 3 ] || [ ! "$#" -gt 0 ]; then
        echo "sleepbeep requires one arg- number of beeps"
        echo "additionally, can supply a 2nd arg- interval between beeps (defaults to 0.25s"
        die "invalid call to sleepbeep"
    fi
    local count=$(($1))
    local interval="${2:-0.25}"
    while [ $count -gt 0 ]; do
        echo -en "\a";
        sleep $interval &> /dev/null
        count=$(($count - 1))
    done
    return 0
}

# selectively saves  the environ- specifically removes things that have been marked to not be exported.
# dump the environ to stdout.
dump_environ() {
    # scope it so we can pass the output through a sed correction for newlines.
    local x y;
    #env dump, if it doesn't match a var pattern, stop processing, else print only if
    #it doesn't match one of the filter lists.
    # vars, then funcs.
    declare | filter-env -f "$(gen_func_filter ${DONT_EXPORT_FUNCS} )" -v "$(gen_var_filter ${DONT_EXPORT_VARS} f x )"
    if ! hasq "--no-attributes" "$@"; then
        echo $'reinstate_loaded_env_attributes ()\n{'
        for y in export 'declare -i' readonly; do
            x=$(${y} | sed -n "/declare \(-[^ ]\+ \)*/!d; s:^declare \(-[^ ]\+ \)*\([A-Za-z0-9_+]\+\)\(=.*$\)\?$:\2:; /^$(gen_regex_var_filter ${DONT_EXPORT_VARS} x y)$/! p;")
            [ -n "$x" ] && echo "    ${y} $(echo $x);"
        done
        
        # if it's just declare -f some_func, filter it, else drop it if it's one of the filtered funcs
        declare -F | sed -n "/^declare -[^ ]\( \|[^ ]? $(gen_regex_func_filter ${DONT_EXPORT_FUNCS})$\)\?/d; s/^/    /;s/;*$/;/p;"

        shopt -p | sed -e 's:^:    :; s/;*$/;/;'
        echo "}"
    fi
    
    if [ -n "${DEBUGGING}" ]; then
        echo "#dumping debug info"
        echo "#var filter..."
        echo "#$(gen_var_filter ${DONT_EXPORT_VARS} f x | sort)"
        echo "#"
        echo "#funcs"
        declare -F | sed -e 's:^:# :'
        echo "#"
        echo "#func filter..."
        echo "#$(gen_func_filter ${DONT_EXPORT_FUNCS} | sort)"
        echo "#DONT_EXPORT_VARS follow"
        for x in `echo $DONT_EXPORT_VARS | sort`; do
            echo "#    $x";
        done
        echo ""
        echo "#DONT_EXPORT_FUNCS follow"
        for x in `echo $DONT_EXPORT_FUNCS | sort`; do
            echo "#    $x";
        done
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

    debug-print "exporting env for ${EBUILD_PHASE} to $1, using optional post-processor '${2:-none}'"

    if [ "${2:-unset}" == "unset" ]; then
        dump_environ > "$1"
    else
        dump_environ | $2 > "$1"
    fi
    chown portage:portage "$1" &>/dev/null
    chmod 0664 "$1" &>/dev/null

    DONT_EXPORT_VARS="${DONT_EXPORT_VARS/ temp_umask /}"

    umask $temp_umask
    debug-print "exported."
}

# reload a saved env, applying usual filters to the env prior to eval'ing it.
load_environ() {
    local src e ret
    # localize these so the reload doesn't have the ability to change them
    local DONT_EXPORT_VARS="${DONT_EXPORT_VARS} src e ret"
    local DONT_EXPORT_FUNCS="${DONT_EXPORT_FUNCS} load_file declare"
    local SANDBOX_STATE=$SANDBOX_ON
    local EBUILD_PHASE=$EBUILD_PHASE
    local reload_failure=0
    SANDBOX_ON=0

    SANDBOX_READ="/bin:${SANDBOX_READ}:/dev/urandom:/dev/random:$PORTAGE_BIN_PATH"
    SANDBOX_ON=$SANDBOX_STATE

    [ ! -f "$1" ] && die "load_environ called with a nonexist env: $1"

    if [ -n "$DEBUGGING" ]; then
        echo "loading env for $EBUILD_PHASE" >&2
    fi

    if [ -z "$1" ]; then
        die "load_environ called with no args, need args"
    fi
    src="$1"
    [ -n "$DEBUGGING" ] && echo "loading environment from $src" >&2

    if [ -f "$src" ]; then

    	# XXX: note all of the *very careful* handling of bash env dumps through this code, and the fact 
    	# it took 4 months to get it right.  There's a reason you can't just pipe the $(export) to a file.
        # They were implemented wrong, as I stated when the export kludge was added.
    	# so we're just dropping the attributes.  .51-r4 should carry a fixed version, .51 -> .51-r3
        # aren't worth the trouble.  Drop all inline declare's that would be executed.
    	# potentially handle this via filter-env?
        # ~harring
        function declare() {
            :
        };
        eval "$(filter-env -f "$(gen_func_filter ${DONT_EXPORT_FUNCS} )" \
            -v "$(gen_var_filter ${DONT_EXPORT_VARS} f x )" -i "$src")"
        ret=$?
        unset -f declare
    else
        echo "ebuild=${EBUILD}, phase $EBUILD_PHASE" >&2
        ret=1
    fi
    return $(( $ret ))
}

# walk the cascaded profile src'ing it's various bashrcs.
# overriden by daemon normally.
source_profiles() {
    local dir
    save_IFS
    # XXX: Given the following unset, is this set needed?
    IFS=$'\n'
    for dir in ${PROFILE_PATHS}; do
        # Must unset it so that it doesn't mess up assumptions in the RCs.
        unset IFS
        if [ -f "${dir}/profile.bashrc" ]; then
            source "${dir}/profile.bashrc"
        fi
    done
    restore_IFS
    if [ -f "$PORTAGE_BASHRC" ]; then
        source "$PORTAGE_BASHRC"
    fi
}

# do all profile, bashrc's, and ebuild sourcing.  Should only be called in setup phase, unless the
# env is *completely* missing, as it is occasionally for ebuilds during prerm/postrm.
init_environ() {
#	echo "initializating environment" >&2
    OCC="$CC"
    OCXX="$CXX"


    # XXX this too, sucks.
#	export PATH="/sbin:/usr/sbin:/usr/lib/portage/bin:/bin:/usr/bin"
    if [ "${EBUILD_PHASE}" == "setup" ]; then
        #we specifically save the env so it's not stomped on by sourcing.
        #bug 51552
        dump_environ --no-attributes > "${T}/.temp_env"

        if [ "$USERLAND" == "GNU" ]; then
            local PORTAGE_SHIFTED_PATH="$PATH"
            source /etc/profile.env &>/dev/null
            PATH="${PORTAGE_SHIFTED_PATH:+${PORTAGE_SHIFTED_PATH}}${PATH:+:${PATH}}"
        fi
        #shift path.  I don't care about 51552, I'm not using the env's supplied path, alright? :)

        #restore the saved env vars.
        if ! load_environ "${T}/.temp_env"; then
            #this shouldn't happen.
            die "failed to load ${T}/.tmp_env- fs is readonly?"
        fi

        rm "${T}/.temp_env"
        source_profiles
    fi

    if [ "${EBUILD_PHASE}" != "depend" ]; then
        [ ! -z "$OCC" ] && export CC="$OCC"
        [ ! -z "$OCXX" ] && export CXX="$OCXX"

    fi

    # if daemonized, it's already loaded these funcs.
    if [ "$DAEMONIZED" != "yes" ]; then
        source "${PORTAGE_BIN_PATH}/ebuild-functions.sh" || die "failed sourcing ebuild-functions.sh"
    fi
    SANDBOX_ON="1"
    export S=${WORKDIR}/${P}

    # Expand KEYWORDS
    # We need to turn off pathname expansion for -* in KEYWORDS and 
    # we need to escape ~ to avoid tilde expansion (damn bash) :)
    set -f
    KEYWORDS="$(echo ${KEYWORDS//~/\\~})"
    set +f

    unset   IUSE   DEPEND   RDEPEND   CDEPEND   PDEPEND
    unset E_IUSE E_DEPEND E_RDEPEND E_CDEPEND E_PDEPEND

    if [ ! -f "${EBUILD}" ]; then
        echo "bailing, ebuild not found at '$EBUILD'"
        die "EBUILD=${EBUILD}; problem is, it doesn't exist.  bye." >&2
    fi

#	eval "$(cat "${EBUILD}"; echo ; echo 'true')" || die "error sourcing ebuild"
    source "${EBUILD}"
    if [ "${EBUILD_PHASE}" != "depend" ]; then
        RESTRICT="${PORTAGE_RESTRICT}"
        unset PORTAGE_RESTRICT
    fi

    [ -z "${ERRORMSG}" ] || die "${ERRORMSG}"

    hasq nostrip ${RESTRICT} && export DEBUGBUILD=1

    #a reasonable default for $S
    if [ "$S" = "" ]; then
        export S=${WORKDIR}/${P}
    fi

    #some users have $TMP/$TMPDIR to a custom dir in their home ...
    #this will cause sandbox errors with some ./configure
    #scripts, so set it to $T.
    export TMP="${T}"
    export TMPDIR="${T}"

    # Note: this next line is not the same as export RDEPEND=${RDEPEND:-${DEPEND}}
    # That will test for unset *or* NULL ("").  We want just to set for unset...

    #turn off glob expansion from here on in to prevent *'s and ? in the DEPEND
    #syntax from getting expanded :)  Fixes bug #1473
#	set -f
    if [ "${RDEPEND-unset}" == "unset" ]; then
        export RDEPEND="${DEPEND}"
        debug-print "RDEPEND: not set... Setting to: ${DEPEND}"
    fi

    #add in dependency info from eclasses
    IUSE="$IUSE $E_IUSE"
    DEPEND="${DEPEND} ${E_DEPEND}"
    RDEPEND="$RDEPEND $E_RDEPEND"
    CDEPEND="$CDEPEND $E_CDEPEND"
    PDEPEND="$PDEPEND $E_PDEPEND"

    unset E_IUSE E_DEPEND E_RDEPEND E_CDEPEND E_PDEPEND
#	set +f

#	declare -r DEPEND RDEPEND SLOT SRC_URI RESTRICT HOMEPAGE LICENSE DESCRIPTION
#	declare -r KEYWORDS INHERITED IUSE CDEPEND PDEPEND PROVIDE
#	echo "DONT_EXPORT_FUNCS=$DONT_EXPORT_FUNCS" >&2
}

# short version.  think these should be sourced via at the daemons choice, rather then defacto.
source "${PORTAGE_BIN_PATH}/ebuild-default-functions.sh" || die "failed sourcing ebuild-default-functions.sh"
source "${PORTAGE_BIN_PATH}/isolated-functions.sh" || die "failed sourcing stripped down functions.sh"

# general func to call for phase execution.  this handles necessary env loading/dumping, and executing pre/post/dyn
# calls.
execute_phases() {
    local ret
    for myarg in $*; do
        EBUILD_PHASE="$myarg"
        MUST_EXPORT_ENV="no"
        case $EBUILD_PHASE in
        nofetch)
            init_environ
            pkg_nofetch
            ;;
        prerm|postrm|preinst|postinst|config)
            export SANDBOX_ON="0"

            if ! load_environ "${T}/environment"; then
                #hokay.  this sucks.
                ewarn 
                ewarn "failed to load env"
                ewarn "this installed pkg may not behave correctly"
                ewarn
                sleepbeep 10
            fi	

            [[ $PORTAGE_DEBUG -ge 3 ]] && set -x
            if type reinstate_loaded_env_attributes &> /dev/null; then
                reinstate_loaded_env_attributes
                unset -f reinstate_loaded_env_attributes
            fi
            [[ -n $PORTAGE_DEBUG ]] && set -x
            type -p pre_pkg_${EBUILD_PHASE} &> /dev/null && pre_pkg_${EBUILD_PHASE}
            if type -p dyn_${EBUILD_PHASE}; then
                dyn_${EBUILD_PHASE}
            else
                pkg_${EBUILD_PHASE}
            fi
            ret=0

            type -p post_pkg_${EBUILD_PHASE} &> /dev/null && post_pkg_${EBUILD_PHASE}
            [[ $PORTAGE_DEBUG -lt 2 ]] && set +x
            ;;
        clean)
            einfo "clean phase is now handled in the python side of portage."
            einfo "ebuild-daemon calls it correctly, upgrading from vanilla portage to ebd" 
            einfo "always triggers this though.  Please ignore it."
            ;;
        unpack|compile|test|install)
            if [ "${SANDBOX_DISABLED="0"}" == "0" ]; then
                export SANDBOX_ON="1"
            else
                export SANDBOX_ON="0"
            fi

            [[ $PORTAGE_DEBUG -ge 3 ]] && set -x
            if ! load_environ ${T}/environment; then
                ewarn 
                ewarn "failed to load env.  This is bad, bailing."
                die "unable to load saved env for phase $EBUILD_PHASE, unwilling to continue"
            fi
            if type reinstate_loaded_env_attributes &> /dev/null; then
#				echo "reinstating attribs" >&2
                reinstate_loaded_env_attributes
                unset -f reinstate_loaded_env_attributes
            fi
            [[ -n $PORTAGE_DEBUG ]] && set -x
            type -p pre_src_${EBUILD_PHASE} &> /dev/null && pre_src_${EBUILD_PHASE}
            dyn_${EBUILD_PHASE}
            ret=0
            type -p post_src_${EBUILD_PHASE} &> /dev/null && post_src_${EBUILD_PHASE}
            [[ $PORTAGE_DEBUG -lt 2 ]] && set +x
            export SANDBOX_ON="0"
            ;;
        setup|setup-binpkg)
            #pkg_setup needs to be out of the sandbox for tmp file creation;
            #for example, awking and piping a file in /tmp requires a temp file to be created
            #in /etc.  If pkg_setup is in the sandbox, both our lilo and apache ebuilds break.

            export SANDBOX_ON="0"

            # binpkgs don't need to reinitialize the env.
            if [ "$myarg"  == "setup" ]; then
    			[ ! -z "${DISTCC_LOG}" ] && addwrite "$(dirname ${DISTCC_LOG})"

        		local x
            	# if they aren't set, then holy hell ensues.  deal.

                [ -z "${CCACHE_SIZE}" ] && export CCACHE_SIZE="500M"
    			ccache -M ${CCACHE_SIZE} &> /dev/null
        		[[ $PORTAGE_DEBUG == 2 ]] && set -x
            	init_environ
                MUST_EXPORT_ENV="yes"
            elif ! load_environ ${T}/environment; then
                die "failed loading saved env; at ${T}/environment"
            fi

            [[ -n $PORTAGE_DEBUG ]] && set -x
            type -p pre_pkg_setup &> /dev/null && \
                pre_pkg_setup
            dyn_setup
            ret=0;
            type -p post_pkg_setup &> /dev/null && \
                post_pkg_setup
            [[ $PORTAGE_DEBUG -lt 2 ]] && set +x

            ;;
        depend)
            SANDBOX_ON="1"
            MUST_EXPORT_ENV="no"

            if [ -z "$QA_CONTROLLED_EXTERNALLY" ]; then
                enable_qa_interceptors
            fi

            init_environ

            if [ -z "$QA_CONTROLLED_EXTERNALLY" ]; then
                disable_qa_interceptors
            fi

            set -f
            [ "${DEPEND:-unset}" != "unset" ] && 		speak "key DEPEND=$(echo $DEPEND)"
            [ "${RDEPEND:-unset}" != "unset" ] && 		speak "key RDEPEND=$(echo $RDEPEND)"
            [ "$SLOT:-unset}" != "unset" ] && 			speak "key SLOT=$(echo $SLOT)"
            [ "$SRC_URI:-unset}" != "unset" ] && 		speak "key SRC_URI=$(echo $SRC_URI)"
            [ "$RESTRICT:-unset}" != "unset" ] && 		speak "key RESTRICT=$(echo $RESTRICT)"
            [ "$HOMEPAGE:-unset}" != "unset" ] && 		speak "key HOMEPAGE=$(echo $HOMEPAGE)"
            [ "$LICENSE:-unset}" != "unset" ] && 		speak "key LICENSE=$(echo $LICENSE)"
            [ "$DESCRIPTION:-unset}" != "unset" ] && 	speak "key DESCRIPTION=$(echo $DESCRIPTION)"
            [ "$KEYWORDS:-unset}" != "unset" ] && 		speak "key KEYWORDS=$(echo $KEYWORDS)"
            [ "$INHERITED:-unset}" != "unset" ] && 		speak "key INHERITED=$(echo $INHERITED)"
            [ "$IUSE:-unset}" != "unset" ] && 			speak "key IUSE=$(echo $IUSE)"
            [ "$CDEPEND:-unset}" != "unset" ] && 		speak "key CDEPEND=$(echo $CDEPEND)"
            [ "$PDEPEND:-unset}" != "unset" ] && 		speak "key PDEPEND=$(echo $PDEPEND)"
            [ "$PROVIDE:-unset}" != "unset" ] && 		speak "key PROVIDE=$(echo $PROVIDE)"
            [ "$EAPI:-unset}" != "unset" ] &&			speak "key EAPI=$(echo $EAPI)"
            set +f
            ;;
        *)
            export SANDBOX_ON="1"
            echo "Please specify a valid command: $EBUILD_PHASE isn't valid."
            echo
            dyn_help
            exit 1
            ;;
        esac

        if [ "${MUST_EXPORT_ENV}" == "yes" ]; then
            export_environ "${T}/environment"
            MUST_EXPORT_ENV="no"
        fi
        [[ $PORTAGE_DEBUG -lt 4 ]] && set +x
    done
    return ${ret:-0}
}

#echo, everything has been sourced.  now level the read-only's.
if [ "$*" != "daemonize" ]; then
    for x in ${DONT_EXPORT_FUNCS}; do
        declare -fr "$x"
    done
    unset x
fi

f="$(declare | { 
    read l; 
    while [ "${l% \(\)}" == "$l" ]; do
        echo "${l/=*}";
        read l;
    done;
    unset l
   })"

#update the don't export filters.
if [ -z "${ORIG_VARS}" ]; then
    DONT_EXPORT_VARS="${DONT_EXPORT_VARS} ${f}"
else
    DONT_EXPORT_VARS="${DONT_EXPORT_VARS} $(echo "${f}" | egrep -v "^$(gen_regex_var_filter ${ORIG_VARS})\$")"
fi
unset f

# I see no differance here...
if [ -z "${ORIG_FUNCS}" ]; then
    DONT_EXPORT_FUNCS="${DONT_EXPORT_FUNCS} $(declare -F | cut -s -d ' ' -f 3)"
else  
    DONT_EXPORT_FUNCS="${DONT_EXPORT_FUNCS} $(declare -F | cut -s -d ' ' -f 3 )"
fi
set +f

export XARGS
if [ "$(id -nu)" == "portage" ] ; then
    export USER=portage
fi
set +H -h
# if we're being src'd for our functions, do nothing.  if called directly, define a few necessary funcs.
if [ "$*" != "daemonize" ]; then

    if [ "${*/depend}" != "$*" ]; then
        speak() {
            echo "$*" >&4
        }
        declare -rf speak
    fi
    if [ -z "${NOCOLOR}" ]; then
        set_colors
    else
        unset_colors
    fi
    unset x
    execute_phases $*
    exit 0
else
    DAEMONIZED="yes"
    export DAEMONIZED
    readonly DAEMONIZED
fi
:
