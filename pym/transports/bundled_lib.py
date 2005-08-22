# bundled_lib.py; implementation of a fetcher class useing httplib and ftplib.
# Copyright 2004 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2
#$Header$

import httplib, ftplib, urlparse, base64, re, sys, os

class BundledConnection:
	"""a fetcher abstraction using httplib and ftplib.
	offers api access to specify the specific window/chunk of a uri you want"""
	def __init__(self, persistant=False,chunk_size=8192,verbose=True):
		self.__persistant = persistant
		self.__chunk_size = chunk_size
		self.__verbose = verbose

		# lifting the connection caching from check_src_uri's code- combine them if possible
		self._http_conn = {}
		self._https_conn = {}
		self._ftp_conn = {}

	def __get_connection(self, uri):
		"""internal function to raid from the instances cache of connections, or return a new one"""
		proto,host,con_dict,url,hash = self.__process_uri(uri)
		cons = getattr(self,"_%s_conn" % proto)
		if not self.__persistant or not cons.has_key(hash):
			if proto in ('http','https'):
				con = httpConnection(host,**con_dict)
			else:
				con = ftpConnection(host,chunk_size=self.__chunk_size,**con_dict)
			if self.__persistant:
				cons[hash] = con
		else:
			con = cons[hash]
		return proto, con, url

	def fetch(self,uri, file_name=None,verbose=None):
		"""fetch uri, storing it in file_name"""
		if verbose==None:
			verbose=self.__verbose
		proto, con, url = self.__get_connection(uri)
		if not file_name:
			x= url.find("/")
			if x == -1:
				raise Exception,"Unable to deterimine file_name from %s" % uri
			file_name = url[x+1:]
		try:
			myf=open(file_name,"w",0)

		except (IOError, OSError), e:
			sys.stderr.write("Failed opening file %s for saving:\n%s\n" % (file_name,str(e)))
			return True
		if verbose:
			print "fetching '%s' -> '%s'" % (uri, file_name)
		if proto in ('http','https'):
			try:
				ret= self.__execute_transfer(con, url, myf, 0)
			except UnableToAccess,ua:
				if verbose:
					print ua
				myf.close()
				os.remove(file_name)
				return True
		else:
			ret = con.request(url, callback=myf.write)
		myf.close()
		return not ret

	def resume(self, uri, file_name=None,verbose=None):
		"""resume uri into file_name"""
		if verbose==None:
			verbose=self.__verbose
		proto, con, url = self.__get_connection(uri)
		if not file_name:
			x= url.find("/")
			if x == -1:
				raise Exception,"Unable to deterimine file_name from %s" % uri
			file_name = url[x+1:]
		try:
			pos = os.stat(file_name).st_size

			# open it manually, since open(file_name,"a") has the lovely feature of 
			# ignoring _all_ previous seek requests the minute a write is issued.
			fd=os.open(file_name, os.O_WRONLY)
			myf = os.fdopen(fd,"w",0)
			if pos > self.__chunk_size:
				pos -= self.__chunk_size 
				myf.seek(pos, 0)
			else:
				pos=0

		except OSError, e:
			if e.errno == 2:
				# file not found
				pos = 0
				myf = open(file_name, "w",0)
			else:
				sys.stderr.write("Failed opening file %s for saving:\n%s\n" % (file_name,str(e)))
				return True

		if verbose:
			print "resuming '%s' -> '%s'" % (uri, file_name)
		if proto in ('http','https'):
			try:
				ret = self.__execute_transfer(con, url, myf, pos)
			except UnableToAccess,ua:
				if verbose:
					print ua
				myf.close()
				return True
		else:
			ret = con.request(url, callback=myf.write, start=pos)
		myf.close()
		return not ret

	def __execute_transfer(self, con, url, fd, pos):
		"""internal http(|s) function for looping over requests storing to fd"""
		rc=1
		redirect_max = 10
		while rc:
#			print "fetching %i-%i" % (pos, pos + (self.__chunk_size *8) -1)
			try:
				data,rc=con.request(url,start=pos, end=(pos+(self.__chunk_size*8) -1))
			except MovedLocation, ml:
				sys.stderr.write(str(ml)+"\n")
				url = ml.location
				redirect_max -= 1
				if redirect_max <= 0:
					print "we've been redirected too many times- bailing"
					return False
				else:
					continue
			except UnhandledError, ue:
				print ue
				return False				
			fd.write(data)
			pos += len(data)
		return True
		
	default_ports = {'http':80, 'https':443, 'ftp':21}

	def __process_uri(self, uri):
		"""internal function to determine the proto, host, uri, options for
		__get_connection, and a hash representing this host's specific options.
		username, password, port, ssl, etc"""
		con_dict = {}
		proto,parts,url = urlparse.urlparse(uri)[0:3]
		if not self.default_ports.has_key(proto):
#			port = self.default_ports[proto]
#		else:
			raise Exception, "unknown protocol %s for uri %s" % (proto,uri)

		parts = parts.split("@")
		if len(parts) > 1:
			con_dict["user"] = parts.pop(0)

		r=re.compile(":\d+$").search(parts[0])
		if r:
			# found a port
			con_dict["port"] = parts[0][r.start() + 1:]
			parts[0] = parts[0][0:r.start()]
		del r

		#grab the pass.
		parts = parts[0].split(":")
		if len(parts) > 1:
			con_dict["passwd"] = parts.pop(0)

		hash=''
		k=con_dict.keys()
		k.sort()
		for x in k:
			hash += '%s:%s\n' % (x, str(con_dict[x]))
		hash += "host:%s" % parts[0]
		return [proto, parts[0], con_dict, url,hash]

