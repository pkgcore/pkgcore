PYTHON ?= python
PYTHONPATH ?= ../../../../src
PYTHON_CALL = PYTHONPATH="$(PYTHONPATH)" PYTHONDONTWRITEBYTECODE=1 $(PYTHON)

TARGET = .generated
KNOWN_EAPI = 0 1 2 3 4 5 6 7 8

all: funcs cmds libs

clean:
	$(RM) -r $(TARGET)


.PHONY: funcs
funcs: $(TARGET)/funcs/global $(addprefix $(TARGET)/funcs/,$(KNOWN_EAPI))

$(TARGET)/funcs/%:
	@mkdir -p $(dir $@)
	./generate_eapi_func_list $* > $@
$(TARGET)/funcs/global:
	@mkdir -p $(dir $@)
	./generate_global_func_list > $@


.PHONY: cmds
cmds: $(addprefix $(TARGET)/cmds/,$(KNOWN_EAPI))
$(TARGET)/cmds/%:
	@mkdir -p $@
	./generate_eapi_cmd_list -b $* > $@/banned
	./generate_eapi_cmd_list -d $* > $@/deprecated
	./generate_eapi_cmd_list -i $* > $@/internal


.PHONY: libs
libs: $(addprefix $(TARGET)/libs/,$(KNOWN_EAPI))

.SECONDARY: $(TARGET)/libs/phases-%
$(TARGET)/libs/phases-%:
	@mkdir -p $(dir $@)
	$(PYTHON_CALL) -c "from pkgcore.ebuild import eapi; print('\n'.join(eapi.eapi$*.phases.values()))" > $@

$(TARGET)/libs/%: $(TARGET)/libs/phases-%
	@mkdir -p $@
	./generate_eapi_lib $* > $@/global
	for phase in $$(cat $<); do \
		./generate_eapi_lib -s $${phase} $* > $@/$${phase}; \
	done
