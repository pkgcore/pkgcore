=====================================
 Config use and implementation notes
=====================================

Using the manager
=================

Normal use
----------

To get at the user's configuration::

 from pkgcore.config import load_config
 config = load_config()
 main_repo = config.get_default('repo')
 spork_repo = config.repo['spork']

Usually this is everything you need to know about the manager. Some
things to be aware of:

- Some of the managed sources of configuration data may be slow, so
  accessing a source is delayed for as long as possible. Some things
  require accessing all sources though and should therefore be
  avoided. The easiest one to trigger is config.repo.keys() or the
  equivalent list(config.sections('repo')). This has to get the
  "class" setting for every available config section, which might be
  slow.
- For the same reason the manager does not know what type names exist
  (there is no hardcoded list of them, so the only way to get that
  information would be loading all config sections). This is why you
  can get this::

   >>> load_config().section('repo') # typo, should be "sections"
   Traceback (most recent call last):
     File "<stdin>", line 1, in ?
   TypeError: '_ConfigMapping' object is not callable

  This constructed a dictlike object for accessing all config sections
  of the type "section", then tried to call it.

Testcase use
------------

For testing of high-level scripts it can be useful to construct a
config manager containing hardcoded values::

 from pkgcore.config import basics, central

 config = central.ConfigManager([{
     'repo' = basics.HardCodedConfigSection({'class': my_repo,
                                             'data': ['1', '2']}),
     'cont' = basics.ConfigSectionFromStringDict({'class': 'pkgcore.my.cont',
                                                  'ref': 'repo'}),
     }])

What this does should be fairly obvious. Be careful you do not use the
same ConfigSection object in more than one place: caching will not
behave the way you want. See `Adding a config source`_ for details.

Adding a configurable
=====================

You often do not really *have* to do anything to make something a
valid "class" value, but it is clearer and it is necessary in certain
cases.

Adding a class
--------------

To make a class available, do this::

 from pkgcore.config import ConfigHint, errors

 class MyRepo:

     pkgcore_config_type = ConfigHint({'cache': 'section_ref'},
                                      typename='repo')

     def __init__(self, repo):
         try:
             self.initialize(repo)
         except SomeRandomException:
             raise errors.InstantiationError('eep!')

The first ConfigHint arg tells the config system what kind of
arguments you take. Without it it assumes arguments with no default
are strings and guesses for the other args based on the type of the
default value. So if you have no default values or they are just None
you should tell the system about your args.

The second one tells it you fulfill the repo "protocol", meaning your
instances will show up in load_config().repo.

ConfigHint takes some more arguments, see the api docs for details.

Adding a callable
-----------------

To make a callable available you can do this::

 from pkgcore.config.hint import configurable

 @configurable({'cache': 'section_ref'}, typename=repo)
 def my_repo(repo):
     # do stuff

configurable is just a convenience function that applies a ConfigHint.

Exception handling
------------------

If you raise an exception when the config system calls you it will
catch the exception and wrap it in an InstantiationError. This is good
for calling code since catching and printing those provides the user
with a readable description of what happened. It is less good for
developers since the raising of a new exception kills the traceback
printed in debug mode. You will have a traceback that "ends" in the
config code handling instantiation.

You can improve this by raising an InstantiationError yourself. If you
do this the config system will be able to add the extra information
needed for a user-friendly error message to it without raising a new
exception, meaning debug mode will give a traceback leading right back
to your code raising the InstantiationError.

Adding a config source
======================

