# Copyright: 2005 Marien Zwart <marienz@gentoo.org>
# License: GPL2


import operator

from pkgcore.test import TestCase

from pkgcore.config import central, basics, errors, configurable


# A bunch of functions used from various tests below.
def repo(cache):
    return cache
@configurable({'content': 'section_ref', 'contents': 'section_refs'})
def drawer(content=None, contents=None):
    return content, contents

# The exception checks here also check if the str value of the
# exception is what we expect. This does not mean the wording of the
# error messages used here is strictly required. It just makes sure
# the error we get is the expected one and is useful. Please make sure
# you check for a sensible error message when more tests are added.

# A lot of the ConfigManager instances get object() as a remote type.
# This makes sure the types are not unnecessarily queried (since
# querying object() will blow up).

class RemoteSource(object):

    """Use this one for tests that do need the names but nothing more."""

    def __iter__(self):
        return iter(('remote',))

    def __getitem__(self, key):
        raise NotImplementedError()


class ConfigManagerTest(TestCase):

    def check_error(self, message, func, *args, **kwargs):
        """Like assertRaises but checks for the message string too."""
        klass = kwargs.pop('klass', errors.ConfigurationError)
        try:
            func(*args, **kwargs)
        except klass, e:
            self.assertEquals(
                message, str(e),
                '\nGot:\n%s\nExpected:\n%s\n' % (message, str(e)))
        else:
            self.fail('no exception raised')

    def test_sections(self):
        manager = central.ConfigManager(
            [{'fooinst': basics.HardCodedConfigSection({'class': repo}),
              'barinst': basics.HardCodedConfigSection({'class': drawer}),
              }])
        self.assertEquals(['barinst', 'fooinst'], sorted(manager.sections()))
        self.assertEquals(manager.drawer.keys(), ['barinst'])
        self.assertEquals(manager.drawer, {'barinst': (None, None)})

    def test_contains(self):
        manager = central.ConfigManager(
            [{'spork': basics.HardCodedConfigSection({'class': drawer})}],
            [RemoteSource()])
        self.assertIn('spork', manager.drawer)
        self.assertNotIn('foon', manager.drawer)

    def test_no_class(self):
        manager = central.ConfigManager(
            [{'foo': basics.HardCodedConfigSection({})}], [object()])
        self.check_error(
            "Collapsing section named 'foo':\n"
            'no class specified',
            manager.collapse_named_section, 'foo')

    def test_missing_section_ref(self):
        manager = central.ConfigManager(
            [{'rsync repo': basics.HardCodedConfigSection({'class': repo}),
              }], [object()])
        self.check_error(
            "Collapsing section named 'rsync repo':\n"
            "type pkgcore.test.config.test_central.repo needs settings for "
            "'cache'",
            operator.getitem, manager.repo, 'rsync repo')

    def test_unknown_type(self):
        manager = central.ConfigManager(
            [{'spork': basics.HardCodedConfigSection({'class': drawer,
                                                      'foon': None})}],
            [object()])
        self.check_error(
            "Collapsing section named 'spork':\n"
            "Type of 'foon' unknown",
            manager.collapse_named_section, 'spork')

    def test_missing_inherit_target(self):
        manager = central.ConfigManager(
            [{'myrepo': basics.HardCodedConfigSection({
                            'class': repo,
                            'inherit': ['baserepo'],
                            }),
              }], [RemoteSource()])
        self.check_error(
            "Collapsing section named 'myrepo':\n"
            "inherit target 'baserepo' cannot be found",
            operator.getitem, manager.repo, 'myrepo')

    def test_inherit_unknown_type(self):
        manager = central.ConfigManager(
            [{'baserepo': basics.HardCodedConfigSection({
                            'cache': 'available',
                            }),
              'actual repo': basics.HardCodedConfigSection({
                            'class': drawer,
                            'inherit': ['baserepo'],
                            }),
              }], [object()])
        self.check_error(
            "Collapsing section named 'actual repo':\n"
            "Type of 'cache' inherited from 'baserepo' unknown",
            operator.getitem, manager.repo, 'actual repo')

    def test_inherit(self):
        manager = central.ConfigManager(
            [{'baserepo': basics.HardCodedConfigSection({
                            'cache': 'available',
                            'inherit': ['unneeded'],
                            }),
              'unneeded': basics.HardCodedConfigSection({
                            'cache': 'unavailable'}),
              'actual repo': basics.HardCodedConfigSection({
                            'class': repo,
                            'inherit': ['baserepo'],
                            }),
              }], [object()])

        self.assertEquals('available', manager.repo['actual repo'])

    def test_incremental(self):
        @configurable({'inc': 'list'}, required=['inc'], incrementals=['inc'])
        def myrepo(*args, **kwargs):
            return args, kwargs
        manager = central.ConfigManager(
            [{'baserepo': basics.HardCodedConfigSection({'inc': ['basic']}),
              'actual repo': basics.HardCodedConfigSection({
                            'class': myrepo,
                            'inherit': ['baserepo'],
                            'inc': ['extended']
                            }),
              }], [object()])
        self.assertEquals(
            ((), {'inc': ['basic', 'extended']}),
            manager.myrepo['actual repo'])

    def test_no_object_returned(self):
        def noop():
            """Do not do anything."""
        manager = central.ConfigManager(
            [{'myrepo': basics.HardCodedConfigSection({'class': noop}),
              }], [object()])
        self.check_error(
            "'No object returned' instantiating "
            "pkgcore.test.config.test_central.noop",
            manager.collapse_named_section('myrepo').instantiate)

    def test_not_callable(self):
        class myrepo(object):
            def __repr__(self):
                return 'useless'
        manager = central.ConfigManager(
            [{'myrepo': basics.HardCodedConfigSection({'class': myrepo()}),
              }], [object()])
        self.check_error(
            "Collapsing section named 'myrepo':\n"
            "Converting argument 'class' to callable:\n"
            "useless is not callable",
            operator.getitem, manager.myrepo, 'myrepo')

    def test_raises_instantiationerror(self):
        def myrepo():
            raise errors.InstantiationError('I raised')
        manager = central.ConfigManager(
            [{'myrepo': basics.HardCodedConfigSection({'class': myrepo}),
              }], [object()])
        self.check_error(
            "Instantiating named section 'myrepo':\n"
            "'I raised' instantiating pkgcore.test.config.test_central.myrepo",
            operator.getitem, manager.myrepo, 'myrepo',
            klass=errors.InstantiationError)

    def test_raises(self):
        def myrepo():
            raise ValueError('I raised')
        manager = central.ConfigManager(
            [{'myrepo': basics.HardCodedConfigSection({'class': myrepo})
              }], [object()])
        self.check_error(
            "Instantiating named section 'myrepo':\n"
            "Caught exception 'I raised' instantiating "
            'pkgcore.test.config.test_central.myrepo',
            operator.getitem, manager.myrepo, 'myrepo')
        manager = central.ConfigManager(
            [{'myrepo': basics.HardCodedConfigSection({'class': myrepo})
              }], [object()], debug=True)
        self.check_error('I raised',
                         operator.getitem, manager.myrepo, 'myrepo',
                         klass=ValueError)

    def test_pargs(self):
        @configurable(types={'p': 'str', 'notp': 'str'},
                      positional=['p'], required=['p'])
        def myrepo(*args, **kwargs):
            return args, kwargs
        manager = central.ConfigManager(
            [{'myrepo': basics.HardCodedConfigSection({
                            'class': myrepo,
                            'p': 'pos',
                            'notp': 'notpos',
                            }),
              }], [object()])

        self.assertEquals(
            manager.myrepo['myrepo'], (('pos',), {'notp': 'notpos'}))

    def test_autoexec(self):
        @configurable(typename='configsection')
        def autoloader():
            return {'spork': basics.HardCodedConfigSection({'class': repo,
                                                            'cache': 'test'})}

        manager = central.ConfigManager(
            [{'autoload-sub': basics.HardCodedConfigSection({
                            'class': autoloader,
                            })}])
        self.assertEquals(['autoload-sub', 'spork'], list(manager.sections()))
        self.assertEquals(['spork'], manager.repo.keys())
        self.assertEquals(
            'test',
            manager.collapse_named_section('spork').instantiate())

    def test_reload(self):
        mod_dict = {'class': repo, 'cache': 'test'}

        @configurable(typename='configsection')
        def autoloader():
            return {'spork': basics.HardCodedConfigSection(mod_dict)}

        manager = central.ConfigManager(
            [{'autoload-sub': basics.HardCodedConfigSection({
                            'class': autoloader})}])

        self.assertEquals(['autoload-sub', 'spork'], list(manager.sections()))
        self.assertEquals(['spork'], manager.repo.keys())
        collapsedspork = manager.collapse_named_section('spork')
        self.assertEquals('test', collapsedspork.instantiate())
        mod_dict['cache'] = 'modded'
        self.assertIdentical(collapsedspork,
                             manager.collapse_named_section('spork'))
        self.assertEquals('test', collapsedspork.instantiate())
        manager.reload()
        newspork = manager.collapse_named_section('spork')
        self.assertNotIdentical(collapsedspork, newspork)
        self.assertEquals(
            'modded', newspork.instantiate(),
            'it did not throw away the cached instance')

    def test_instantiate_default_ref(self):
        manager = central.ConfigManager(
            [{'spork': basics.HardCodedConfigSection({'class': drawer})}],
            [object()])
        self.assertEquals(
            (None, None),
            manager.collapse_named_section('spork').instantiate())

    def test_allow_unknowns(self):
        @configurable(allow_unknowns=True)
        def myrepo(**kwargs):
            return kwargs

        manager = central.ConfigManager(
            [{'spork': basics.HardCodedConfigSection({
                            'class': myrepo, 'spork': 'foon'})}], [object()])

        self.assertEquals(
            {'spork': 'foon'},
            manager.collapse_named_section('spork').instantiate())

    def test_reinstantiate_after_raise(self):
        # The most likely bug this tests for is attempting to
        # reprocess already processed section_ref args.
        spork = object()
        @configurable({'thing': 'section_ref'})
        def myrepo(thing):
            self.assertIdentical(thing, spork)
            raise errors.InstantiationError('I suck')
        def spork_producer():
            return spork
        manager = central.ConfigManager(
            [{'spork': basics.HardCodedConfigSection({
                            'class': myrepo,
                            'thing': basics.HardCodedConfigSection({
                                    'class': spork_producer,
                                    }),
                            })}], [object()])
        spork = manager.collapse_named_section('spork')
        for i in range(3):
            self.check_error(
                "'I suck' instantiating "
                'pkgcore.test.config.test_central.myrepo',
                spork.instantiate, klass=errors.InstantiationError)
        for i in range(3):
            self.check_error(
                "'I suck' instantiating "
                'pkgcore.test.config.test_central.myrepo',
                manager.collapse_named_section('spork').instantiate,
                klass=errors.InstantiationError)

    def test_instantiation_caching(self):
        def myrepo():
            return object()

        manager = central.ConfigManager(
            [{'spork': basics.HardCodedConfigSection({'class': myrepo}),
              'drawer': basics.ConfigSectionFromStringDict({
                            'class': 'pkgcore.test.config.test_central.drawer',
                            'content': 'spork',
                            }),
              }], [object()])

        config = manager.collapse_named_section('spork')
        self.assertIdentical(config.instantiate(), config.instantiate())
        self.assertIdentical(
            config.instantiate(),
            manager.collapse_named_section('drawer').instantiate()[0])

    def test_collapse_named_errors(self):
        manager = central.ConfigManager(
            [{'spork': basics.ConfigSectionFromStringDict({
                            'class': 'pkgcore.test.config.test_central.drawer',
                            'content': 'ref'})}], [RemoteSource()])
        self.assertRaises(KeyError, operator.getitem, manager.repo, 'foon')
        self.check_error(
            "Collapsing section named 'spork':\n"
            "Collapsing section ref 'content':\n"
            "no section called 'ref'",
            operator.getitem, manager.repo, 'spork')

    def test_recursive_autoload(self):
        @configurable(typename='configsection')
        def autoloader():
            return {'autoload-sub': basics.HardCodedConfigSection(
                    {'class': autoloader}),
                    'spork': basics.HardCodedConfigSection({'class': repo,
                                                            'cache': 'test'})}

        self.check_error(
            "section 'autoload-sub' from autoload is already collapsed!",
            central.ConfigManager,
            [{'autoload-sub': basics.HardCodedConfigSection({
                            'class': autoloader,
                            })}], [object()])

    def test_recursive_section_ref(self):
        manager = central.ConfigManager(
            [{'spork': basics.ConfigSectionFromStringDict({
                            'class': 'pkgcore.test.config.test_central.drawer',
                            'content': 'foon'}),
              'foon': basics.ConfigSectionFromStringDict({
                            'class': 'pkgcore.test.config.test_central.drawer',
                            'content': 'spork'}),
              'self': basics.ConfigSectionFromStringDict({
                            'class': 'pkgcore.test.config.test_central.drawer',
                            'content': 'self'}),
              }], [object()])
        self.check_error(
            "Collapsing section named 'self':\n"
            "Collapsing section ref 'content':\n"
            "Reference to 'self' is recursive",
            operator.getitem, manager.drawer, 'self')
        self.check_error(
            "Collapsing section named 'spork':\n"
            "Collapsing section ref 'content':\n"
            "Collapsing section named 'foon':\n"
            "Collapsing section ref 'content':\n"
            "Reference to 'spork' is recursive",
            operator.getitem, manager.drawer, 'spork')

    def test_recursive_inherit(self):
        manager = central.ConfigManager(
            [{'spork': basics.ConfigSectionFromStringDict({
                            'class': 'pkgcore.test.config.test_central.drawer',
                            'inherit': 'foon'}),
              'foon': basics.ConfigSectionFromStringDict({
                            'class': 'pkgcore.test.config.test_central.drawer',
                            'inherit': 'spork'}),
              'self': basics.ConfigSectionFromStringDict({
                            'class': 'pkgcore.test.config.test_central.drawer',
                            'inherit': 'self'}),
              }], [object()])
        self.check_error(
            "Collapsing section named 'self':\n"
            "Inherit 'self' is recursive",
            operator.getitem, manager.drawer, 'self')
        # There is a small wart here: because collapse_section does
        # not know the name of the section it is collapsing the
        # recursive inherit of spork by foon suceeds. The re-inherit
        # of foon after that does not. As far as I can tell the only
        # effect of this is the error message is slightly inaccurate
        # (should be "inherit 'spork' is recursive").
        self.check_error(
            "Collapsing section named 'spork':\n"
            "Inherit 'foon' is recursive",
            operator.getitem, manager.drawer, 'spork')

    def test_alias(self):
        def myspork():
            return object
        manager = central.ConfigManager(
            [{'spork': basics.HardCodedConfigSection({'class': myspork}),
              'foon': basics.section_alias('spork', 'myspork'),
              }], [object()])
        # This tests both the detected typename of foon and the caching.
        self.assertIdentical(manager.myspork['spork'], manager.myspork['foon'])

    def test_typecheck(self):
        @configurable({'myrepo': 'ref:repo'}, typename='repo')
        def reporef(myrepo=None):
            return myrepo
        @configurable({'myrepo': 'refs:repo'}, typename='repo')
        def reporefs(myrepo=None):
            return myrepo
        @configurable(typename='repo')
        def myrepo():
            return 'repo!'
        manager = central.ConfigManager([{
                    'myrepo': basics.HardCodedConfigSection({'class': myrepo}),
                    'drawer': basics.HardCodedConfigSection({'class': drawer}),
                    'right':  basics.AutoConfigSection({'class': reporef,
                                                        'myrepo': 'myrepo'}),
                    'wrong':  basics.AutoConfigSection({'class': reporef,
                                                        'myrepo': 'drawer'}),
                    }], [object()])
        self.check_error(
            "Collapsing section named 'wrong':\n"
            "Collapsing section ref 'myrepo':\n"
            "reference should be of type 'repo', got 'drawer'",
            operator.getitem, manager.repo, 'wrong')
        self.assertEquals('repo!', manager.repo['right'])

        manager = central.ConfigManager([{
                    'myrepo': basics.HardCodedConfigSection({'class': myrepo}),
                    'drawer': basics.HardCodedConfigSection({'class': drawer}),
                    'right':  basics.AutoConfigSection({'class': reporefs,
                                                        'myrepo': 'myrepo'}),
                    'wrong':  basics.AutoConfigSection({'class': reporefs,
                                                        'myrepo': 'drawer'}),
                    }], [object()])
        self.check_error(
            "Collapsing section named 'wrong':\n"
            "Collapsing section refs 'myrepo':\n"
            "reference should be of type 'repo', got 'drawer'",
            operator.getitem, manager.repo, 'wrong')
        self.assertEquals(['repo!'], manager.repo['right'])

    def test_default(self):
        manager = central.ConfigManager([{
                    'thing': basics.HardCodedConfigSection({'class': drawer,
                                                            'default': True}),
                    'bug': basics.HardCodedConfigSection({'class': None,
                                                          'default': True}),
                    'ignore': basics.HardCodedConfigSection({'class': drawer}),
                    }], [object()])
        self.assertEquals((None, None), manager.get_default('drawer'))
        self.assertTrue(manager.collapse_named_section('thing').default)

        manager = central.ConfigManager([{
                    'thing': basics.HardCodedConfigSection({'class': drawer,
                                                            'default': True}),
                    'thing2': basics.HardCodedConfigSection({'class': drawer,
                                                             'default': True}),
                    }], [object()])
        self.check_error(
            "both 'thing2' and 'thing' are default for 'drawer'",
            manager.get_default, 'drawer')

        manager = central.ConfigManager([])
        self.assertIdentical(None, manager.get_default('drawer'))

    def test_broken_default(self):
        def broken():
            raise errors.InstantiationError('broken')
        manager = central.ConfigManager([{
                    'thing': basics.HardCodedConfigSection({
                            'class': drawer, 'default': True,
                            'content': basics.HardCodedConfigSection({
                                    'class': 'spork'})}),
                    'thing2': basics.HardCodedConfigSection({
                            'class': broken, 'default': True})}], [object()])
        self.check_error(
            "Collapsing default drawer 'thing':\n"
            "Collapsing section named 'thing':\n"
            "Collapsing section ref 'content':\n"
            "Converting argument 'class' to callable:\n"
            "'spork' is not callable",
            manager.get_default, 'drawer')
        self.check_error(
            "Instantiating default broken 'thing2':\n"
            "'broken' instantiating pkgcore.test.config.test_central.broken",
            manager.get_default, 'broken')

    def test_instantiate_broken_ref(self):
        def broken():
            raise errors.InstantiationError('broken')
        manager = central.ConfigManager([{
                    'one': basics.HardCodedConfigSection({
                            'class': drawer,
                            'content': basics.HardCodedConfigSection({
                                    'class': broken})}),
                    'multi': basics.HardCodedConfigSection({
                            'class': drawer,
                            'contents': [basics.HardCodedConfigSection({
                                        'class': broken})]}),
                    }], [object()])
        self.check_error(
            "Instantiating ref 'content':\n"
            "'broken' instantiating pkgcore.test.config.test_central.broken",
            manager.collapse_named_section('one').instantiate)
        self.check_error(
            "Instantiating refs 'contents':\n"
            "'broken' instantiating pkgcore.test.config.test_central.broken",
            manager.collapse_named_section('multi').instantiate)

    def test_autoload_instantiationerror(self):
        @configurable(typename='configsection')
        def broken():
            raise errors.InstantiationError('broken')
        self.check_error(
            "Instantiating autoload 'autoload_broken':\n"
            "'broken' instantiating pkgcore.test.config.test_central.broken",
            central.ConfigManager, [{
                    'autoload_broken': basics.HardCodedConfigSection({
                            'class': broken})}], [object()])

    def test_autoload_uncollapsable(self):
        self.check_error(
            "Collapsing autoload 'autoload_broken':\n"
            "Collapsing section named 'autoload_broken':\n"
            "Converting argument 'class' to callable:\n"
            "'spork' is not callable",
            central.ConfigManager, [{
                    'autoload_broken': basics.HardCodedConfigSection({
                            'class': 'spork'})}], [object()])

    def test_autoload_wrong_type(self):
        self.check_error(
            "Section 'autoload_wrong' is marked as autoload but type is "
            'drawer, not (remote)configsection',
            central.ConfigManager, [{
                    'autoload_wrong': basics.HardCodedConfigSection({
                            'class': drawer})}], [object()])

    def test_autoload_remoteconfig(self):
        @configurable(typename='remoteconfigsection')
        def remote():
            return {'autoload_spork': basics.HardCodedConfigSection({
                        'class': drawer})}
        manager = central.ConfigManager([{
                    'autoload_remote': basics.HardCodedConfigSection({
                            'class': remote})}], [RemoteSource()])
        self.assertTrue(manager.collapse_named_section('autoload_spork'))

    def test_lazy_refs(self):
        @configurable({'myrepo': 'lazy_ref:repo', 'thing': 'lazy_ref'},
                      typename='repo')
        def reporef(myrepo=None, thing=None):
            return myrepo, thing
        @configurable({'myrepo': 'lazy_refs:repo', 'thing': 'lazy_refs'},
                      typename='repo')
        def reporefs(myrepo=None, thing=None):
            return myrepo, thing
        @configurable(typename='repo')
        def myrepo():
            return 'repo!'
        manager = central.ConfigManager([{
                    'myrepo': basics.HardCodedConfigSection({'class': myrepo}),
                    'drawer': basics.HardCodedConfigSection({'class': drawer}),
                    'right':  basics.AutoConfigSection({'class': reporef,
                                                        'myrepo': 'myrepo'}),
                    'wrong':  basics.AutoConfigSection({'class': reporef,
                                                        'myrepo': 'drawer'}),
                    }], [object()])
        self.check_error(
            "reference should be of type 'repo', got 'drawer'",
            manager.repo['wrong'][0].collapse)
        self.assertEquals('repo!', manager.repo['right'][0].instantiate())

        manager = central.ConfigManager([{
                    'myrepo': basics.HardCodedConfigSection({'class': myrepo}),
                    'drawer': basics.HardCodedConfigSection({'class': drawer}),
                    'right':  basics.AutoConfigSection({'class': reporefs,
                                                        'myrepo': 'myrepo'}),
                    'wrong':  basics.AutoConfigSection({'class': reporefs,
                                                        'myrepo': 'drawer'}),
                    }], [object()])
        self.check_error(
            "reference should be of type 'repo', got 'drawer'",
            manager.repo['wrong'][0][0].collapse)
        self.assertEquals(
            ['repo!'],
            [c.instantiate() for c in manager.repo['right'][0]])

    def test_untyped_lazy_refs(self):
        @configurable({'myrepo': 'lazy_ref', 'thing': 'lazy_ref'},
                      typename='repo')
        def reporef(myrepo=None, thing=None):
            return myrepo, thing
        @configurable({'myrepo': 'lazy_refs', 'thing': 'lazy_refs'},
                      typename='repo')
        def reporefs(myrepo=None, thing=None):
            return myrepo, thing
        @configurable(typename='repo')
        def myrepo():
            return 'repo!'
        manager = central.ConfigManager([{
                    'myrepo': basics.HardCodedConfigSection({'class': myrepo}),
                    'right':  basics.AutoConfigSection({'class': reporef,
                                                        'myrepo': 'myrepo'}),
                    }], [object()])
        self.assertEquals('repo!', manager.repo['right'][0].instantiate())

        manager = central.ConfigManager([{
                    'myrepo': basics.HardCodedConfigSection({'class': myrepo}),
                    'right':  basics.AutoConfigSection({'class': reporefs,
                                                        'myrepo': 'myrepo'}),
                    }], [object()])
        self.assertEquals(
            ['repo!'],
            [c.instantiate() for c in manager.repo['right'][0]])

    def test_inherited_default(self):
        manager = central.ConfigManager([{
                    'default': basics.HardCodedConfigSection({
                            'default': True,
                            'inherit': ['basic'],
                            }),
                    'uncollapsable': basics.HardCodedConfigSection({
                            'default': True,
                            'inherit': ['spork'],
                            }),
                    'basic': basics.HardCodedConfigSection({'class': drawer}),
                    }], [RemoteSource()])
        self.assertTrue(manager.get_default('drawer'))

    def test_autoload_default_order(self):
        @configurable(typename='configsection')
        def autoloader():
            return {
                'spork': basics.HardCodedConfigSection({'class': repo,
                                                        'cache': 'test',
                                                        'default': True})}

        manager = central.ConfigManager([{
                    'autoload-sub': basics.HardCodedConfigSection({
                            'class': autoloader,
                            }),
                    'foon': basics.HardCodedConfigSection({
                            'class': repo,
                            'cache': 'foon',
                            'default': True,
                            }),
               }], [object()])
        self.assertIdentical(
            manager.collapse_named_section('foon').instantiate(),
            manager.get_default('repo'))

    def test_section_names(self):
        manager = central.ConfigManager([{
                    'thing': basics.HardCodedConfigSection({'class': drawer}),
                    }], [RemoteSource()])
        collapsed = manager.collapse_named_section('thing')
        self.assertEquals('thing', collapsed.name)
