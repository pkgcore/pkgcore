#!/usr/bin/python -O
# Copyright 1999-2004 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2
# $Header$

import os,sys,string
sys.path = ["/usr/lib/portage/pym"]+sys.path

import portage

os.chdir(portage.root+portage.VDB_PATH)
myvirts=portage.grabdict(portage.root+"var/cache/edb/virtuals")
mypvirts={}
if portage.profiledir:
	mypvirts=portage.grabdict(portage.profiledir+"/virtuals")
mydict={}
myvalidargs=[]
origkey={}
for x in sys.argv[1:]:
	myparts=string.split(x,"/")
	x=myparts[1]+"/"+myparts[2]
	try:
		myfile=open(x+"/VIRTUAL","r")
	except SystemExit, e:
		raise # Needed else the app won't quit
	except:
		continue
	myline=myfile.readline()
	mykey=string.join(string.split(myline))
	if portage.isspecific(x):
		mysplit=portage.portage_versions.catpkgsplit(x)
		newkey=mysplit[0]+"/"+mysplit[1]
		origkey[newkey]=x
		x=newkey
	else:
		origkey[x]=x
	if portage.isspecific(mykey):
		mysplit=portage.portage_versions.catpkgsplit(mykey)
		mykey=mysplit[0]+"/"+mysplit[1]
	myvalidargs.append(x)
	mydict[x]=mykey
for x in mydict.keys():
	if mypvirts.has_key(x) and len(mypvirts[x])>=1 and mypvirts[x][0]==mydict[x]:
		#this is a default setting; don't record
		continue
	if myvirts.has_key(x):
		if mydict[x] not in myvirts[x]:
			myvirts[x][0:0]=[mydict[x]]
	else:
		myvirts[x]=[mydict[x]]
print ">>> Database upgrade..."
print ">>> Writing out new virtuals file..."
portage.writedict(myvirts,portage.root+"var/cache/edb/virtuals")
if not os.path.exists("/tmp/db-upgrade-bak"):
	os.mkdir("/tmp/db-upgrade-bak")
print ">>> Backing up to /tmp/db-upgrade-bak..."
for myarg in myvalidargs:
	print ">>> Backing up",portage.root+portage.VDB_PATH+"/"+origkey[myarg]
	os.system("mv "+portage.root+portage.VDB_PATH+"/"+origkey[myarg]+" /tmp/db-upgrade-bak")
print ">>> Done."
