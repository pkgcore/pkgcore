"""list based, symlink aware fs listdir caching implementation"""
import os,stat,weakref

def norm_path(mypath):
	newpath = os.path.normpath(mypath)
	if len(mypath) > 1:
		if newpath[:2] == "//":
			newpath=newpath.replace("//","/")
	return newpath

def abs_link(sym):
	# note this doesn't parse every single entry.  that's up to you.
	l=os.readlink(sym)
	if l[0] != '/':
		l = os.path.dirname(sym)+"/"+l
	return norm_path(l)

class node:
	"""class representing a directory"""
	__slots__=["dir_node_name","dir_node_ref","dirs","files","others","sdirs","sfiles","mtime"]
#	instances = 0
	def __init__(self):#,dirs=[],others=[],files=[],mtime=-1):
		self.dir_node_ref=[]
		self.dir_node_name=[]
		self.dirs=[]
		self.files=[]
		self.others=[]
		self.sdirs=[]
		self.sfiles=[]
		self.mtime=-1

#	def __del__(self):
#		print "del'ing a node"
#		del self.dir_node_n
#		del self.sdirs
#		del self.sfiles
#		del self.dirs
#		del self.files
#		del self.others
#		del self.mtime

	def get_node(self,nnode):
		"""retrieve directory node if exists"""
		try:	
			x=self.dir_node_name.index(nnode)
			return self.dir_node_ref[x]
		except (ReferenceError,ValueError),e :
#			print "ref exception",e
			return None

	def add_node(self,nnode,ref_node=None,symlink=False):
		self.dir_node_name.append(nnode)
		if ref_node:
			if symlink:
				self.dir_node_ref.append(weakref.proxy(ref_node))
			else:
				self.dir_node_ref.append(ref_node)
		else:
			self.dir_node_ref.append(node())
		return self.dir_node_ref[-1]

	def del_node(self,nnode):
		try:
			x=self.dir_node_name.index(nnode)
			del self.dir_node_name[x]
			del self.dir_node_ref[x]
		except Exception,e:
			print "warning, dcache was asked to delete a non_existant node: lacks node %s" % nnode
			print "e=",e
	
	def rec_del_node(self):
		while len(self.dir_node_n):
			self.dir_node_name[0].rec_del_node()
			del self.dir_node_name[0][0]
			del self.dir_node_ref[0]

class dcache:
	def __init__(self):
		self.cache=node()

	def _get_dir_ent(self, mypath,symlink=False):
		p=mypath.split("/")
		if not p[0]:
			p = p[1:]
		if not p[-1]:
			p = p[0:-1]
		fullpath=''
		c = self.cache
		if not len(p):
			return self.cache
		while len(p):
			fullpath += '/' + p[0]

			g=c.get_node(p[0])
			if not g:
				st=os.lstat(fullpath)
				if stat.S_ISLNK(st.st_mode):
					# yippee
					fullpath=abs_link(fullpath)
#					print "hijacking %s to %s" % (p[0], fullpath)
					g=self._get_dir_ent(fullpath)
					g=c.add_node(p[0],ref_node=self._get_dir_ent(fullpath))
				elif stat.S_ISDIR(st.st_mode):
					g=c.add_node(p[0])
				else:
					raise Exception("%s is not a dir!" % fullpath)
			c=g
			p.pop(0)
		if symlink:
			c["actpath"]=fullpath
		return c

	def cacheddir(self, mypath):
		mypath=norm_path(mypath)
		if mypath=="/":
			ent=self.cache
		else:
			ent = self._get_dir_ent(mypath)
#		print "nodes mtime=",ent.mtime
		listing_needed = (ent.mtime == -1)

		mtime = os.stat(mypath).st_mtime
		if not listing_needed:
#			print "nost listing needed"
			if mtime != ent.mtime:
				print "mtime flipped it"
				self._invalidate_dir_node(ent)
				listing_needed = True

#		print "ent = ",ent,"listing_needed=",listing_needed
		if listing_needed:
			ent.mtime=mtime
#			print "set nodes mtime to",ent.mtime,"from",mtime
			l = os.listdir(mypath)
			for x in l:
				try:
					ps=os.lstat(mypath+"/"+x).st_mode
					if stat.S_ISREG(ps):
						ent.files.append(x)
					elif stat.S_ISDIR(ps):
						ent.dirs.append(x)
					elif stat.S_ISLNK(ps):
						ps=os.stat(mypath+"/"+x).st_mode
						if stat.S_ISDIR(ps):
							ent.sdirs.append(x)
						else:
							ent.sfiles.append(x)
					else:
						ent.others.append(x)
				except:
					ent.others.append(x)
		return list(ent.dirs + ent.sdirs + ent.files + ent.sfiles + ent.others),\
			[1 for x in ent.dirs]+[3 for x in ent.sdirs]+	\
			[0 for x in ent.files]+	[2 for x in ent.sfiles]+[4 for x in ent.others]
