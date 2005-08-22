#!/usr/bin/python -O
# Copyright 1999-2004 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2
# $Header$

from xml.sax import saxutils, make_parser, handler
from xml.sax.handler import feature_namespaces

class Metadata_XML(handler.ContentHandler):
	_inside_herd="No"
	_inside_maintainer="No"
	_inside_email="No"
	_inside_longdescription="No"

	_herds = []
	_maintainers = []
	_longdescription = ""

	def startElement(self, tag, attr):
		if tag == "herd":
			self._inside_herd="Yes"
		if tag == "longdescription":
			self._inside_longdescription="Yes"
		if tag == "maintainer":
			self._inside_maintainer="Yes"
		if tag == "email":
			self._inside_email="Yes"

	def endElement(self, tag):
		if tag == "herd":
			self._inside_herd="No"
		if tag == "longdescription":
			self._inside_longdescription="No"
		if tag == "maintainer":
			self._inside_maintainer="No"
		if tag == "email":
			self._inside_email="No"

	def characters(self, contents):
		if self._inside_herd == "Yes":
			self._herds.append(contents)

		if self._inside_longdescription == "Yes":
			self._longdescription = contents
			
		if self._inside_maintainer=="Yes" and self._inside_email=="Yes":
			self._maintainers.append(contents)
