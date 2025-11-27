PYTHON ?= python
SPHINX_BUILD ?= $(PYTHON) -m sphinx.cmd.build

.PHONY: man html
man html:
	doc/build.sh $@ "$$(pwd)/build/sphinx/$@"

html: man

.PHONY: sdist wheel
sdist wheel:
	$(PYTHON) -m build --$@


.PHONY: clean
clean:
	$(RM) -r build doc/api doc/generated dist
	$(MAKE) -C data/lib/pkgcore/ebd clean

.PHONY: format
format:
	$(PYTHON) -m ruff format

.PHONY: dev-environment
dev-environment:
	$(PYTHON) -m pip install -e .[test,doc,formatter]
