from functools import partial

from pkgcore.merge import triggers


class fake_trigger(triggers.base):

    def __init__(self, **kwargs):
        self._called = []
        if isinstance(kwargs.get('_hooks', False), str):
            kwargs['_hooks'] = (kwargs['_hooks'],)
        for k, v in kwargs.items():
            if callable(v):
                v = partial(v, self)
            setattr(self, k, v)

    def trigger(self, *args):
        self._called.append(args)


class fake_engine:

    def __init__(self, **kwargs):
        kwargs.setdefault('observer', None)
        self._triggers = []
        for k, v in kwargs.items():
            if callable(v):
                v = partial(v, self)
            setattr(self, k, v)

    def add_trigger(self, hook_point, trigger, required_csets):
        if hook_point in getattr(self, "blocked_hooks", []):
            raise KeyError(hook_point)
        self._triggers.append((hook_point, trigger, required_csets))


class fake_reporter:
    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)
