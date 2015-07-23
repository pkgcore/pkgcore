
"""Pylint plugin checking for trailing whitespace."""

from __future__ import print_function
import sys
import __builtin__ as builtins

from pylint import interfaces, checkers
if hasattr(interfaces, 'IASTNGChecker'):
    print('ERROR: please install >=pylint-1.0', file=sys.stderr)
    exit(1)

try:
    from astroid import nodes, utils, Getattr, CallFunc, rebuilder
except ImportError:
    print('ERROR: could not import astroid; make sure that package is '
          'installed: dev-python/astroid', file=sys.stderr)
    raise


class SnakeoilChecker(checkers.BaseChecker):
    """Custom snakeoil linter checks."""

    __implements__ = (interfaces.IRawChecker, interfaces.IAstroidChecker)

    name = 'snakeoil'

    # XXX move some of those over to RewriteDemandload somehow
    # (current monkey patch running the rewriter does not support that)

    # pylint: disable=too-few-public-methods,multiple-statements
    class _MessageCPC01(object): pass
    class _MessageCPC02(object): pass
    class _MessageWPC01(object): pass
    class _MessageWPC02(object): pass
    class _MessageWPC03(object): pass
    class _MessageWPC04(object): pass
    class _MessageWPC06(object): pass
    class _MessageWPC08(object): pass
    # pylint: enable=too-few-public-methods,multiple-statements

    msgs = {
        'CPC01': ('line too long: length %d',
                  'More complete version of the standard line too long check.',
                  _MessageCPC01),
        'CPC02': ('trailing whitespace', 'trailing whitespace sucks.',
                  _MessageCPC02),
        'WPC01': ('demandload with arglen < 2 ignored',
                  'A call which is probably a demandload has too little '
                  'arguments.',
                  _MessageWPC01),
        'WPC02': ('demandload with non-string-constant arg ignored',
                  'A call which is probably a demandload has a second arg '
                  'that is not a string constant. Fix the code to cooperate '
                  'with the dumb checker.',
                  _MessageWPC02),
        'WPC03': ('old-style demandload call',
                  'A call which uses the old way of callling demandload, '
                  'with spaces.',
                  _MessageWPC03),
        'WPC04': ('non new-style class',
                  'All classes should be new-style classes.',
                  _MessageWPC04),
        'WPC06': ('raise of Exception base class',
                  'A raise statement in which Exception is raised- make a '
                  'subclass of it and raise that instead.',
                  _MessageWPC06),
        'WPC08': ('Iterating over dict.keys()',
                  'Iterating over dict.keys()- use `for x in dict` or '
                  '`for x in d.iteritems()` if you need the vals too',
                  _MessageWPC08),
        }

    def process_module(self, stream):
        for linenr, line in enumerate(stream):
            line = line.rstrip('\r\n')
            if len(line) > 80:
                self.add_message('CPC01', line=linenr, args=len(line))
            if line.endswith(' ') or line.endswith('\t'):
                self.add_message('CPC02', line=linenr)

    def visit_class(self, node):
        if not node.bases:
            self.add_message('WPC04', line=node.fromlineno)

    def visit_raise(self, node):
        if node.exc is None or not hasattr(node.exc, 'func'):
            return
        elif getattr(node.exc.func, 'name', None) == 'Exception':
            self.add_message('WPC06', line=node.fromlineno)

    def visit_for(self, node):
        expr = node.iter
        if isinstance(expr, CallFunc):
            expr = list(expr.get_children())[0]
            if isinstance(expr, Getattr) and expr.attrname == 'keys':
                self.add_message('WPC08', line=node.fromlineno)


class SnakeoilASTRewrites(utils.ASTWalker):
    """Handle some of the magic imports snakeoil injects."""

    # Wipe the shadowing we still allow for >=py2.5 compat.
    ignore_shadowing = frozenset(
        x for x in ('intern', 'cmp')
        if x not in dir(builtins))

    def __init__(self, linter):
        utils.ASTWalker.__init__(self, self)
        self.linter = linter

    def leave(self, node):
        pass

    def set_context(self, parent, child):
        pass

    def _do_compatibility_rewrite(self, node):
        wipes = [x for x in node.names if x[0] in self.ignore_shadowing
                 or x[1] in self.ignore_shadowing]
        if not wipes:
            return
        for src, trg in wipes:
            del node.scope().locals[trg if trg is not None else src]
        node.names = [x for x in node.names if x not in wipes]

    def visit_from(self, node):
        if getattr(node, 'modname', None) == 'snakeoil.compatibility':
            self._do_compatibility_rewrite(node)

    def visit_import(self, node):
        if getattr(node, 'modname', None) == 'snakeoil.compatibility':
            self._do_compatibility_rewrite(node)

    def visit_callfunc(self, node):
        """Hack fake imports into the tree after demandload calls."""
        # XXX inaccurate hack
        if not getattr(node.func, 'name', '').endswith('demandload'):
            return
        # sanity check.
        if len(node.args) < 2:
            self.linter.add_message('WPC01', line=node.fromlineno)
            return
        if not isinstance(node.args[1], nodes.Const):
            self.linter.add_message('WPC02', line=node.fromlineno)
            return
        if node.args[1].value.find(" ") != -1:
            self.linter.add_message('WPC03', line=node.fromlineno)
            return
        # Ignore the first arg since it's gloals()
        for mod in (module.value for module in node.args[1:]):
            if not isinstance(mod, str):
                self.linter.add_message('WPC02', line=node.fromlineno)
                continue
            col = mod.find(':')
            if col == -1:
                # Argument to Import probably works like this:
                # "import foo, foon as spork" is
                # nodes.Import([('foo', None), ('foon', 'spork')])
                # (not entirely sure though, have not found documentation.
                # The asname/importedname might be the other way around fex).
                new_node = nodes.Import()
                rebuilder._set_infos(node, new_node, node.parent) # pylint: disable=protected-access
                new_node.names = [(mod, mod)]
                #node.frame().add_local_node(new_node, mod)
                node.set_local(mod, new_node)
            else:
                for name in mod[col+1:].split(','):
                    new_node = nodes.From(mod[:col], ((name, None),), 0)
                    rebuilder._set_infos(node, new_node, node.parent) # pylint: disable=protected-access
                    #node.frame().add_local_node(newstuff, name)
                    node.set_local(name, new_node)


def register(linter):
    """Required method to get our checker registered."""

    rewriter = SnakeoilASTRewrites(linter)
    # XXX HACK: monkeypatch the linter to transform the tree before
    # the astroid checkers get at it.
    #
    # Why do we do this? Because a whole bunch of places work with
    # copies of astroid data, not the data itself, by the time a normal
    # checker runs it is too late to manipulate the data reliably. And
    # pylint does not provide a hook that gets run at the right point
    # to do this tree rewriting. So we monkeypatch in the hook.
    #
    # Ideally we would do something like
    #
    # linter.register_preprocessor(rewriter)
    #
    # and the linter would call walk(astroid) on everything registered that way
    # before the internal astroid checkers run (not sure if it should be before
    # or after the raw checkers run, probably does not matter). Perhaps give
    # those preprocessors a priority attribute too. Definitely give them a msgs
    # attribute.

    original_check_astroid_module = linter.check_astroid_module
    def snakeoil_check_astroid_module(astroid, *args):
        # Rewrite the ast for demandload awareness, then let the normal
        # checks work with that tree.
        rewriter.walk(astroid)
        return original_check_astroid_module(astroid, *args)
    linter.check_astroid_module = snakeoil_check_astroid_module

    # Finally, register our custom checks.
    linter.register_checker(SnakeoilChecker(linter))
