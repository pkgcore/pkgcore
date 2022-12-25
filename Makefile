PYTHON ?= python
SPHINX_BUILD ?= $(PYTHON) -m sphinx.cmd.build

.PHONY: man html
man html:
	$(SPHINX_BUILD) -a -b $@ doc build/sphinx/$@

.PHONY: sdist wheel
sdist wheel:
	$(PYTHON) -m build --$@

.PHONY: clean
clean:
	$(RM) -r build/sphinx doc/api doc/generated dist
	$(MAKE) -C data/lib/pkgcore/ebd clean

.PHONY: format
format:
	$(PYTHON) -m black .
