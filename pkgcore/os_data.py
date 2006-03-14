# Copyright: 2005 Gentoo Foundation
# License: GPL2

import os,pwd,grp

ostype=os.uname()[0]

lchown = None
if ostype=="Linux":
	userland="GNU"
	xargs = os.environ["XARGS"]="xargs -r"
elif ostype == "Darwin":
	userland="Darwin"
	os.environ["XARGS"]="xargs"
	def lchown(*pos_args, **key_args):
		pass
elif ostype in ["FreeBSD","OpenBSD","NetBSD"]:
	userland="BSD"
	xargs = os.environ["XARGS"]="xargs"
else:
	raise Exception("Operating system unsupported, '%s'" % ostype)

if not lchown:
	if "lchown" in dir(os):
		# Included in python-2.3
		lchown = os.lchown
	else:
		import missingos
		lchown = missingos.lchown


	
#os.environ["USERLAND"]=userland

#Secpass will be set to 1 if the user is root or in the portage group.
secpass=0

uid=os.getuid()
# hard coding sucks.
root_uid = 0
wheelgid = 0

if uid==0:
	secpass=2
try:
	wheelgid=grp.getgrnam("wheel")[2]
	if (not secpass) and (wheelgid in os.getgroups()):
		secpass=1
except KeyError:
	print "portage initialization: your system doesn't have a 'wheel' group."
	print "Please fix this as it is a normal system requirement. 'wheel' is GID 10"
	print "'emerge baselayout' and an 'etc-update' should remedy this problem."

#Discover the uid and gid of the portage user/group
try:
	portage_uid=pwd.getpwnam("portage")[2]
	portage_gid=grp.getgrnam("portage")[2]
	if (secpass==0):
		secpass=1
except KeyError:
	portage_uid=0
	portage_gid=wheelgid
	print 
	print "portage: 'portage' user or group missing. Please update baselayout"
	print "         and merge portage user(250) and group(250) into your passwd"
	print "         and group files. Non-root compilation is disabled until then."
	print "         Also note that non-root/wheel users will need to be added to"
	print "         the portage group to do portage commands.\n"
	print "         For the defaults, line 1 goes into passwd, and 2 into group."
	print "         portage:x:250:250:portage:/var/tmp/portage:/bin/false"
	print "         portage::250:portage"

if (uid!=0) and (portage_gid not in os.getgroups()):
	if not os.environ.has_key("PORTAGE_SCRIPT"):
		print "*** You are not in the portage group. You may experience cache problems"
		print "*** due to permissions preventing the creation of the on-disk cache."
		print "*** Please add this user to the portage group if you wish to use portage."

