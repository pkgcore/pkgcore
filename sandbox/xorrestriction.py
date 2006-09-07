
class XorRestriction(base):
    """Boolean XOR grouping of restrictions."""
    __slots__ = ()

    def __init__(self, *a, **kw):
        raise NotImplementedError("kindly don't use xor yet")

    def match(self, vals):
        if not self.restrictions:
            return not self.negate

        if self.negate:
            # 1|1 == 0|0 == 1, 0|1 == 1|0 == 0
            armed = self.restrictions[0].match(*vals)
            for rest in islice(self.restrictions, 1, len(self.restrictions)):
                if armed != rest.match(vals):
                    return False
            return True
        # 0|1 == 1|0 == 1, 0|0 == 1|1 == 0
        armed = False
        for rest in self.restrictions:
            if armed == rest.match(vals):
                if armed:
                    return False
            else:
                if not armed:
                    armed = True
        if armed:
            return True
        return False

    def force_True(self, pkg, *vals):
        pvals = [pkg]
        pvals.extend(vals)
        entry_point = pkg.changes_count()
        truths = [r.match(*pvals) for r in self.restrictions]
        count = truths.count(True)
        # get the simple one out of the way first.
        l = len(truths)
        if self.negate:
            f = lambda r: r.force_False(*pvals)
            t = lambda r: r.force_True(*pvals)
            if count > l/2:	order = ((t, count, True), (f, l - count, False))
            else:			order = ((f, l - count, False), (t, count, True))
            for action, current, desired in order:
                if current == l:
                    return True
                for x, r in enumerate(self.restrictions):
                    if truths[x] != desired:
                        if action(r):
                            current += 1
                        else:
                            break
                if current == l:
                    return True
                pkg.rollback(entry_point)
            return False

        stack = []
        for x, val in enumerate(truths):
            falses = filter(None, val)
            if truths[x]:
                falses.remove(x)
                stack.append((falses, None))
            else:
                stack.append((falses, x))

        if count == 1:
            return True
            del stack[truths.index(True)]

        for falses, truths in stack:
            failed = False
            for x in falses:
                if not self.restrictions[x].force_False(*pvals):
                    failed = True
                    break
            if not failed:
                if trues is not None:
                    if self.restrictions[x].force_True(*pvals):
                        return True
                else:
                    return True
            pkg.rollback(entry_point)
        return False

    def force_False(self, pkg, *vals):
        pvals = [pkg]
        pvals.extend(vals)
        entry_point = pkg.changes_count()
        truths = [r.match(*pvals) for r in self.restrictions]
        count = truths.count(True)
        # get the simple one out of the way first.
        l = len(truths)
        if not self.negate:
            f = lambda r: r.force_False(*pvals)
            t = lambda r: r.force_True(*pvals)
            if count > l/2:	order = ((t, count, True), (f, l - count, False))
            else:			order = ((f, l - count, False), (t, count, True))
            for action, current, desired in order:
                if current == l:
                    return True

                for x, r in enumerate(self.restrictions):
                    if truths[x] != desired:
                        if action(r):
                            current += 1
                        else:
                            break
                if current == l:
                    return True
                pkg.rollback(entry_point)
            return False
        # the fun one.
        stack = []
        for x, val in enumerate(truths):
            falses = filter(None, val)
            if truths[x]:
                falses.remove(x)
                stack.append((falses, None))
            else:
                stack.append((falses, x))

        if count == 1:
            return True

        for falses, truths in stack:
            failed = False
            for x in falses:
                if not self.restrictions[x].force_False(*pvals):
                    failed = True
                    break
            if not failed:
                if trues is not None:
                    if self.restrictions[x].force_True(*pvals):
                        return True
                else:
                    return True
            pkg.rollback(entry_point)
        return False

    def __str__(self):
        if self.negate:
            return "not ( %s )" % " ^^ ".join(str(x) for x in self.restrictions)
        return "( %s )" % " ^^ ".join(str(x) for x in self.restrictions)
