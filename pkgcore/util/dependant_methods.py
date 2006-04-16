# Copyright: 2005 Brian Harring <ferringb@gmail.com>
# License: GPL2


# metaclasses, 101.  metaclass gets called to instantiate a class (creating a class instance).
# effectively, __metaclass__ controls how that class is converted from a definition, to an object, with the 
# object being used to create instances of that class.
# note python doesn't exactly have definitions, just executions, but analogy is close enough :P
	
from pkgcore.util.lists import flatten
from pkgcore.util.currying import pre_curry

__all__ = ["ForcedDepends"]

def ensure_deps(self, name, *a, **kw):
	ignore_deps = "ignore_deps" in kw
	if ignore_deps:
		del kw["ignore_deps"]
		s = [name]
	else:
		s = yield_deps(self, self.stage_depends, name)

	r = True
	for dep in s:
		if dep not in self._stage_state:
			r = getattr(self, dep).raw_func(*a, **kw)
			if r:
				self._stage_state.add(dep)
			else:
				return r
	return r

def dont_iterate_strings(val):
	if isinstance(val, (tuple, list)):
		return val
	elif isinstance(val, basestring):
		return (val,)
	raise ValueError("encountered val %s when it must be a list or string", val)

def yield_deps(inst, d, k):
	if k not in d:
		yield k
		return
	s = [k, iter(dont_iterate_strings(d.get(k,())))]
	while s:
		if isinstance(s[-1], basestring):
			yield s.pop(-1)
			continue
		exhausted = True
		for x in s[-1]:
			v = d.get(x)
			if v:
				s.append(x)
				s.append(iter(dont_iterate_strings(v)))
				exhausted = False
				break
			yield x
		if exhausted:
			s.pop(-1)


class ForcedDepends(type):
	def __call__(cls, *a, **kw):
		if not getattr(cls, "stage_depends"):
			return super(ForcedDepends, cls).__call_(*a, **kw)
		
		o = super(ForcedDepends, cls).__call__(*a, **kw)
		if not hasattr(o, "_stage_state"):
			o._stage_state = set()

		# wrap the funcs

		for x in set(filter(None, flatten(o.stage_depends.iteritems()))):
			f = getattr(o, x)
			f2 = pre_curry(ensure_deps, o, x)
			f2.raw_func = f
			setattr(o, x, f2)

		return o
