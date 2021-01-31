========================
 Python Code Guidelines
========================

Note that not all of the existing code follows this style guide.
This doesn't mean existing code is correct.

Stats are all from a sempron 1.6Ghz with python 2.4.2.

Finally, code _should_ be documented, following epydoc/epytext guidelines

Follow pep8, with following exemptions
======================================

- <80 char limit is only applicable where it doesn't make the logic
  ugly. This is not an excuse to have a 200 char if statement (fix
  your logic). Use common sense.
- Combining imports is ok.
- Use absolute imports
- _Simple_ try/except combined lines are acceptable, but not forced
  (this is your call). example::

   try: l.remove(blah)
   except IndexError: pass

- For comments, 2 spaces trailing is pointless- not needed.
- Classes should be named SomeClass, functions/methods should be named
  some_func.
- Exceptions are classes.  Don't raise strings.
- Avoid __var 'private' attributes unless you absolutely have a reason
  to hide it, and the class won't be inherited (or that attribute
  must _not_ be accessed)
- Using string module functions when you could use a string method is
  evil. Don't do it.
- Use isinstance(str_instance, basestring) unless you _really_ need to
   know if it's utf8/ascii

Throw self with a NotImplementedError
=====================================

The reason for this is simple: if you just throw a NotImplementedError,
you can't tell how the path was hit if derivative classes are involved;
thus throw NotImplementedError(self, string_name_of_attr)

This gives far better tracebacks.

Be aware of what the interpreter is actually doing
==================================================

Don't use len(list_instance) when you just want to know if it's
nonempty/empty::

  l=[1]
  if l: blah
  # instead of
  if len(l): blah

python looks for __nonzero__, then __len__. It's far faster
than if you try to be explicit there::

  python -m timeit -s 'l=[]' 'if len(l) > 0: pass'
  1000000 loops, best of 3: 0.705 usec per loop

  python -m timeit -s 'l=[]' 'if len(l): pass'
  1000000 loops, best of 3: 0.689 usec per loop

  python -m timeit -s 'l=[]' 'if l: pass'
  1000000 loops, best of 3: 0.302 usec per loop

Don't explicitly use has_key. Rely on the 'in' operator
=======================================================

::

  python -m 'timeit' -s 'd=dict(zip(range(1000), range(1000)))' 'd.has_key(1999999)'
  1000000 loops, best of 3: 0.512 usec per loop

  python -m 'timeit' -s 'd=dict(zip(range(1000), range(1000)))' '1999999 in d'
  1000000 loops, best of 3: 0.279 usec per loop

Python interprets the 'in' command by using __contains__ on the
instance. The interpreter is faster at doing getattr's than actual
python code is: for example, the code above uses d.__contains__ , if you do
d.has_key or d.__contains__, it's the same speed. Using 'in' is faster
because it has the interpreter do the lookup.

So be aware of how the interpreter will execute that code. Python
code specified attribute access is slower then the interpreter doing
it on its own.

If you're in doubt, python -m timeit is your friend. ;-)

Do not use [] or {} as default args in function/method definitions
==================================================================

::

  >>> def f(default=[]):
  >>>   default.append(1)
  >>>   return default
  >>> print f()
  [1]
  >>> print f()
  [1,1]

When the function/class/method is defined, the default args are
instantiated _then_, not per call. The end result of this is that if it's a
mutable default arg, you should use None and test for it being None; this is
exempted if you _know_ the code doesn't mangle the default.

Visible curried functions should have documentation
===================================================

When using the currying methods (pkgcore.util.currying) for function
mangling, preserve the documentation via pretty_docs.

If this is exempted, pydoc output for objects isn't incredibly useful.

Unit testing
============

All code _should_ have test case functionality.  We use twisted.trial - you
should be running >=2.2 (<2.2 results in false positives in the spawn tests).
Regressions should be test cased, exempting idiot mistakes (e.g, typos).

We are more than willing to look at code that lacks tests, but
actually merging the code to integration requires that it has tests.

One area that is (at the moment) exempted from this is the ebuild interaction;
testing that interface is extremely hard, although it _does_ need to
be implemented.

