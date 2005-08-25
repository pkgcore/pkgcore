#!/bin/bash
# Copyright 1999-2004 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2
# $Id: portage_gpg_update.sh 1912 2005-08-25 03:54:42Z ferringb $

wget -O - http://www.gentoo.org/proj/en/devrel/roll-call/userinfo.xml | sed 's:.*\(0x[0-9a-fA-F]\+\)[^0-9a-fA-F].*:\1:gp;d' | xargs gpg -vvv --no-default-keyring  --no-permission-warning --homedir /usr/portage/metadata --keyring "gentoo.gpg" --keyserver subkeys.pgp.net --recv-keys &> gpg.log