class ftpConnection:
	"""higher level interface over ftplib"""
	def __init__(self,host,ssl=False,port=21,user=None,passwd=None,passive=True, chunk_size=8192,debug=0):
		"""ssl is currently not supported
		debug flips on a bit of extra info
		chunk_size controls the size of chunks transferred per callback- useful for performance tweaking
		
		note a ftpConnection instance *must not* be called in a threaded/parallel manner- 
		the connection can handle one, and only one request, and is currently not smart 
		enough to lock itself for protection"""
		self.__chunk = chunk_size
		self.__pos = 0
		self.__end = 0
		self.__endlimit = False
		if ssl:
			raise Exception, "sftp isn't support atm"
		args=[]
		self.__con = ftplib.FTP()
		self.__con.set_debuglevel(debug)
		self.__con.connect(host,port)
		if user and passwd:
			self.__con.login(user,passwd)
		else:
			self.__con.login()
		self.__con.set_pasv(passive)

	def request(self, file, start=0, end=0, callback=None):
		"""make a request of file, with optional start/end
		callback is used for processing data- if callback, then callback is called, and the return 
		is true/false depending on success

		if no callback, then the requested window is returned, eg string.
		
		technical note: do to the way the protocol works, the remote host may send more then what 
		was specified via start/end.  Despite this, only that window is processed/returned.
		Just worth noting since it means if you're requested 3 bytes from a file, depending on how 
		quickly the server disconnects, 13k may've been sent by that point (still, only the 3 bytes 
		are actually processed by callback/returned)."""

		self.__pos = start
		self.__end = end
		self.__callback = callback
		self.__data = ''
		self.__aborted = False

		if end:
			self.__endlimit = True		
		if end:
			block = end - start
		else:
			block = self.__chunk
		if block > self.__chunk:
			block = self.__chunk

		try:
			d=self.__con.retrbinary("retr %s" % file, self.__transfer_callback, block, start)
		except ftplib.all_errors:
			self.__data = ''
			return False

		if callback == None:
			d = self.__data
			self.__data = ''
			return d
		

	def __transfer_callback(self, data):
		"""internal callback function used with ftplib.  This either appends the returned data,
		or passes it off to the requested callback function"""
		if self.__aborted:
			return

		l=len(data)

		if self.__endlimit and self.__pos + l >= self.__end:
			data = data[:self.__end - l]
			l = self.__end - self.__pos
			self.__aborted = True
			self.__con.abort()

		self.__pos += l
		if self.__callback:
			self.__callback(data)
		else:
			self.__data += data
		return

class httpConnection:
	"""higher level abstraction over httplib allowing window level access to a remote uri"""
	def __init__(self,host,ssl=False,port=None,user=None,passwd=None):
		"""options for this host connection, sent to the server via the headers
		note you cannot just specify the port as 443 and assume it'll do ssl-
		you must flip on ssl to enable descryption/encryption of the protocol

		just like with ftpConnection, instances *must not* be called in a parallel/threaded
		manner without external locking.
		This class isn't smart enough to protect itself, although it will be made so at 
		some point."""

		self.__headers = {}
		self.__host = host
		if user and passwd:
			self.__headers.extend({"Authorization": "Basic %s" %
				base64.encodestring("%s:%s" % (user,passwd)).replace("\012","")
			})

		if port == None:
			if ssl:
				self.__port = httplib.HTTPS_PORT
			else:
				self.__port = httplib.HTTP_PORT
		else:
			self.__port = port
		if ssl:
			self.__conn = httplib.HTTPSConnection(self.__host, self.__port)
		else:
			self.__conn = httplib.HTTPConnection(self.__host, self.__port)

	def request(self,uri,start=None,end=None):
		"""returns httpconnection.response, our chucks an exception."""
		if end==None and start:
			end += 3000
		size = None
		if not (start == None or end == None):
			size = end - start
			self.__headers["Range"]="bytes=%i-%i" % (start, end)
		try:
			self.__conn.request("GET",uri,{},self.__headers)
		except httplib.HTTPException, e:
			print "caught exception %s" % str(e)
			if start and end:
				del self.__headers["Range"]
			return None,False
		if start and end:
			del self.__headers["Range"]
		response = self.__conn.getresponse()
		rc = response.status
		if rc in (301,302):
			response.read()
			for x in str(response.msg).split("\n"):
				p = x.split(":")
				# assume the remote server is dumb, and ignore case.
				if x[0].lower() == "location":
					raise MovedLocation(rc, x[1])

			# if we hit this point, the server is stupid.
			raise Exception,"received %i, but no location" % rc
		
		if rc in (404,403):
			response.read()
			raise UnableToAccess(rc,response.reason)
		elif rc not in (200,206):
			response.read()
			raise UnhandledError(rc,response.reason)
		data=response.read()
		if size != None:
			return data,(rc==206 and len(data) -1 == size)
		return data,(rc==206)


class UnhandledError(Exception):
	"""basically an unknown state/condition was encountered, so control is being relinquished"""
	def __init__(self, status, reason):
		self.status = status
		self.reason = str(reason)
	def __str__(self):
		return "Unhandled Status code: %i: %s" % (self.status, self.reason)

class UnableToAccess(Exception):
	"""404's and 403's"""
	def __init__(self,status,reason):
		self.status = status
		self.reason = str(reason)
	def __str__(self):
		return "%s code: %s" % (self.status,self.reason)

class MovedLocation(Exception):
	"""http 301/302 exception"""
	def __init__(self,status,new_loc):
		self.status=status
		self.location = str(new_loc)

	def __str__(self):
		if self.status == 301:
			return "301: Location has moved: %s" % self.location
		else:
			return "302: Location has temporarily moved: %s" % self.location
	
