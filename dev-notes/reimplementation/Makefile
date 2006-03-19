
buildtoc = ../buildtoc.py
htmlfromrst = $(addsuffix .html,$(basename $(wildcard *.rst))) toc.html

all: $(htmlfromrst)

.PHONY: all clean

toc.rst: $(buildtoc)
	$(buildtoc) > toc.rst

%.html: %.rst
	rst2html.py $< $@

clean:
	rm -f $(htmlfromrst) toc.rst
