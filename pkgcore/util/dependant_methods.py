# Copyright: 2005 Brian Harring <ferringb@gmail.com>
# License: GPL2


# metaclasses, 101.  metaclass gets called to instantiate a class (creating a class instance).
# effectively, __metaclass__ controls how that class is converted from a definition, to an object, with the 
# object being used to create instances of that class.
# note python doesn't exactly have definitions, just executions, but analogy is close enough :P
	
from pkgcore.util.lists import unique, flatten
from pkgcore.util.currying import pre_curry

def ensure_deps(name, func, self, *a, **kw):
	if "_stage_state" not in self.__dict__:
		self._stage_state = set()

	if "raw" in kw:
		del kw["raw"]
		r=func(self, *a, **kw)

	else:
		if name in self._stage_state:
			return True
		for x in self.stage_depends.get(name,[]):
			r = getattr(self,x)(*a, **kw)
			if not r:
				return r
		r = func(self, *a, **kw)
	if r:
		self._stage_state.add(name)
	return r


class ForcedDepends(type):
	def __call__(cls, *a, **kw):
		for k,v in getattr(cls, "stage_depends", {}).items():
			if not isinstance(v, (list, tuple)):
				if v == None:
					cls.stage_depends[k] = []
				else:
					cls.stage_depends[k] = [v]
		
		for x in unique(cls.stage_depends.keys() + flatten(cls.stage_depends.values())):
			setattr(cls, x, pre_curry(ensure_deps, x, getattr(cls, x)))
		return super(ForcedDepends, cls).__call__(*a, **kw)