Config sources are pretty straightforward: they are mappings from a
section name to a ConfigSection subclass. The only tricky thing is the
combination of section references and caching. The general rule is "do
not expose the same ConfigSection in more than one way". If you do it
will be collapsed and instantiated once for every way it is exposed,
which is usually not what you want. An example::

 from pkgcore.config import basics
 from pkgcore.config.hint import configurable

 def example():
     return object()

 @configurable({'ref': 'section_ref'})
 def nested(ref):
     return ref

 multi = basics.HardCodedConfigSection({'class': example})

 myconf = {
     'multi': multi,
     'bad': basics.HardCodedConfigSection({'class': nested, 'ref': multi})
     'good': basics.ConfigSectionFromStringDict({'class': 'nested',
                                                 'ref': 'multi'})

If you feed this to the ConfigManager and instantiate everything
"multi" and "good" will be identical but "bad" will be a different
object. For an explanation of why this happens see the implementation
notes in the next section.

You trigger a similar problem if you create a custom ConfigSection
subclass that bypasses central's collapse_named_section for named
section refs. If you somehow get at the referenced ConfigSection and
hand it to collapse_section you will most likely circumvent caching.
Only use collapse_section for unnamed sections.

ConfigManager tries not to extract more things from this mapping than
it has to. Specifically, it will not call __getitem__ before it needs
to instantiate the section or needs to know its type. However it
*will* iterate over the keys (section names) immediately to find
autoloads. If this is a problem (getting those names is slow) then
make sure the manager knows your config is "remote".

Implementation notes
====================

This code has evolved quite a bit over time. The current code/design
tries among other things to:

- Allow sections to contain both named and nameless/inline references
  to other sections.
- Allow serialization of the loaded config.
- Not do unnecessary work (if possibly not recollapse configs,
  definitely not trigger unnecessary imports, access configs
  unnecessarily, reinstantiate configs)
- Provide both end-user error messages that are complete enough to
  track down a problem in a complex nested config and tracebacks that
  reach back to actual buggy code for developers.

Overview from load_config() to instantiated repo
------------------------------------------------

When you call load_config() it looks up what config files are available
(/etc/pkgcore/pkgcore.conf, ~/.config/pkgcore/pkgcore.conf,
/etc/portage/make.conf) and loads them. This produces a dict mapping section
names to ConfigSection instances. For the ini-format pkgcore.conf files this is
straightforward, for make.conf this is a lot of work done in
pkgcore.ebuild.portage_conf. I'm not going to describe that module here, read
the source for details.

The ConfigSections have a pretty straightforward api: they work like
dicts but get passed a string describing what "type" the value should
be and a central.ConfigManager instance for reasons described later.
Passing in this "type" string when getting the value is necessary
because the way things like lists of strings are stored depends on the
format of the configuration file but the parser does not have enough
information to know it should parse as a list instead of a string. For
example, an ini-format pkgcore.conf could contain::

  [my-overlay-cache]
  class=pkgcore.cache.flat_hash.database
  auxdbkeys=DEPEND RDEPEND

We want to turn that auxdbkeys value into a list of strings in the ini
file parser code instead of in the central.ConfigManager or even
higher up because more exotic config sections may want to store this
in a different way (perhaps as a comma-separated list, or even as
"<el>DEPEND</el><el>RDEPEND</el>". But there is obviously not enough
information in the ini file for the parser to know this is meant as a
list instead of a string with a space in it.

central.ConfigManager gets instantiated with one or more of those
dicts mapping section names to ConfigSections. They're split up into
normal and "remote" configs which I'll describe later, let's assume
they're all "remote" for now. In that case no work is done when the
ConfigManager is instantiated.

Getting an actual configured object out of the ConfigManager is split
in two phases. First the involved config sections are "collapsed":
inherits are processed, values are converted to the right type,
presence of required arguments is checked, etc. Everything up to
actually instantiating the target class and actually instantiating any
section references it needs. The result of this work is bundled in a
CollapsedConfig instance. Actual instantiation is handled by the
CollapsedConfig instance.

The ConfigManager manages CollapsedConfig instances. It creates new
ones if required and makes sure that if a cached instance is available
it is used.

For the remainder of the example let's assume our config looks like
this::

  [spork]
  inherit=cache
  auxdbkeys=DEPEND RDEPEND

  [cache]
  class=pkgcore.cache.flat_hash.database

Running config.repo['spork'] runs
config.collapse_named_section('spork'). This first checks if this
section was already collapsed and returns the CollapsedConfig if it is
available. If it is not in the cache it looks up the ConfigSection
with that name in the dicts handed to the ConfigManager on
instantiation and calls collapse_section on it.

collapse_section first recursively finds any inherited sections (just
the "cache" section in this case). It then grabs the 'class' setting
(which is always of type 'callable'). In this case that's
"pkgcore.cache.flat_hash.database", which the ConfigSection imports
and returns. This is then wrapped in a config.basics.ConfigType. A
ConfigType contains the information necessary to validate arguments
passed to the callable. It uses the magic pkgcore_config_type
attribute if the callable has it and introspection for everything
else. In this case
pkgcore.cache.flat_hash.database.pkgcore_config_type is a ConfigHint
stating the "auxdbkeys" argument is of type "list".

Now that collapse_section has a ConfigType it uses it to retrieve the
arguments from the ConfigSections and passes the ConfigType and
arguments to CollapsedConfig's __init__. Then it returns the
CollapsedConfig instance to collapse_named_section.
collapse_named_section caches it and returns it.

Now we're back in the __getattr__ triggered by config.repo['spork'].
This checks if the ConfigType on the CollapsedConfig is actually
'repo', and returns collapsedConfig.instantiate() if this matches.

Lazy section references
-----------------------

The main reason the above is so complicated is to support various
kinds of references to other sections. Example::

  [spork]
  class=pkgcore.Spork
  ref=foon

  [foon]
  class=pkgcore.Foon

Let's say pkgcore.Spork has a ConfigHint stating the type of the "ref"
argument is "lazy_ref:foon" (lazy reference to a foon) and its typename is
"repo", and pkgcore.Foon has a ConfigHint stating its typename is
"foon". a "lazy reference" is an instance of basics.LazySectionRef,
which is an object containing just enough information to produce a
CollapsedConfig instance. This is not the most common kind of
reference, but it is simpler from the config point of view so I'm
describing this one first.

When collapse_section runs on the "spork" section it calls
section.get_value(self, 'ref:repo', 'section_ref'). "lazy_ref" in the
type hint is converted to just "ref" here because the ConfigSections
do not have to distinguish between lazy and "normal" references.
Because this particular ConfigSection only supports named
references it returns a LazyNamedSectionRef(central, 'ref:repo',
'foon'). This just gets handed to Spork's __init__. If the Spork
decides to call instantiate() on the LazyNamedSectionRef it calls
central.collapse_named_section('foon'), checks if the result is of
type foon, instantiates it and returns it.

The same thing using a dhcp-style config::

  spork {
      class pkgcore.Spork;
      ref {
          class pkgcore.Foon;
      };
  }

In this format the reference is an inline unnamed section. When
get_value(central, 'ref:repo', 'foon') is called it returns a
LazyUnnamedSectionRef(central, 'ref:repo', section) where section is a
ConfigSection instance for the nested section (knowing just that
"class" is "pkgcore.Foon" in this case). This is handed to
Spork.__init__. If Spork calls instantiate() on it it calls
central.collapse_section(self.section) and does the same type checking
and instantiating LazyNamedSectionRef did.

Notice neither Spork nor ConfigManager care if the reference is inline
or named. get_value just has to return a LazySectionRef instance
(LazyUnnamedSectionRef and LazyNamedSectionRef are subclasses of
this). How this actually gets a referenced config section is up to the
ConfigSection whose get_value gets called.

Normal section references
-------------------------

If Spork's ConfigHint defines the type of its "ref" argument as
"ref:foon" instead of "lazy_ref:foon" it gets handed an actual Foon
instance instead of a LazySectionRef to one. This is built on top of
the lazy reference code. For the ConfigSections nothing changes (the
same get_value call is made). But the ConfigManager now immediately
calls collapse() on the LazySectionRef, retrieving a CollapsedConfig
instance (for the "foon"). This is handed to the CollapsedConfig for
"spork", and when this one is instantiated the referenced
CollapsedConfig is also instantiated.

Miscellaneous details
---------------------

The support for nameless sections means neither ConfigSection nor
CollapsedConfig have a name attribute. This makes the error handling
code a bit tricky as it has to tag in the name at various points, but
this works better than enforcing names where it does not make sense
(means lots of unnecessary duplication of names when dealing with
dicts of HardCoded/StringBasedConfigSections).

The suppport for serialization of the loaded config means section_refs
cannot be instantiated straight away. The object used for
serialization is the CollapsedConfig which gives you both the actual
values and the type they have. If the CollapsedConfig contained
arbitrary instantiated objects serializing them would be impossible.
So it contains nested CollapsedConfigs instead.

Not doing unnecessary work is done by caching in two places. The
simple one is CollapsedConfig caching its instantiated value. This is
pretty straightforward. The more subtle one is ConfigManager caching
CollapsedConfigs by name. It is obviously a good idea to cache these
(if we didn't we would have to cache the instantiated value in the
ConfigManager). An alternative would be caching them by their
ConfigSection. This has the minor disadvantage of keeping the
ConfigSection in memory, and the larger one that it may break caching
for weird config sources that generate ConfigSections on demand. The
downside of caching by name is we have to make sure nothing generates
a CollapsedConfig for a named section in a way other than
collapse_named_section (handing the ConfigSection to collapse_section
bypasses caching).

This means a ConfigSection cannot return a raw ConfigSection from a
section_ref get_value call. If it was a ConfigSection that central
then collapsed and the reference was actually to a named section
caching is bypassed.

The need for a section name starting with "autoload" is also there to
avoid unnecessary work. Without this we would have to figure out the
typename of every section. While we can do that without entirely
collapsing the config we cannot avoid importing the "class", which
means load_config() would import most of pkgcore. That should
definitely be avoided.