If tests are missing from code (due to tests not being written initially),
new tests are always desired.


If it's FS related code, it's _usually_ cheaper to try then to ask then try
===========================================================================

...but you should verify it ;)


existing file (but empty to avoid reading overhead)::

  echo > dar

  python -m 'timeit' -s 'import os' 'os.path.exists("dar") and open("dar").read()'
  10000 loops, best of 3: 36.4 usec per loop

  python -m 'timeit' -s 'import os' $'try:open("dar").read()\nexcept IOError: pass'
  10000 loops, best of 3: 22 usec per loop

nonexistent file::

  rm foo

  python -m 'timeit' -s 'import os' 'os.path.exists("foo") and open("foo").read()'
  10000 loops, best of 3: 29.8 usec per loop

  python -m 'timeit' -s 'import os' $'try:open("foo").read()\nexcept IOError: pass'
  10000 loops, best of 3: 27.7 usec per loop

As you can see, there is a bit of a difference. :)

Note that this was qualified with "If it's FS related code"; syscalls
are not cheap- if it's not triggering syscalls, the next section is
relevant.

Catching Exceptions in python code (rather then cpython) isn't cheap
====================================================================

stats from python-2.4.2

When an exception is caught::

  python -m 'timeit' -s 'd=dict(zip(range(1000), range(1000)))' $'try: d[1999]\nexcept KeyError: pass'
  100000 loops, best of 3: 8.7 usec per loop

  python -m 'timeit' -s 'd=dict(zip(range(1000), range(1000)))' $'1999 in d and d[1999]'
  1000000 loops, best of 3: 0.492 usec per loop

When no exception is caught, overhead of try/except setup::

  python -m 'timeit' -s 'd=dict(zip(range(1000), range(1000)))' $'try: d[0]\nexcept KeyError: pass'
  1000000 loops, best of 3: 0.532 usec per loop

  python -m 'timeit' -s 'd=dict(zip(range(1000), range(1000)))' $'d[0]'
  1000000 loops, best of 3: 0.407 usec per loop


This doesn't advocate writing code that doesn't protect itself- just be aware
of what the code is actually doing, and be aware that exceptions in
python code are costly due to the machinery involved.

Another example is when to use or not to use dict's setdefault or get methods:

key exists::

  # Through exception handling
  python -m timeit -s 'd=dict.fromkeys(range(100))' 'try: x=d[1]' 'except KeyError: x=42'
  1000000 loops, best of 3: 0.548 usec per loop

  # d.get
  python -m timeit -s 'd=dict.fromkeys(range(100))' 'x=d.get(1, 42)'
  1000000 loops, best of 3: 1.01 usec per loop


key doesn't exist::

  # Through exception handling
  python -m timeit -s 'd=dict.fromkeys(range(100))' 'try: x=d[101]' 'except KeyError: x=42'
  100000 loops, best of 3: 8.8 usec per loop

  # d.get
  python -m timeit -s 'd=dict.fromkeys(range(100))' 'x=d.get(101, 42)'
  1000000 loops, best of 3: 1.05 usec per loop


The short version of this is: if you know the key is there, dict.get()
is slower. If you don't, get is your friend. In other words, use it
instead of doing a containment test and then accessing the key.

Of course this only considers the case where the default value is
simple. If it's something more costly "except" will do relatively
better since it's not constructing the default value if it's not
needed. So if in doubt and in a performance-critical piece of code:
benchmark parts of it with timeit instead of assuming "exceptions are
slow" or "[] is fast".

cpython 'leaks' vars into local namespace for certain constructs
================================================================

::

  def f(s):
      while True:
          try:
              some_func_that_throws_exception()
          except Exception, e:
              # e exists in this namespace now.
              pass
          # some other code here...

From the code above, e bled into the f namespace- that's referenced
memory that isn't used, and will linger until the while loop exits.

Python _does_ bleed variables into the local namespace- be aware of
this, and explicitly delete references you don't need when dealing in
large objs, especially dealing with exceptions::

  class c:
      d = {}
      for x in range(1000):
          d[x] = x

