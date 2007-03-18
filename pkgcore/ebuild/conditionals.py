# Copyright: 2005-2007 Brian Harring <ferringb@gmail.com>
# License: GPL2

"""DepSet parsing.

Turns a DepSet (depends, rdepends, SRC_URI, license, etc) into
appropriate conditionals.
"""

# TODO: move exceptions elsewhere, bind them to a base exception for pkgcore

from pkgcore.restrictions import packages, values, boolean
from pkgcore.util.iterables import expandable_chain
from pkgcore.util.lists import iflatten_instance
from pkgcore.ebuild.atom import atom
from pkgcore.ebuild.errors import ParseError

try:
    from pkgcore.ebuild._depset import parse_depset
except ImportError:
    parse_depset = None

class DepSet(boolean.AndRestriction):

    """
    gentoo DepSet syntax parser
    """

    __slots__ = ("has_conditionals", "element_class", "_node_conds",
                 "restrictions", "_known_conditionals")
    type = packages.package_type
    negate = False

    __inst_caching__ = False
    parse_depset = parse_depset
    if parse_depset is not None:
        parse_depset = staticmethod(parse_depset)

    def __init__(self, dep_str, element_class, \
        operators=None,
        element_func=None):

        """
        @param dep_str: string abiding by DepSet syntax
        @param operators: mapping of node -> callable for special operators
            in DepSet syntax
        @param element_func: if None, element_class is used for generating
            elements, else it's used to generate elements.
            Mainly useful for when you need to curry a few args for instance
            generation, since element_class _must_ be a class
        @param element_class: class of generated elements
        """


        sf = object.__setattr__
        sf(self, "_known_conditionals", None)
        sf(self, "element_class", element_class)
        if element_func is None:
            element_func = element_class

        if self.parse_depset is not None:
            restrictions = None
            if operators is None:
                has_conditionals, restrictions = self.parse_depset(dep_str,
                    element_func, boolean.AndRestriction,
                    boolean.OrRestriction)
            else:
                for x in operators:
                    if x not in ("", "||"):
                        break
                else:
                    has_conditionals, restrictions = self.parse_depset(dep_str,
                        element_func, operators.get(""), operators.get("||"))

            if restrictions is not None:
                sf(self, "_node_conds", has_conditionals)
                sf(self, "restrictions", restrictions)
                return

        sf(self, "restrictions", [])
        if operators is None:
            operators = {"||":boolean.OrRestriction, "":boolean.AndRestriction}

        raw_conditionals = []
        depsets = [self.restrictions]

        node_conds = False
        words = iter(dep_str.split())
        k = None
        try:
            for k in words:
                if ")" in k:
                    if ")" != k:
                        raise ParseError(dep_str, k)
                    # no elements == error. if closures don't map up,
                    # indexerror would be chucked from trying to pop
                    # the frame so that is addressed.
                    if not depsets[-1]:
                        raise ParseError(dep_str)
                    elif raw_conditionals[-1].endswith('?'):
                        node_conds = True
                        c = raw_conditionals[-1]
                        if c[0] == "!":
                            c = values.ContainmentMatch(c[1:-1], negate=True)
                        else:
                            c = values.ContainmentMatch(c[:-1])

                        depsets[-2].append(
                            packages.Conditional("use", c, tuple(depsets[-1])))

                    else:
                        if len(depsets[-1]) == 1:
                            depsets[-2].append(depsets[-1][0])
                        elif raw_conditionals[-1] == '' and (len(raw_conditionals) == 1 or ('' == raw_conditionals[-2])):
                            # if the frame is an and and the parent is an and, collapse it in.
                            depsets[-2].extend(depsets[-1])
                        else:
                            depsets[-2].append(
                                operators[raw_conditionals[-1]](finalize=True,
                                                            *depsets[-1]))

                    raw_conditionals.pop()
                    depsets.pop()

                elif "(" in k:
                    if k != "(":
                        raise ParseError(dep_str, k)

                    k = ''
                    # push another frame on
                    depsets.append([])
                    raw_conditionals.append(k)

                elif k[-1] == '?' or k in operators:
                    # use conditional or custom op.
                    # no tokens left == bad dep_str.
                    k2 = words.next()

                    if k2 != "(":
                        raise ParseError(dep_str, k2)

                    # push another frame on
                    depsets.append([])
                    raw_conditionals.append(k)

                elif "|" in k:
                    raise ParseError(dep_str, k)
                else:
                    # node/element.
                    depsets[-1].append(element_func(k))


        except (RuntimeError, SystemExit, KeyboardInterrupt):
            raise
        except IndexError:
            # [][-1] for a frame access, which means it was a parse error.
            raise
        except StopIteration:
            if k is None:
                raise
            raise ParseError(dep_str, k)
        except Exception, e:
            raise ParseError(dep_str, e)

        # check if any closures required
        if len(depsets) != 1:
            raise ParseError(dep_str)

        sf(self, "_node_conds", node_conds)
        sf(self, "restrictions", tuple(self.restrictions))


    def evaluate_depset(self, cond_dict, tristate_filter=None):
        """
        @param cond_dict: container to be used for conditional collapsing,
            typically is a use list
        @param tristate_filter: a control; if specified, must be a container
            of conditionals to lock to cond_dict.
            during processing, if it's not in tristate_filter will
            automatically enable the payload
            (regardless of the conditionals negation)
        """

        if not self.has_conditionals:
            return self

        flat_deps = self.__class__("", self.element_class)

        stack = [boolean.AndRestriction, iter(self.restrictions)]
        base_restrict = []
        restricts = [base_restrict]
        count = 1
        while count:
            for node in stack[-1]:
                if isinstance(node, self.element_class):
                    restricts[-1].append(node)
                    continue
                if isinstance(node, packages.Conditional):
                    if not node.payload:
                        continue
                    elif tristate_filter is not None:
                        assert len(node.restriction.vals) == 1
                        val = list(node.restriction.vals)[0]
                        if val in tristate_filter:
                            # if val is forced true, but the check is
                            # negation ignore it
                            # if !mips != mips
                            if (val in cond_dict) == node.restriction.negate:
                                continue
                    elif not node.restriction.match(cond_dict):
                        continue
                    if not isinstance(node.payload, tuple):
                        stack += [boolean.AndRestriction, iter((node.payload))]
                    else:
                        stack += [boolean.AndRestriction, iter(node.payload)]
                else:
                    stack += [node.__class__,
                              iter(node.restrictions)]
                count += 1
                restricts.append([])
                break
            else:
                stack.pop()
                l = len(restricts)
                if l != 1:
                    if restricts[-1]:
                        # optimization to avoid uneccessary frames.
                        if len(restricts[-1]) == 1:
                            restricts[-2].append(restricts[-1][0])
                        elif stack[-1] is stack[-3] is boolean.AndRestriction:
                            restricts[-2].extend(restricts[-1])
                        else:
                            restricts[-2].append(stack[-1](*restricts[-1]))
                    stack.pop()
                count -= 1
                restricts.pop()

        object.__setattr__(flat_deps, "restrictions", tuple(base_restrict))
        return flat_deps

    @staticmethod
    def find_cond_nodes(restriction_set, yield_non_conditionals=False):
        conditions_stack = []
        new_set = expandable_chain(restriction_set)
        for cur_node in new_set:
            if isinstance(cur_node, packages.Conditional):
                conditions_stack.append(cur_node.restriction)
                new_set.appendleft(list(cur_node.payload) + [None])
            elif (isinstance(cur_node, boolean.base)
                  and not isinstance(cur_node, atom)):
                new_set.appendleft(cur_node.restrictions)
            elif cur_node is None:
                conditions_stack.pop()
            elif conditions_stack or yield_non_conditionals: # leaf
                yield (cur_node, conditions_stack[:])

    @property
    def node_conds(self):
        if self._node_conds is False:
            object.__setattr__(self, "_node_conds", {})
        elif self._node_conds is True:
            nc = {}

            always_required = set()

            for payload, restrictions in self.find_cond_nodes(
                self.restrictions, True):
                if not restrictions:
                    always_required.add(payload)
                else:
                    if len(restrictions) == 1:
                        current = restrictions[0]
                    else:
                        current = values.AndRestriction(finalize=True,
                            *restrictions)

                    nc.setdefault(payload, []).append(current)

            for k in always_required:
                if k in nc:
                    del nc[k]
            for k in nc:
                nc[k] = tuple(nc[k])

            object.__setattr__(self, "_node_conds", nc)

        return self._node_conds

    @property
    def has_conditionals(self):
        return bool(self._node_conds)

    @property
    def known_conditionals(self):
        if self._node_conds is False:
            return frozenset()
        if self._known_conditionals is None:
            kc = set()
            for payload, restrictions in self.find_cond_nodes(
                self.restrictions):
                kc.update(iflatten_instance(x.vals for x in restrictions))
            kc = frozenset(kc)
            object.__setattr__(self, "_known_conditionals", kc)
            return kc
        return self._known_conditionals

    def match(self, *a):
        raise NotImplementedError

    force_False = force_True = match

    def __str__(self):
        return ' '.join(stringify_boolean(x) for x in self.restrictions)

    def __iter__(self):
        return iter(self.restrictions)

    def __getitem__(self, key):
        return self.restrictions[key]


def stringify_boolean(node, func=str):
    """func is used to stringify the actual content. Useful for fetchables."""
    if isinstance(node, boolean.OrRestriction):
        return "|| ( %s )" % " ".join(stringify_boolean(x, func)
                                      for x in node.restrictions)
    elif isinstance(node, boolean.AndRestriction) and \
        not isinstance(node, atom):
        return "( %s )" % " ".join(stringify_boolean(x, func)
            for x in node.restrictions)
    elif isinstance(node, packages.Conditional):
        assert len(node.restriction.vals) == 1
        return "%s%s? ( %s )" % (
            node.restriction.negate and "!" or "",
            list(node.restriction.vals)[0],
            " ".join(stringify_boolean(x, func) for x in node.payload))
    elif isinstance(node, DepSet):
        return ' '.join(stringify_boolean(x, func) for x in node.restrictions)
    return func(node)
