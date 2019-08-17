__all__ = ("group_attempts", "fails_filter", "reduce_to_failures",)


def group_attempts(sequence, filter_func=None):
    if filter_func is None:
        filter_func = lambda x:True
    last, l = None, []
    for x in sequence:
        if isinstance(x, tuple) and x[0] == 'inspecting':
            if l:
                yield last, l
            last, l = x[1], []
        elif last is not None:
            if filter_func(x):
                # inline ignored frames
                if getattr(x, 'ignored', False):
                    l.extend(y for y in x.events if filter_func(y))
                else:
                    l.append(x)
    if l:
        yield last, l

def fails_filter(x):
    if not isinstance(x, tuple):
        return not x.succeeded
    if x[0] == "viable":
        return not x[1]
    return x[0] != "inspecting"

def reduce_to_failures(frame):
    if frame.succeeded:
        return []
    l = [frame]
    for pkg, nodes in group_attempts(frame.events, fails_filter):
        l2 = []
        for x in nodes:
            if not isinstance(x, tuple):
                l2.append(reduce_to_failures(x))
            else:
                l2.append(x)
        l.append((pkg, l2))
    return l