While the class above is contrived, the thing to note is that
c.x is now valid- the x from the for loop bleeds into the class
namespace and stays put.

Don't leave uneeded vars lingering in class namespace.

Variables that leak from for loops _normally_ aren't an issue, just be
aware it does occur- especially if the var is referencing a large object
(thus keeping it in memory).

So... for loops leak, list comps leak, dependent on your except
clause they can also leak.

Do not go overboard with this though. If your function will exit soon
do not bother cleaning up variables by hand. If the "leaking" things
are small do not bother either.

The current code deletes exception instances explicitly much more
often than it should since this was believed to clean up the traceback
object. This does not work: the only thing "del e" frees up is the
exception instance and the arguments passed to its constructor. "del
e" also takes a small amount of time to run (clearing up all locals
when the function exits is faster).

Unless you need to generate (and save) a range result, use xrange
=================================================================

::
  python -m timeit 'for x in range(10000): pass'
  100 loops, best of 3: 2.01 msec per loop

  $ python -m timeit 'for x in xrange(10000): pass'
  1000 loops, best of 3: 1.69 msec per loop

Removals from a list aren't cheap, especially left most
=======================================================

If you _do_ need to do left most removals, the deque module is your friend.

Rightmost removals aren't too cheap either, depending on what idiocy people
come up with to try and 'help' the interpreter::

  python -m timeit $'l=range(1000);i=0;\nwhile i < len(l):\n\tif l[i]!="asdf":del l[i]\n\telse:i+=1'
  100 loops, best of 3: 4.12 msec per loop

  python -m timeit $'l=range(1000);\nfor i in xrange(len(l)-1,-1,-1):\n\tif l[i]!="asdf":del l[i]'
  100 loops, best of 3: 3 msec per loop

  python -m timeit 'l=range(1000);l=[x for x in l if x == "asdf"]'
  1000 loops, best of 3: 1 msec per loop

Granted, that's worst case, but the worst case is usually where people
get bitten (note the best case still is faster for list comprehension).

On a related note, don't pop() unless you have a reason to.

If you're testing for None specifically, be aware of the 'is' operator
======================================================================

Is avoids the equality protocol, and does a straight ptr comparison::

  python -m timeit '10000000 != None'
  1000000 loops, best of 3: 0.721 usec per loop

  $ python -m timeit '10000000 is not None'
  1000000 loops, best of 3: 0.343 usec per loop


Note that we're specificially forcing a large int; using 1 under 2.5 is the
same runtime, the reason for this is that it defaults to an identity check,
then a comparison; for small ints, python uses singletons, thus identity kicks in.

Deprecated/crappy modules
=========================

- Don't use types module. Use isinstance (this isn't a speed reason,
  types sucks).
- Don't use strings module. There are exceptions, but use string
  methods when available.
- Don't use stat module just to get a stat attribute- e.g.,::
    import stats
    l=os.stat("asdf")[stat.ST_MODE]

    # can be done as (and a bit cleaner)
    l=os.stat("asdf").st_mode


Know the exceptions that are thrown, and catch just those you're interested in
==============================================================================

::

  try:
      blah
  except Exception:
      blah2

There is a major issue here. It catches SystemExit exceptions (triggered by
keyboard interupts); meaning this code, which was just bad exception handling
now swallows Ctrl+c (meaning it now screws with UI code).

Catch what you're interested in *only*.

tuples versus lists.
====================

The former is immutable, while the latter is mutable.

Lists over-allocate (a cpython thing), meaning it takes up more memory
then is used (this is actually a good thing usually).

If you're generating/storing a lot of sequences that shouldn't be
modified, use tuples. They're cheaper in memory, and people can reference
the tuple directly without being concerned about it being mutated elsewhere.

However, using lists there would require each consumer to copy the list
to protect themselves from mutation. So... over-allocation +
allocating a new list for each consumer.

Bad, mm'kay.

Don't try to copy immutable instances (e.g. tuples/strings)
===========================================================

