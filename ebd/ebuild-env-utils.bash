# this functionality is all related to saving/loading environmental dumps for ebuilds

__regex_filter_input() {
	# We don't need to reset IFS in this context, thus skip the pop.
	local IFS='|'
	local regex="^(${*})$"
	# use egrep if possible... tis faster.
	local l ret=0
	if l=$(type -P gsed || type -P sed); then
		"${l}" -re "/${regex}/d"
		ret=$?
		[[ ${ret} != 0 ]] && die "got failing return code (${ret}) invoking ${l} -e '/${regex}/d'"
	elif l=$(type -P egrep); then
		# use type -p; qa_interceptors may be active.
		"${l}" -v "${regex}"
		ret=$?
		# return status is 1 for no matches and 2 for errors
		[[ ${ret} -gt 1 ]] && die "got failing return code (${ret}) ${l} -v '${regex}'"
		ret=0 # reset the return status if there are no matches, it isn't an error
	else
		while read l; do
			[[ ${l} =~ ${regex} ]] || echo "${l}"
		done
	fi
	return ${ret}
}

__escape_regex_array() {
	local __tmp_array
	# Need to get the content of the original array...
	eval "__tmp_array=( \"\${$1[@]}\" )"
	__tmp_array=( "${__tmp_array[@]//\+/\\+}" )
	__tmp_array=( "${__tmp_array[@]//\./\\.}" )
	__tmp_array=( "${__tmp_array[@]//\*/\\*}" )
	# Now transfer the content back.
	eval $1='( "${__tmp_array[@]}" )'
} &> /dev/null

__filter_env() {
	local opts
	[[ ${PKGCORE_DEBUG} -ge 1 ]] && opts="--debug"
	__ebd_ipc_cmd "filter_env" "${opts}" "$@"
}

# selectively saves the environ- specifically removes things that have been marked to not be exported.
# dump the environ to stdout.
__environ_dump() {
	__shopt_push -f

	# dump variables first so no local variables get picked up
	local exported_vars=( $(compgen -v | __regex_filter_input ${PKGCORE_BLACKLIST_VARS[@]}) )
	if [[ ${#exported_vars[@]} -ne 0 ]]; then
		declare -p "${exported_vars[@]}" || die "failed outputting env vars ${exported_vars[@]}"
	fi

	local func_filters=( "${PKGCORE_BLACKLIST_FUNCS[@]}" ${PKGCORE_EAPI_FUNCS} "${PKGCORE_PRELOADED_ECLASSES[@]}" )

	# Punt any regex chars...
	__escape_regex_array func_filters
	local exported_funcs=( $(compgen -A function | __regex_filter_input "${func_filters[@]}" ) )
	if [[ ${#exported_funcs[@]} -ne 0 ]]; then
		declare -f "${exported_funcs[@]}" || die "failed outputting funcs ${exported_funcs[@]}"
	fi

	__shopt_pop
}

# dump environ to $1, optionally piping it through $2 and redirecting $2's output to $1.
__environ_save_to_file() {
	if [[ $# -ne 1 && $# -ne 2 ]]; then
		die "${FUNCNAME}: requires at least one argument, two max; got $@"
	fi

	if [[ $# -eq 1 ]]; then
		__environ_dump > "$1"
	else
		__environ_dump | $2 > "$1"
	fi
	chown portage:portage "$1" &> /dev/null
	chmod 0664 "$1" &> /dev/null
}

# reload a saved env, applying usual filters to the env prior to eval'ing it.
__environ_sanitize_saved_env() {
	if [[ $# -ne 1 ]]; then
		die "scrub_environ called with wrong args, only one can be given: $@"
	fi

	[[ ! -f $1 ]] && die "${FUNCNAME}: called with a nonexist env: $1"

	# here's how this goes; we do an eval'd loadup of the target env w/in a subshell..
	# declares and such will slide past filter-env (so it goes).  we then use our own
	# __environ_dump from within to get a clean dump from that env, and load it into
	# the parent eval.
	(
		# protect the core vars and functions needed to do a __environ_dump
		# some of these are already readonly- we still are forcing it to be safe.
		readonly PKGCORE_EXISTING_PATH SANDBOX_ON T
		readonly -a PKGCORE_BLACKLIST_VARS PKGCORE_BLACKLIST_FUNCS
		readonly -f __filter_env __environ_dump __regex_filter_input

		__shopt_push -f
		IFS=$' \t\n'
		declare -a PKGCORE_FUNC_ARRAY=( "${PKGCORE_BLACKLIST_FUNCS[@]}" )
		declare -a PKGCORE_VAR_ARRAY=( "${PKGCORE_BLACKLIST_VARS[@]}" )
		IFS=,
		PKGCORE_FUNC_ARRAY=${PKGCORE_FUNC_ARRAY[*]}
		PKGCORE_VAR_ARRAY=${PKGCORE_VAR_ARRAY[*]}
		IFS=$' \t\n'
		__shopt_pop

		rm -f "${T}"/.pre-scrubbed-env || die "failed rm'ing"
		# run the filtered env.
		__filter_env \
			--funcs "${PKGCORE_FUNC_ARRAY}" \
			--vars "${PKGCORE_VAR_ARRAY}" \
			"$1" "${T}"/.pre-scrubbed-env \
			|| die "failed first step of scrubbing the env to load"

		[[ -s ${T}/.pre-scrubbed-env ]] || die "empty pre-scrubbed-env file, pkgcore bug?"
		source "${T}"/.pre-scrubbed-env >&2 || die "failed sourcing scrubbed env"

		# ok. it's loaded into this subshell... now we use our dump mechanism (which we trust)
		# to output it- this mechanism is far more bulletproof then the load filtering (since
		# declare and friends can set vars via many, many different ways), thus we use it
		# as the final filtering.
		rm -f "${T}"/.scrubbed-env
		__environ_dump > "${T}"/.scrubbed-env || die "dumping environment failed"
	) && return

	echo "die 'failed parsing the env dump'" # yep, we're injecting code into the eval.
	exit 1
	# note no die usage here... exit instead, since we don't want another tb thrown
}

:
