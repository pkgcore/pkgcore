SUBDIRS = framework reimplementation misc
buildtoc = ./buildtoc.py
htmlfromrst = $(addsuffix .html,$(basename $(wildcard *.rst))) toc.html

all: SUBDIRS $(htmlfromrst) toc.html

.PHONY: all clean

SUBDIRS:
	for subdir in $(SUBDIRS); do \
		(cd $$subdir && make) || exit 1; \
	done

CLEAN_SUBDIRS:
	for subdir in $(SUBDIRS); do \
		(cd $$subdir && make clean); \
	done


toc.rst: $(buildtoc)
	$(buildtoc) > toc.rst

%.html: %.rst
	rst2html.py $< $@

clean: CLEAN_SUBDIRS
	rm -f $(htmlfromrst) toc.rst
