# Install destination commands

into() {
	${PKGCORE_PREFIX_SUPPORT} || local ED=${D}
	if [[ $1 == "/" ]]; then
		export PKGCORE_DESTTREE=""
	else
		export PKGCORE_DESTTREE=$1
	fi

	# only EAPI <= 6 supports DESTTREE
	${PKGCORE_HAS_DESTTREE} && export DESTTREE=${PKGCORE_DESTTREE}
}

insinto() {
	${PKGCORE_PREFIX_SUPPORT} || local ED=${D}
	if [[ $1 == "/" ]]; then
		export PKGCORE_INSDESTTREE=""
	else
		export PKGCORE_INSDESTTREE=$1
	fi

	# only EAPI <= 6 supports DESTTREE
	${PKGCORE_HAS_DESTTREE} && export INSDESTTREE=${PKGCORE_INSDESTTREE}
}

exeinto() {
	${PKGCORE_PREFIX_SUPPORT} || local ED=${D}
	if [[ $1 == "/" ]]; then
		export PKGCORE_EXEDESTTREE=""
	else
		export PKGCORE_EXEDESTTREE=$1
	fi
}

docinto() {
	${PKGCORE_PREFIX_SUPPORT} || local ED=${D}
	if [[ $1 == "/" ]]; then
		export PKGCORE_DOCDESTTREE=""
	else
		export PKGCORE_DOCDESTTREE=$1
	fi
}

# Install options commands

insopts() {
	{ has -s "$@" || has --strip "$@"; } && \
		ewarn "insopts shouldn't be given -s; stripping should be left to the manager."
	export INSOPTIONS=$@
}

diropts() {
	export DIROPTIONS=$@
}

exeopts() {
	{ has -s "$@" || has --strip "$@"; } && \
		ewarn "exeopts shouldn't be given -s; stripping should be left to the manager."
	export EXEOPTIONS=$@
}

libopts() {
	{ has -s "$@" || has --strip "$@"; } && \
		ewarn "libopts shouldn't be given -s; stripping should be left to the manager."
	export LIBOPTIONS=$@
}
