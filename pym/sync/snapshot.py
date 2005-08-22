# snapshot.py; provides the capability of fetching a portage tree snapshot, and syncing a tree with it.
# Copyright 2004 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2
#$Header$

import os
import time
import portage_checksum, portage_exec
import shutil
import sync.rsync

"""snapshot-http://gentoo.chem.wisc.edu/gentoo"""
class SnapshotHost:
	def __init__(self,host_uri,snapshots_dir,tmp_dir,fetcher=None,use_md5=True):
		if fetcher==None:
			import transports.bundled_lib
			fetcher=transports.bundled_lib.BundledConnection()
		self.__fetcher=fetcher
		self.__host_uri=host_uri
		self.__tmpdir = tmp_dir
		self.__snapshots_dir = snapshots_dir
		self.__use_md5 = use_md5

	def sync(self, local_path,verbosity=1):
		attempts=0
		downloaded=False
		while attempts < 40 and not downloaded:
			file="portage-%s.tar.bz2" % time.strftime("%Y%m%d",
				time.localtime(time.time() - (attempts*24*60*60)))
			loc=self.__snapshots_dir+"/"+file
			rem=self.__host_uri+"/"+file
			downloaded=self.__fetch_snapshot(file,loc,rem,verbosity)
			attempts += 1

		if not downloaded:
			# no snapshot, no syncy-poo.
			return False

		return self.__apply_snapshot(loc,local_path,verbosity)

	def __apply_snapshot(self,snapshot,local_tree,verbosity):
		"""apply the actual snapshot.  for different methods of this, inherit this class
		and overload this function
		current it untars to a temp location, and rsync's it over to local_path."""

		#this should be checked
		portage_exec.spawn(("tar","-jxf",snapshot,"-C",self.__tmpdir))
		syncer=sync.rsync.RsyncHost("%s/portage/" % self.__tmpdir,local_host=True)
		try:
			ret = syncer.sync({},local_tree,excludes=("/distfiles","/local","/packages"),verbosity=verbosity)
		except sync.rsync.RSyncSyntaxError,e:
			print "caught rsync syntax exception:",e
			return False
		except IOError, ie:
			print "issue: ",ie
			return False
		if verbosity:
			print "cleaning tempoary snapshot directory- %s/portage" % self.__tmpdir
		shutil.rmtree(self.__tmpdir+"/portage")

		#nuke all other return codes.
		if ret != True:
			return False
		return ret

	def __fetch_snapshot(self,file,loc,rem,verbosity):
		grab_md5=True
		hash=None
		md5=None
		md5_existed=False
		ret=False
		if self.__use_md5 and os.path.exists(loc+".md5sum"):
			hash=self.__read_md5sum(loc+".md5sum")
			if hash==None:
				os.remove(loc+".md5sum")
			else:
				md5_existed=True
				grab_md5=False

		if self.__use_md5 and grab_md5:
			ret=self.__fetcher.fetch(rem+".md5sum",file_name=loc+".md5sum",verbose=(verbosity==1))
			if not ret:
				hash=self.__read_md5sum(loc+".md5sum")

		if ret:
			if verbosity:
				print "!!! failed to fetch md5 for %s" % file
				return False

		# at this point we have the md5, and know the image *should* exist.
		ret = False
		if os.path.exists(loc):
			if self.__use_md5:
				md5=portage_checksum.perform_md5(loc)
			if hash == md5 or not self.__use_md5:
				if verbosity:
					print ">>> reusing %s" % loc
					return True
			else:
				if verbosity:
					print ">>> resuming %s" % rem
				ret=self.__fetcher.resume(rem,file_name=loc,verbose=(verbosity==1))
		else:
			if verbosity:
				print ">>> fetching %s" % rem
				ret=self.__fetcher.fetch(rem,file_name=loc,verbose=(verbosity==1))
			
		if ret:
			if verbosity:
				print "!!! failed %s" % file
			return False

		if self.__use_md5 and md5==None:
			md5=portage_checksum.perform_md5(loc)

		if self.__use_md5 and md5_existed and md5!= hash:
			print ">>> re-grabbing the hash"
			# grab the md5 anew to be safe.
			os.remove(loc+".md5sum")
			if not self.__fetcher.fetch(rem+".md5sum",file_name=loc+".md5sum",verbose=True):
				hash=self.__read_md5sum(loc+".md5sum")

		if md5!=hash and self.__use_md5:
			if verbosity:
				print "!!! snapshots correct md5: %s" % hash
				print "!!! snapshots actual md5 : %s" % md5
				print "!!! cycling to next candidate."
				print
				return False
		# if this point has been reached, things are sane.
		return True
		

	def __read_md5sum(self,file):
		try:
			myf=open(file,"r")
			hash=myf.readline().split()[0]
			if len(hash)!=32:
				return None
			return hash
		except (OSError,IOError,IndexError),e:
			print e
			return None
