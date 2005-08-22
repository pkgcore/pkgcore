import elog_modules.mod_save, portage_exec, portage_exception

def process(mysettings, cpv, logentries, fulltext):
	elog_modules.mod_save.process(mysettings, cpv, logentries, fulltext)
	
	if (not "PORTAGE_LOG_COMMAND" in mysettings.keys()) \
			or len(mysettings["PORTAGE_LOG_COMMAND"]) == 0:
		raise portage_exception.MissingParameter("!!! Custom logging requested but PORTAGE_LOG_COMMAND is not defined")
	else:
		mylogcmd = mysettings["PORTAGE_LOG_COMMAND"]
		mylogcmd.replace("${LOGFILE}", elogfilename)
		mylogcmd.replace("${PACKAGE}", cpv)
		retval = portage_exec.spawn_bash(mylogcmd)
		if retval != 0:
			raise portage_exception.PortageException("!!! PORTAGE_LOG_COMMAND failed with exitcode %d" % retval)
	return
