#!/usr/bin/env bash
#
# Test pkgcore upgrading between releases. Currently requires sudo, curl, git,
# and pychroot to be installed.
#
# Usage: upgrade.sh [starting snakeoil version] [starting pkgcore version] \
#	[upgrading snakeoil version] [upgrading pkgcore version]
#
# TODO:
#	* use local git repos instead of re-cloning them for git upgrades
#	* get rid of sudo usage
#	* use custom, minimized stage3 tarballs

SNAKEOIL_ORIG=${1:-0.6.4}
PKGCORE_ORIG=${2:-0.9.1}
SNAKEOIL_NEW=${3:-9999}
PKGCORE_NEW=${4:-9999}
BUILD_LOG=/tmp/pkgcore.log

CHROOT=$(mktemp -p /tmp -d chroot-XXXXXX)
SNAKEOIL_PATH=/home/test/snakeoil
PKGCORE_PATH=/home/test/pkgcore
GENTOO=/var/gentoo/repos/gentoo
STAGE3=$(curl -Ss https://distfiles.gentoo.org/releases/amd64/autobuilds/latest-stage3-amd64-nomultilib.txt | awk '/^[^#]/ {print $1}')

# wipe chroot on exit
cleanup() {
	sudo rm -rf "${CHROOT}"
}
trap cleanup EXIT

curl "https://distfiles.gentoo.org/releases/amd64/autobuilds/${STAGE3}" | tar -jx -C "${CHROOT}" 2>/dev/null
chmod 777 "${CHROOT}"/tmp

# Done after untarring to ignore previous permission errors when unpacking
# devices nodes. The host's devfs gets mounted over the chroot anyway.
set -e

git clone https://github.com/pkgcore/snakeoil.git "${CHROOT}${SNAKEOIL_PATH}"
git clone https://github.com/pkgcore/pkgcore.git "${CHROOT}${PKGCORE_PATH}"
git clone --depth 1 https://github.com/gentoo-mirror/gentoo.git "${CHROOT}${GENTOO}"

pushd "${CHROOT}${SNAKEOIL_PATH}" >/dev/null
git checkout v${SNAKEOIL_ORIG}
popd >/dev/null
pushd "${CHROOT}${PKGCORE_PATH}" >/dev/null
git checkout v${PKGCORE_ORIG}
popd >/dev/null

ln -sfn "${GENTOO}"/profiles/default/linux/amd64/13.0/no-multilib "${CHROOT}"/etc/portage/make.profile
rm -rf "${CHROOT}"/usr/portage
ln -sfn "${GENTOO}" "${CHROOT}"/usr/portage

cat <<-EOF >"${CHROOT}"/etc/portage/package.accept_keywords
	dev-python/snakeoil ~amd64 **
	sys-apps/pkgcore ~amd64 **
EOF

cat <<-EOF >"${CHROOT}"/etc/portage/package.use/git
	dev-vcs/git -gpg -perl -webdav
EOF

# drop sudo when network namespacing is added for non-root users
sudo pychroot "${CHROOT}" bash -c "
	set -e
	eselect python set python2.7
	pushd ${PKGCORE_PATH}/bin >/dev/null
	PYTHONPATH=${SNAKEOIL_PATH} ./pmerge \=dev-python/snakeoil-${SNAKEOIL_ORIG} >> ${BUILD_LOG}
	./pmerge \=sys-apps/pkgcore-${PKGCORE_ORIG} >> ${BUILD_LOG}
	echo BOOTSTRAP: snakeoil-${SNAKEOIL_ORIG} pkgcore-${PKGCORE_ORIG} | tee -a ${BUILD_LOG}
	popd >/dev/null

	pmerge -1 \=dev-python/snakeoil-${SNAKEOIL_ORIG} \=sys-apps/pkgcore-${PKGCORE_ORIG} >> ${BUILD_LOG}
	echo REINSTALL: snakeoil-${SNAKEOIL_ORIG} pkgcore-${PKGCORE_ORIG} | tee -a ${BUILD_LOG}
	pmerge -1 \=dev-python/snakeoil-${SNAKEOIL_NEW} \=sys-apps/pkgcore-${PKGCORE_NEW} >> ${BUILD_LOG}
	echo UPGRADE: snakeoil-${SNAKEOIL_NEW} pkgcore-${PKGCORE_NEW} | tee -a ${BUILD_LOG}
"
