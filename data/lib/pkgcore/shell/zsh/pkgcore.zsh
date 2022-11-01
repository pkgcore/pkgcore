# Common library of shell functions for parsing various Gentoo-related data
# and leveraging pkgcore functionality.

# get an attribute for a given package
_pkgattr() {
	local prog=$(_get_caller)
	local pkg_attr=$1 pkg_atom=$2 repo=$3
	local ret=0 pid fdout fderr
	local -a pkg error

	if [[ -z ${pkg_atom} ]]; then
		echo "${prog}: enter a valid package name or repo path" >&2
		return 1
	fi

	# setup pipes for stdout/stderr capture
	local tmpdir=$(mktemp -d)
	trap "rm -rf '${tmpdir}'" EXIT HUP INT TERM
	mkfifo "${tmpdir}"/{stdout,stderr}

	if [[ -n ${repo} ]]; then
		pquery -r "${repo}" --raw --unfiltered --cpv -R --one-attr "${pkg_attr}" \
			-n -- "${pkg_atom}" >"${tmpdir}"/stdout 2>"${tmpdir}"/stderr &
	else
		pquery --ebuild-repos --raw --unfiltered --cpv -R --one-attr "${pkg_attr}" \
			-n -- "${pkg_atom}" >"${tmpdir}"/stdout 2>"${tmpdir}"/stderr &
	fi

	# capture pquery stdout/stderr into separate vars
	pid=$!
	exec {fdout}<"${tmpdir}"/stdout {fderr}<"${tmpdir}"/stderr
	rm -rf "${tmpdir}"
	pkg=("${(@f)$(<&${fdout})}")
	error=("${(@f)$(<&${fderr})}")
	wait ${pid}
	ret=$?
	exec {fdout}<&- {fderr}<&-

	if [[ ${ret} != 0 ]]; then
		# re-prefix the main pquery error message with the shell function name
		echo "${prog}: ${error[1]#pquery: error: }" >&2
		# output the remaining portion of the error message
		local line
		for line in "${error[@]:1}"; do
			echo -E "${line}" >&2
		done
		return 1
	fi

	local choice
	if [[ -z ${pkg[@]} ]]; then
		echo "${prog}: no matches found: ${pkg_atom}" >&2
		return 1
	elif [[ ${#pkg[@]} > 1 ]]; then
		echo "${prog}: multiple matches found: ${pkg_atom}" >&2
		choice=$(_choose "${pkg[@]%%|*}")
		[[ $? -ne 0 ]] && return 1
	else
		choice=-1
	fi
	echo ${pkg[${choice}]#*|}
}

# get the caller of the current function
_get_caller() {
	echo ${${funcstack[-1]}:t}
}

# cross-shell compatible PATH searching
_which() {
	whence -p "$1" >/dev/null
}

# cross-shell compatible read num chars
_read_nchars() {
	local var
	read -k $1 var
	echo ${var}
}

# cross-shell compatible array index helper
# zsh arrays start at 1
_array_index() {
	index=$1
	echo $(( ++index ))
}

## Completion related functions ##

# configured repo info
#
# Note that this only supports the repos.conf format,
# PORTDIR/PORTDIR_OVERLAY in make.conf are not supported.
#
# optional args:
#  -t repo_types -- show specific repo types (defaults to showing source repos)
#    The repo_types parameter can be any of the following characters in combination:
#      e: package.provided "repo"
#      i: vdb "repo"
#      s: all source repos (default if the -t option isn't passed)
#      b: all binary repos
#      a: repo-stack "repo"
#    For example, `_repos -t sbi` will return the list of source, binary, and
#    installed repos.
#  -v section:key
#  -p print the output instead of using completion
#  -l use repo locations instead of repo_ids
_repos() {
	typeset -A opts
	zparseopts -E -A opts t: l p v:

	local repo_name output_type
	typeset -a repos repo_types output

	# verify selected repo types
	if [[ -n ${opts[(I)-t]} ]]; then
		local -a supported_repo_types=(e i s b a)
		repo_types=(${(s::)opts[-t]})
		for type in ${repo_types[@]}; do
			if [[ ! ${type} =~ [${supported_repo_types[@]}] ]]; then
				echo "${funcstack[1]}: invalid repo type: ${type}" >&2
				echo "supported types: ${supported_repo_types[@]} (see docs)" >&2
				return 1
			fi
		done
	else
		# default to showing source repos
		repo_types=(s)
	fi

	if [[ -e /etc/portage/repos.conf ]]; then
		repos_conf_files=( /etc/portage/repos.conf /etc/portage/repos.conf/** )
	else
		repos_conf_files=( /usr/share/pkgcore/config/repos.conf )
	fi

	IFS='= '

	local file
	for file in "${repos_conf_files[@]}"; do
		[[ -f ${file} ]] || continue
		while read -r name value; do
			# skip comments and empty lines
			[[ -z ${name} || ${name} == '#'* ]] && continue
			if [[ (${name} == '['*']') && -z ${value} ]]; then
				repo_name=${name//[\[\]]}
				[[ ${repo_name} != "DEFAULT" ]] && repos+=(${repo_name})
				typeset -A ${repo_name}
			else
				eval "${repo_name}[${name}]=\"${value}\""
			fi
		done < ${file}
	done

	if [[ -n ${opts[(I)-v]} ]]; then
		section=${opts[-v]%%:*}
		value=${opts[-v]##*:}
		eval "output=\${${section}[${value}]}"
	elif [[ -n ${opts[(I)-l]} ]]; then
		# repo paths
		output_type="repo paths"
		for repo in ${repos[@]}; do
			eval "output+=(\${${repo}[location]})"
		done
	else
		# repo names
		output_type="repos"

		[[ ${repo_types} =~ "s" ]] && output+=(${repos[@]})
		[[ ${repo_types} =~ "e" ]] && output+=( provided )
		[[ ${repo_types} =~ "i" ]] && output+=( vdb )
		[[ ${repo_types} =~ "b" ]] && output+=( binpkg )
		[[ ${repo_types} =~ "a" ]] && output+=( repo-stack )
	fi

	if [[ -n ${compstate} ]] && [[ -z ${opts[(I)-p]} ]]; then
		_describe -t repos ${output_type} output
	else
		print ${output}
	fi
}

# available licenses
#
# optional args:
#  -r repo  specify the repo to use; otherwise the default repo is used
#  -p       print the output instead of using completion
_licenses() {
	typeset -A opts
	zparseopts -E -A opts p r:

	typeset -a licenses

	if [[ -n ${opts[(I)-r]} ]]; then
		repo=${opts[-r]}
	else
		repo=$(_repos -p -v DEFAULT:main-repo)
	fi

	repo_path=${$(_repos -p -v "${repo}:location")%/}
	licenses=("${repo_path}"/licenses/*(.:t))

	if [[ -n ${compstate} ]] && [[ -z ${opts[(I)-p]} ]]; then
		_describe -t licenses 'licenses' licenses
	else
		print ${licenses}
	fi
}

# global/local USE flag info
#
# optional args
#  -r repo  specify the repo to use; otherwise the default repo is used
#  -p       print the output instead of using completion
#  -g       only show global use flags
#  -l       only show local use flags
#  -o       don't show use flag descriptions
_use() {
	typeset -A opts
	zparseopts -E -A opts o p r:

	local desc
	typeset -a use use_global use_local

	if [[ -n ${opts[(I)-r]} ]]; then
		repo=${opts[-r]}
	else
		repo=$(_repos -p -v DEFAULT:main-repo)
	fi

	repo_path=${$(_repos -p -v "${repo}:location")%/}
	[[ -f ${repo_path}/profiles/use.desc ]] && use_global=(${(S)${${(f)"$(<${repo_path}/profiles/use.desc)"}:#\#*}/ - /:})
	[[ -f ${repo_path}/profiles/use.local.desc ]] && use_local=(${(S)${(S)${${(f)"$(<${repo_path}/profiles/use.local.desc)"}:#\#*}/*:/}/ - /:})

	if [[ -z ${opts[(I)-g]} && -z ${opts[(I)-l]} ]]; then
		# both global and local use flags are shown by default
		use=( ${use_global} ${use_local} )
	elif [[ -n ${opts[(I)-g]} ]]; then
		use=${use_global}
		desc='global '
	elif [[ -n ${opts[(I)-l]} ]]; then
		use=${use_local}
		desc='local '
	fi

	# strip use flag descriptions
	if [[ -n ${opts[(I)-o]} ]]; then
		use=(${^use/:*/})
	fi

	if [[ -n ${compstate} ]] && [[ -z ${opts[(I)-p]} ]]; then
		_describe -t use "${desc}use flag" use
	else
		print ${use}
	fi
}

# package categories provided by repos
#
# optional args
#  -r repo  specify the repo to use; otherwise the default repo is used
#  -p       print the output instead of using completion
_categories() {
	typeset -A opts
	zparseopts -E -A opts p r:

	typeset -a categories

	if [[ -n ${opts[(I)-r]} ]]; then
		repo=${opts[-r]}
	else
		repo=$(_repos -p -v DEFAULT:main-repo)
	fi

	repo_path=${$(_repos -p -v "${repo}:location")%/}
	[[ -f ${repo_path}/profiles/categories ]] && categories=(${${(f)"$(<${repo_path}/profiles/categories)"}:#\#*})

	if [[ -n ${compstate} ]] && [[ -z ${opts[(I)-p]} ]]; then
		_describe -t categories 'categories' categories
	else
		print ${categories}
	fi
}

# arches provided by repos
#
# optional args
#  -r repo  specify the repo to use; otherwise the default repo is used
#  -p       print the output instead of using completion
_arches() {
	typeset -A opts
	zparseopts -E -A opts p r:

	typeset -a arches

	if [[ -n ${opts[(I)-r]} ]]; then
		repo=${opts[-r]}
	else
		repo=$(_repos -p -v DEFAULT:main-repo)
	fi

	repo_path=${$(_repos -p -v "${repo}:location")%/}
	[[ -f ${repo_path}/profiles/arch.list ]] && arches=(${${(f)"$(<${repo_path}/profiles/arch.list)"}:#\#*})

	if [[ -n ${compstate} ]] && [[ -z ${opts[(I)-p]} ]]; then
		_describe -t arches 'arches' arches
	else
		print ${arches}
	fi
}

# profiles provided by repos
#
# optional args
#  -r repo  specify the repo to use; otherwise the default repo is used
#  -p       print the output instead of using completion
#  -f       output full, absolute profile paths
_profiles() {
	typeset -A opts
	zparseopts -E -A opts a p f r:

	local file repo repo_path arch path pstatus
	typeset -a profiles

	if [[ -n ${opts[(I)-r]} ]]; then
		repo=${opts[-r]}
	else
		repo=$(_repos -p -v DEFAULT:main-repo)
	fi

	repo_path=${$(_repos -p -v "${repo}:location")%/}
	file=${repo_path}/profiles/profiles.desc

	if [[ -f ${file} ]]; then
		while read -r arch path pstatus; do
			# skip comments and empty lines
			[[ -z ${arch} || ${arch} == '#'* ]] && continue
			[[ -n ${opts[(I)-f]} ]] && path=${repo_path}/profiles/${path}
			profiles+=(${path})
		done < ${file}
	fi

	if [[ -n ${compstate} ]] && [[ -z ${opts[(I)-p]} ]]; then
		_describe -t profiles 'profiles' profiles $*
	else
		print ${profiles}
	fi
}
