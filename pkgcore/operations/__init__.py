# Copyright: 2005-2011 Brian Harring <ferringb@gmail.com>
# License: GPL2/BSD

"""
operation templates for package/repository/data source objects

For new format implementations, new formats, and generally any new extension,
an operation class will likely have to be defined.  While the implementations
are a bit repetitive, the design of it is intentional to ensure that any derivative
will be forced to adhere to the pkgcore internal api.

Basically it's a crappy form of zope interfaces; converting to zope.interfaces may
occur down the line if dependencies can be kept as minimal as possible.
"""

class base(object):

    def __init__(self, disable_overrides=(), enable_overrides=()):
        enabled_ops = set(self._filter_disabled_commands(
            self._collect_operations()))
        enabled_ops.update(enable_overrides)
        enabled_ops.difference_update(disable_overrides)

        for op in enabled_ops:
            self._enable_operation(op)

        self._enabled_ops = frozenset(enabled_ops)

    def _filter_disabled_commands(self, sequence):
        for command in sequence:
            check_f = getattr(self, '_cmd_check_support_%s' % command, None)
            if check_f is not None and not check_f():
                continue
            yield command

    def _enable_operation(self, operation):
        setattr(self, operation,
            getattr(self, '_cmd_api_%s' % operation))

    @classmethod
    def _collect_operations(cls):
        for x in dir(cls):
            if x.startswith("_cmd_") and not x.startswith("_cmd_api_") \
                and not x.startswith("_cmd_check_support_"):
                yield x[len("_cmd_"):]

    def supports(self, operation_name=None, raw=False):
        if not operation_name:
            if not raw:
                return self._enabled_ops
            return frozenset(self._collect_operations())
        if raw:
            return hasattr(self, '_cmd_api_%s' % operation_name)
        return hasattr(self, operation_name)

    #def __dir__(self):
    #    return list(self._enabled_ops)
