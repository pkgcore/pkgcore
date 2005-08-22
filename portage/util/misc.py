# Copyright 1998-2005 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2
# $Header$
cvs_id_string="$Id: misc.py 1803 2005-07-13 05:51:35Z ferringb $"[5:-2]

#clean this up.
import sys,string,shlex,os.path,stat,types
import shutil


def stack_dictlist(original_dicts, incremental=0, incrementals=[], ignore_none=0):
	"""Stacks an array of dict-types into one array. Optionally merging or
	overwriting matching key/value pairs for the dict[key]->list.
	Returns a single dict. Higher index in lists is preferenced."""
	final_dict = None
	kill_list = {}
	for mydict in original_dicts:
		if mydict == None:
			continue
		if final_dict == None:
			final_dict = {}
		for y in mydict.keys():
			if not final_dict.has_key(y):
				final_dict[y] = []
			if not kill_list.has_key(y):
				kill_list[y] = []
			
			mydict[y].reverse()
			for thing in mydict[y]:
				if thing and (thing not in kill_list[y]) and ("*" not in kill_list[y]):
					if (incremental or (y in incrementals)) and thing[0] == '-':
						if thing[1:] not in kill_list[y]:
							kill_list[y] += [thing[1:]]
					else:
						if thing not in final_dict[y]:
							final_dict[y].append(thing[:])
			mydict[y].reverse()
			if final_dict.has_key(y) and not final_dict[y]:
				del final_dict[y]
	return final_dict


def stack_dicts(dicts, incremental=0, incrementals=[], ignore_none=0):
	"""Stacks an array of dict-types into one array. Optionally merging or
	overwriting matching key/value pairs for the dict[key]->string.
	Returns a single dict."""
	final_dict = None
	for mydict in dicts:
		if mydict == None:
			if ignore_none:
				continue
			else:
				return None
		if final_dict == None:
			final_dict = {}
		for y in mydict.keys():
			if mydict[y]:
				if final_dict.has_key(y) and (incremental or (y in incrementals)):
					final_dict[y] += " "+mydict[y][:]
				else:
					final_dict[y]  = mydict[y][:]
			mydict[y] = string.join(mydict[y].split()) # Remove extra spaces.
	return final_dict

def stack_lists(lists, incremental=1):
	"""Stacks an array of list-types into one array. Optionally removing
	distinct values using '-value' notation. Higher index is preferenced."""
	new_list = []
	for x in lists:
		for y in x:
			if y:
				if incremental and y[0]=='-':
					while y[1:] in new_list:
						del new_list[new_list.index(y[1:])]
				else:
					if y not in new_list:
						new_list.append(y[:])
	return new_list


def unique_array(array):
	"""Takes an array and makes sure each element is unique."""
	newarray = []
	for x in array:
		if x not in newarray:
			newarray.append(x)
	return newarray


def flatten(mytokens):
	"""this function now turns a [1,[2,3]] list into
	a [1,2,3] list and returns it."""
	newlist=[]
	for x in mytokens:
		if type(x)==list:
			newlist.extend(flatten(x))
		else:
			newlist.append(x)
	return newlist
