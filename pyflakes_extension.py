#!/usr/bin/env python
# Copyright: 2011 Brian Harring <ferringb@gmail.com>
# License: GPL2/BSD 3 clause

import ast as _ast
from pyflakes import checker as _checker, messages as _messages

_Checker = _checker.Checker

SNAKEOIL_LOC = 'snakeoil.demandload.demandload'
SNAKEOIL_REGEX_LOC = 'snakeoil.demandload.demand_compile_regexp'
SNAKEOIL_MOD = 'snakeoil.demandload'
from snakeoil.demandload import parse_imports as parse_demandload


class BadDemandloadCall(_messages.Message):

    message = 'bad invocation of demandload; should be demandload(globals(), *targets)'

    def __init__(self, filename, lineno, target=None):
        _messages.Message.__init__(self, filename, lineno)
        if target is not None:
            self.message = self.message + ': exception %r will occur'
            self.message_args = (target,)


class BadDemandloadRegexCall(BadDemandloadCall):

    message = 'bad invocation of demand_compile_regexp; should be demand_compile_regexp(globals(), name, *args)'


class UnBindingDemandload(_messages.Message):

    message = 'demandloaded target %s was deleted; pointless demandload then'

    def __init__(self, filename, lineno, target):
        _messages.Message.__init__(self, filename, lineno)
        self.message_args = (target,)


class DemandloadImportation(_checker.Importation):

    pass


class DemandloadChecker(_Checker):

    def addBinding(self, lineno, value, reportRedef=True):
        _Checker.addBinding(self, lineno, value, reportRedef=reportRedef)
        if isinstance(value, _checker.Importation):
            value.is_demandload_func = False
            value.is_demandload_module = False
            value.is_demandload_regex = False

            module_frag = getattr(value.source, 'module', '')
            if module_frag:
                module_frag += '.'
            for alias in value.source.names:
                if value.name != (alias.asname or alias.name):
                    continue
                name = module_frag + alias.name
                if name == SNAKEOIL_LOC:
                    value.is_demandload_func = True
                elif name == SNAKEOIL_MOD:
                    value.is_demandload_module = True
                elif name == SNAKEOIL_REGEX_LOC:
                    value.is_demandload_regex = True
        elif isinstance(value, _checker.UnBinding):
            if isinstance(self.scope.get(value.name), DemandloadImportation):
                self.report(UnBindingDemandload, lineno, value.name)

    def CALL(self, tree):
        is_demandload = is_demandload_regex = False
        if isinstance(tree.func, _ast.Attribute):
            if not isinstance(tree.func.value, _ast.Name):
                # this means it's a multilevel lookup;
                # pkgcore.ebuild.ebuild_src.some_func
                # ignore it; it *could* miss a direct
                # snakeoil.demandload.demandload, but
                # I don't care, bad form of access imo.
                return self.handleChildren(tree)

            src = self.scope.get(tree.func.value.id)

            if getattr(src, 'is_demandload_module', False):
                if tree.func.attr == 'demandload':
                    is_demandload = True
                elif tree.func.attr == 'demand_compile_regexp':
                    is_demandload_regex = True
        elif hasattr(tree.func, 'id'):
            # pylint: disable=bad-whitespace
            is_demandload       = getattr(self.scope.get(tree.func.id), 'is_demandload_func', False)
            is_demandload_regex = getattr(self.scope.get(tree.func.id), 'is_demandload_regex', False)

        if is_demandload_regex:
            # should do validation here.
            if len(tree.args) < 3:
                self.report(BadDemandloadRegexCall, tree.lineno)
            elif tree.args[1].__class__.__name__.upper() not in ("STR", "UNICODE"):
                self.report(BadDemandloadRegexCall, tree.lineno, "name argument isn't string nor unicode")
            elif tree.args[2].__class__.__name__.upper() not in ("STR", "UNICODE"):
                self.report(BadDemandloadRegexCall, tree.lineno, "regex argument isn't string nor unicode")
            else:
                code = "%s = re.compile(%r)\n" % (tree.args[1].s, tree.args[2].s)
                fakenode = _ast.copy_location(compile(code, self.filename, "exec", _ast.PyCF_ONLY_AST).body[0],
                                              tree)
                self.addBinding(tree.lineno, _checker.Assignment(tree.args[1].s, fakenode))

        if is_demandload:
            if len(tree.args) < 2:
                self.report(BadDemandloadCall, tree.lineno)
                return self.handleChildren(tree)

            for chunk in tree.args[1:]:
                chunk_cls = chunk.__class__.__name__
                if chunk_cls.upper() not in ('STR', 'UNICODE'):
                    self.report(BadDemandloadCall, chunk.lineno,
                                "invoked with non string/unicode arg: %r" % (chunk_cls,))
                    continue
                s = chunk.s
                try:
                    targets = list(parse_demandload([s]))
                except ValueError as ve:
                    self.report(BadDemandloadCall, chunk.lineno, ve)
                    continue
                for src, asname in targets:
                    fakenode = _ast.copy_location(
                        compile("import %s as %s\n" % (src, asname),
                                self.filename, "exec", _ast.PyCF_ONLY_AST).body[0],
                        chunk)
                    self.addBinding(chunk.lineno,
                                    DemandloadImportation(asname, fakenode))
        return self.handleChildren(tree)


if __name__ == '__main__':
    _checker.Checker = DemandloadChecker
    from pyflakes.scripts.pyflakes import main
    main()