Example: copy.copy((1,2,3)) is dumb; nobody makes a mistake that obvious,
but in larger code people do (people even try using [:] to copy a
string; it returns the same string since it's immutable).

You can't modify them, therefore there is no point in trying to make copies of them.


__del__ methods mess with garbage collection
============================================

__del__ methods have the annoying side affect of blocking garbage
collection when that instance is involved in a cycle- basically, the
interpreter doesn't know what __del__ is going to reference, so it's
unknowable (general case) how to break the cycle.

So... if you're using __del__ methods, make sure the instance doesn't
wind up in a cycle (whether careful data structs, or weakref usage).

A general point: python isn't slow, your algorithm is
=====================================================

::

  l = []
  for x in data_generator():
      if x not in l:
          l.append(x)

That code is _best_ case O(1) (e.g., yielding all 0's). The worst case is
O(N^2).

::

  l=set()
  for x in data_generator():
      if x not in l:
          l.add(x)

Best/Worst are now constant (this isn't strictly true due to the potential
expansion of the set internally, but that's ignorable in this case).

Furthermore, the first loop actually invokes the __eq__ protocol for x for
each element, which can potentially be *quite* slow if dealing in
complex objs.

The second loop invokes __hash__ once on x instead (technically the set
implementation may invoke __eq__ if a collision occurs, but that's an implementation
detail).

Technically, the second loop still is a bit innefficient::

  l=set(data_generator())

is simpler and faster.

An example data for people who don't see how _bad_ this can get::

  python -m timeit $'l=[]\nfor x in xrange(1000):\n\tif x not in l:l.append(x)'
  10 loops, best of 3: 74.4 msec per loop

  python -m timeit $'l=set()\nfor x in xrange(1000):\n\tif x not in l:l.add(x)'
  1000 loops, best of 3: 1.24 msec per loop

  python -m timeit 'l=set(xrange(1000))'
  1000 loops, best of 3: 278 usec per loop

The difference here is obvious.

This does _not_ mean that sets are automatically better everywhere,
just be aware of what you're doing- for a single search of a range,
the setup overhead is far slower then a linear search.  Nature of sets, while
the implementation may be able to guess the proper list size, it still has to
add each item in; if it *cannot* guess the size (ie, no size hint, generator,
iterator, etc), it has to just keep adding items in, expanding the set as
needed (which requires linear walks for each expansion).  While this may seem
obvious, people sometimes do effectively the following::

  python -m timeit -s 'l=range(50)' $'if 1001 in set(l): pass'
  100000 loops, best of 3: 12.2 usec per loop

  python -m timeit -s 'l=range(50)' $'if 1001 in l: pass'
  10000 loops, best of 3: 7.68 usec per loop

What's up with __hash__ and dicts
=================================

A bunch of things (too many things most likely) in the codebase define
__hash__. The rule for __hash__ is (quoted from
http://docs.python.org/ref/customization.html):

 Should return a 32-bit integer usable as a hash value for dictionary
 operations. The only required property is that objects which compare
 equal have the same hash value.

Here's a quick rough explanation for people who do not know how a "dict" works
internally:

- Things added to it are dumped in a "bucket" depending on their hash
  value.
- To check if something is in the dict it first determines the bucket
  to check (based on hash value), then does equality checks (__cmp__
  or __eq__ if there is one, otherwise object identity comparison) for
  everything in the bucket (if there is anything).

So what does this mean?

- There's no reason at all to define your own __hash__ unless you also
  define __eq__ or __cmp__. The behaviour of your object in dicts/sets
  will not change, it will just be slower (since your own __hash__ is
  almost certainly slower than the default one).
- If you define __eq__ or __cmp__ and want your object to be usable in
  a dict you have to define __hash__. If you don't the default
  __hash__ is used which means your objects act in dicts like only
  object identity matters *until* you hit a hash collision and your
  own __eq__ or __cmp__ kicks in.
- If you do define your own __hash__ it has to produce the same value
  for objects that compare equal, or you get *really* weird behaviour
  in dicts/sets ("thing in dict" returning False because the hash
  values differ while "thing in dict.keys()" returns True because that
  does not use the hash value, only equality checks).
- If the hash value changes after the object was put in a dict you get
  weird behaviour too ("s=set([thing]); thing.change_hash();thing in s"
  is False, but "thing in list(s)" is True). So if your objects are
  mutable they can usually provide __eq__/__cmp__ but not __hash__.
- Not having many hash "collisions" (same hash value for objects that
  compare nonequal) is good, but collisions are not illegal. Too many
  of them just slow down dict/set operations (in a worst case scenario
  of the same hash for every object dict/set operations become linear
  searches through the single hash bucket everything ends up in).
- If you use the hash value directly keep in mind that collisions are
  legal. Do not use comparisons of hash values as a substitute for
  comparing objects (implementing __eq__ / __cmp__). Probably the only
  legitimate use of hash() is to determine an object's hash value
  based on things used for comparison.


__eq__ and __ne__
=================

From http://docs.python.org/ref/customization.html:

  There are no implied relationships among the comparison operators.
  The truth of x==y does not imply that x!=y is false. Accordingly,
  when defining __eq__(), one should also define __ne__() so that the
  operators will behave as expected.

They really mean that. If you define __eq__ but not __ne__ doing "!="
on instances compares them by identity. This is surprisingly easy to
miss, especially since the natural way to write unit tests for classes
with custom comparisons goes like this::

  self.assertEqual(YourClass(1), YourClass(1))
  # Repeat for more possible values. Uses == and therefore __eq__,
  # behaves as expected.
  self.assertNotEqual(YourClass(1), YourClass(2))
  # Repeat for more possible values. Uses != and therefore object
  # identity, so they all pass (all different instances)!

So you end up only testing __eq__ on equal values (it can say
"identical" for different values without you noticing).

Adding a __ne__ that just does "return not self == other" fixes this.


__eq__/__hash__ and subclassing
===============================

If your class has a custom __eq__ and it might be subclassed you have
to be very careful about how you "compare" to instances of a subclass.
Usually you will want to be "different" from those unconditionally::

  def __eq__(self, other):
      if self.__class is not YourClass or other.__class__ is not YourClass:
          return False
      # Your actual code goes here

This might seem like overkill, but it is necessary to avoid problems if
you are subclassed and the subclass does not have a new __eq__. If you
just do an "isinstance(other, self.__class__)" check you will compare
equal to instances of a subclass, which is usually not what you want.
If you just check for "self.__class__ is other.__class__" then
subclasses that add a new attribute without overriding __eq__ will
compare equal when they should not (because the new attribute
differs).

If you subclass something that has an __eq__ you should most likely
override it (you might get away with not doing so if the class does
not do the type check demonstrated above). If you add a new attribute
don't forget to override __hash__ too (that is not critical, but you
will have unnecessary hash collisions if you forget it).

This is especially important for pkgcore because of
pkgcore.util.caching. If an instance of a class with a broken __eq__
is used as argument for the __init__ of a class that uses
caching.WeakInstMeta it will cause a cached instance to be used when
it should not. Notice the class with the broken __eq__ does not have
to be cached itself to trigger this! Getting this wrong can cause fun
behaviour like atoms showing up in the list of fetchables because the
restrictions they're in compare equal independent of their "payload".


Exception subclassing
=====================

It is pretty common for an Exception subclass to want to customize the
return value of str() on an instance. The easiest way to do that is::

  class MyException(Exception):

      """Describe when it is raised here."""

      def __init__(self, stuff):
          Exception.__init__(self, 'MyException because of %s' % (stuff,))

This is usually easier than defining a custom __str__ (since you do
not have to store the value of "stuff" as an attribute) and you should
be calling the base class __init__ anyway.

(This does not mean you should never store things like "stuff" as
attrs: it can be very useful for code catching the exception to have
access to it. Use common sense.)


Memory debugging
================

Either heappy, or dowser are the two currently recommended tools.

To use dowser, insert the following into the code wherever you'd like
to check the heap- this is blocking also::

  import cherrpy
  import dowser
  cherrypy.config.update({'engine.autoreload_on': False})
  try:
    cherrypy.quickstart(dowser.Root())
  except AttributeError:
    cherrypy.root = dowser.Root()
    cherrypy.server.start()


For using heappy, see the heappy documentation in pkgcore/dev-notes.
