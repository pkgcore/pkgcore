SUBDIRS 	=

bin_PROGRAMS	=
if BUILD_TBZ2TOOL
bin_PROGRAMS += tbz2tool
endif

if BUILD_FILTER_ENV
SUBDIRS += filter-env
endif

if BUILD_MISSINGOS
SUBDIRS += python-missingos
endif

tbz2tool_SOURCES = tbz2tool.c
