from snakeoil.errors import walk_exception_chain
from snakeoil.test import TestCase

from pkgcore.config import basics, central, errors
from pkgcore.config.hint import configurable


# A bunch of functions used from various tests below.
def repo(cache):
    return cache
@configurable({'content': 'ref:drawer', 'contents': 'refs:drawer'})
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

class RemoteSource:

    """Use this one for tests that do need the names but nothing more."""

    def __iter__(self):
        return iter(('remote',))

    def __getitem__(self, key):
        raise NotImplementedError()


def _str_exc(exc):
    return ":\n".join(str(x) for x in walk_exception_chain(exc))

class ConfigManagerTest(TestCase):

    def check_error(self, message, func, *args, **kwargs):
        """Like assertRaises but checks for the message string too."""
        klass = kwargs.pop('klass', errors.ConfigurationError)
        try:
            func(*args, **kwargs)
        except klass as e:
            self.assertEqual(
                message, _str_exc(e),
                f'\nGot:\n{_str_exc(e)!r}\nExpected:\n{message!r}\n')
        else:
            self.fail('no exception raised')

    def get_config_obj(self, manager, obj_type, obj_name):
        types = getattr(manager.objects, obj_type)
        return types[obj_name]

    def test_sections(self):
        manager = central.ConfigManager(
            [{'fooinst': basics.HardCodedConfigSection({'class': repo}),
              'barinst': basics.HardCodedConfigSection({'class': drawer}),
              }])
        self.assertEqual(['barinst', 'fooinst'], sorted(manager.sections()))
        self.assertEqual(list(manager.objects.drawer.keys()), ['barinst'])
        self.assertEqual(manager.objects.drawer, {'barinst': (None, None)})

    def test_contains(self):
        manager = central.ConfigManager(
            [{'spork': basics.HardCodedConfigSection({'class': drawer})}],
            [RemoteSource()])
        self.assertIn('spork', manager.objects.drawer)
        self.assertNotIn('foon', manager.objects.drawer)

    def test_no_class(self):
        manager = central.ConfigManager(
            [{'foo': basics.HardCodedConfigSection({})}])
        self.check_error(
            "Collapsing section named 'foo':\n"
            'no class specified',
            manager.collapse_named_section, 'foo')

    def test_missing_section_ref(self):
        manager = central.ConfigManager(
            [{'rsync repo': basics.HardCodedConfigSection({'class': repo}),
              }])
        self.check_error(
            "Collapsing section named 'rsync repo':\n"
            "type module.config.test_central.repo needs settings for "
            "'cache'",
            self.get_config_obj, manager, 'repo', 'rsync repo')

    def test_unknown_type(self):
        manager = central.ConfigManager(
            [{'spork': basics.HardCodedConfigSection({'class': drawer,
                                                      'foon': None})}])
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
            "Inherit target 'baserepo' cannot be found",
            self.get_config_obj, manager, 'repo', 'myrepo')

    def test_inherit_unknown_type(self):
        manager = central.ConfigManager(
            [{'baserepo': basics.HardCodedConfigSection({
                            'cache': 'available',
                            }),
              'actual repo': basics.HardCodedConfigSection({
                            'class': drawer,
                            'inherit': ['baserepo'],
                            }),
              }])
        self.check_error(
            "Collapsing section named 'actual repo':\n"
            "Type of 'cache' unknown",
            self.get_config_obj, manager, 'repo', 'actual repo')

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
              }])

        self.assertEqual('available', manager.objects.repo['actual repo'])

    def test_no_object_returned(self):
        def noop():
            """Do not do anything."""
        manager = central.ConfigManager(
            [{'myrepo': basics.HardCodedConfigSection({'class': noop}),
              }])
        self.check_error(
            "Failed instantiating section 'myrepo':\n"
            "'No object returned' instantiating "
            "module.config.test_central.noop",
            manager.collapse_named_section('myrepo').instantiate)

    def test_not_callable(self):
        class myrepo:
            def __repr__(self):
                return 'useless'
        manager = central.ConfigManager(
            [{'myrepo': basics.HardCodedConfigSection({'class': myrepo()}),
              }])
        self.check_error(
            "Collapsing section named 'myrepo':\n"
            "Failed converting argument 'class' to callable:\n"
            "useless is not callable",
            self.get_config_obj, manager, 'myrepo', 'myrepo')

    def test_raises_instantiationerror(self):
        def myrepo():
            raise Exception('I raised')
        manager = central.ConfigManager(
            [{'myrepo': basics.HardCodedConfigSection({'class': myrepo}),
              }])
        self.check_error(
            "Failed instantiating section 'myrepo':\n"
            "Failed instantiating section 'myrepo': exception caught from 'module.config.test_central.myrepo':\n"
            "I raised",
            self.get_config_obj, manager, 'myrepo', 'myrepo')

    def test_raises(self):
        def myrepo():
            raise ValueError('I raised')
        manager = central.ConfigManager(
            [{'myrepo': basics.HardCodedConfigSection({'class': myrepo})
              }])
        self.check_error(
            "Failed instantiating section 'myrepo':\n"
            "Failed instantiating section 'myrepo': exception caught from 'module.config.test_central.myrepo':\n"
            "I raised",
            self.get_config_obj, manager, 'myrepo', 'myrepo')
        manager = central.ConfigManager(
            [{'myrepo': basics.HardCodedConfigSection({'class': myrepo})
              }], debug=True)
        self.check_error(
            "Failed instantiating section 'myrepo':\n"
            "Failed instantiating section 'myrepo': exception caught from 'module.config.test_central.myrepo':\n"
            "I raised",
                self.get_config_obj, manager, 'myrepo', 'myrepo',
                klass=errors.ConfigurationError)

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
              }])

        self.assertEqual(
            manager.objects.myrepo['myrepo'], (('pos',), {'notp': 'notpos'}))

    def test_autoexec(self):
        @configurable(typename='configsection')
        def autoloader():
            return {'spork': basics.HardCodedConfigSection({'class': repo,
                                                            'cache': 'test'})}

        manager = central.ConfigManager(
            [{'autoload-sub': basics.HardCodedConfigSection({
                            'class': autoloader,
                            })}])
        self.assertEqual(set(['autoload-sub', 'spork']), set(manager.sections()))
        self.assertEqual(['spork'], list(manager.objects.repo.keys()))
        self.assertEqual(
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

        self.assertEqual(set(['autoload-sub', 'spork']), set(manager.sections()))
        self.assertEqual(['spork'], list(manager.objects.repo.keys()))
        collapsedspork = manager.collapse_named_section('spork')
        self.assertEqual('test', collapsedspork.instantiate())
        mod_dict['cache'] = 'modded'
        self.assertIdentical(collapsedspork,
                             manager.collapse_named_section('spork'))
        self.assertEqual('test', collapsedspork.instantiate())
        types = manager.types
        manager.reload()
        newspork = manager.collapse_named_section('spork')
        self.assertNotIdentical(collapsedspork, newspork)
        self.assertEqual(
            'modded', newspork.instantiate(),
            'it did not throw away the cached instance')
        self.assertNotIdentical(types, manager.types)

    def test_instantiate_default_ref(self):
        manager = central.ConfigManager(
            [{'spork': basics.HardCodedConfigSection({'class': drawer})}],
            )
        self.assertEqual(
            (None, None),
            manager.collapse_named_section('spork').instantiate())

    def test_allow_unknowns(self):
        @configurable(allow_unknowns=True)
        def myrepo(**kwargs):
            return kwargs

        manager = central.ConfigManager(
            [{'spork': basics.HardCodedConfigSection({
                            'class': myrepo, 'spork': 'foon'})}])

        self.assertEqual(
            {'spork': 'foon'},
            manager.collapse_named_section('spork').instantiate())

    def test_reinstantiate_after_raise(self):
        # The most likely bug this tests for is attempting to
        # reprocess already processed section_ref args.
        spork = object()
        @configurable({'thing': 'ref:spork'})
        def myrepo(thing):
            self.assertIdentical(thing, spork)
            raise errors.ComplexInstantiationError('I suck')
        @configurable(typename='spork')
        def spork_producer():
            return spork
        manager = central.ConfigManager(
            [{'spork': basics.HardCodedConfigSection({
                            'class': myrepo,
                            'thing': basics.HardCodedConfigSection({
                                    'class': spork_producer,
                                    }),
                            })}])
        spork = manager.collapse_named_section('spork')
        for i in range(3):
            self.check_error(
                "Failed instantiating section 'spork':\n"
                "Failed instantiating section 'spork': exception caught from 'module.config.test_central.myrepo':\n"
                "'I suck', callable unset!",
                spork.instantiate)
        for i in range(3):
            self.check_error(
                "Failed instantiating section 'spork':\n"
                "Failed instantiating section 'spork': exception caught from 'module.config.test_central.myrepo':\n"
                "'I suck', callable unset!",
                manager.collapse_named_section('spork').instantiate)

    def test_instantiation_caching(self):
        @configurable(typename='drawer')
        def myrepo():
            return object()

        manager = central.ConfigManager(
            [{'spork': basics.HardCodedConfigSection({'class': myrepo}),
              'drawer': basics.ConfigSectionFromStringDict({
                            'class': 'module.config.test_central.drawer',
                            'content': 'spork',
                            }),
              }])

        config = manager.collapse_named_section('spork')
        self.assertIdentical(config.instantiate(), config.instantiate())
        self.assertIdentical(
            config.instantiate(),
            manager.collapse_named_section('drawer').instantiate()[0])

    def test_collapse_named_errors(self):
        manager = central.ConfigManager(
            [{'spork': basics.ConfigSectionFromStringDict({
                            'class': 'module.config.test_central.drawer',
                            'content': 'ref'})}], [RemoteSource()])
        self.assertRaises(KeyError, self.get_config_obj, manager, 'repo', 'foon')
        self.check_error(
            "Collapsing section named 'spork':\n"
            "Failed collapsing section key 'content':\n"
            "no section called 'ref'",
            self.get_config_obj, manager, 'repo', 'spork')

    def test_recursive_autoload(self):
        @configurable(typename='configsection')
        def autoloader():
            return {'autoload-sub': basics.HardCodedConfigSection(
                    {'class': autoloader}),
                    'spork': basics.HardCodedConfigSection({'class': repo,
                                                            'cache': 'test'})}

        self.check_error(
            "New config is trying to modify existing section(s) 'autoload-sub' "
            "that was already instantiated.",
            central.ConfigManager,
            [{'autoload-sub': basics.HardCodedConfigSection({
                            'class': autoloader,
                            })}])

    def test_recursive_section_ref(self):
        manager = central.ConfigManager(
            [{'spork': basics.ConfigSectionFromStringDict({
                            'class': 'module.config.test_central.drawer',
                            'content': 'foon'}),
              'foon': basics.ConfigSectionFromStringDict({
                            'class': 'module.config.test_central.drawer',
                            'content': 'spork'}),
              'self': basics.ConfigSectionFromStringDict({
                            'class': 'module.config.test_central.drawer',
                            'content': 'self'}),
              }])
        self.check_error(
            "Collapsing section named 'self':\n"
            "Failed collapsing section key 'content':\n"
            "Reference to 'self' is recursive",
            self.get_config_obj, manager, 'drawer', 'self')
        self.check_error(
            "Collapsing section named 'spork':\n"
            "Failed collapsing section key 'content':\n"
            "Collapsing section named 'foon':\n"
            "Failed collapsing section key 'content':\n"
            "Reference to 'spork' is recursive",
            self.get_config_obj, manager, 'drawer', 'spork')

    def test_recursive_inherit(self):
        manager = central.ConfigManager(
            [{'spork': basics.ConfigSectionFromStringDict({
                            'class': 'module.config.test_central.drawer',
                            'inherit': 'foon'}),
              'foon': basics.ConfigSectionFromStringDict({
                            'class': 'module.config.test_central.drawer',
                            'inherit': 'spork'}),
              }])
        self.check_error(
            "Collapsing section named 'spork':\n"
            "Inherit 'spork' is recursive",
            self.get_config_obj, manager, 'drawer', 'spork')

    def test_alias(self):
        def myspork():
            return object
        manager = central.ConfigManager(
            [{'spork': basics.HardCodedConfigSection({'class': myspork}),
              'foon': basics.section_alias('spork', 'myspork'),
              }])
        # This tests both the detected typename of foon and the caching.
        self.assertIdentical(manager.objects.myspork['spork'], manager.objects.myspork['foon'])

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
                    }])
        self.check_error(
            "Collapsing section named 'wrong':\n"
            "Failed collapsing section key 'myrepo':\n"
            "reference 'drawer' should be of type 'repo', got 'drawer'",
            self.get_config_obj, manager, 'repo', 'wrong')
        self.assertEqual('repo!', manager.objects.repo['right'])

        manager = central.ConfigManager([{
                    'myrepo': basics.HardCodedConfigSection({'class': myrepo}),
                    'drawer': basics.HardCodedConfigSection({'class': drawer}),
                    'right':  basics.AutoConfigSection({'class': reporefs,
                                                        'myrepo': 'myrepo'}),
                    'wrong':  basics.AutoConfigSection({'class': reporefs,
                                                        'myrepo': 'drawer'}),
                    }])
        self.check_error(
            "Collapsing section named 'wrong':\n"
            "Failed collapsing section key 'myrepo':\n"
            "reference 'drawer' should be of type 'repo', got 'drawer'",
            self.get_config_obj, manager, 'repo', 'wrong')
        self.assertEqual(['repo!'], manager.objects.repo['right'])

    def test_default(self):
        manager = central.ConfigManager([{
                    'thing': basics.HardCodedConfigSection({'class': drawer,
                                                            'default': True}),
                    'bug': basics.HardCodedConfigSection({'class': None,
                                                          'inherit-only':True,
                                                          'default': True}),
                    'ignore': basics.HardCodedConfigSection({'class': drawer}),
                    }])
        self.assertEqual((None, None), manager.get_default('drawer'))
        self.assertTrue(manager.collapse_named_section('thing').default)

        manager = central.ConfigManager([{
                    'thing': basics.HardCodedConfigSection({'class': drawer,
                                                            'default': True}),
                    'thing2': basics.HardCodedConfigSection({'class': drawer,
                                                             'default': True}),
                    }])
        self.check_error(
            "type drawer incorrectly has multiple default sections: 'thing', 'thing2'",
            manager.get_default, 'drawer')

        manager = central.ConfigManager([])
        self.assertIdentical(None, manager.get_default('drawer'))

    def test_broken_default(self):
        def broken():
            raise errors.ComplexInstantiationError('broken')
        manager = central.ConfigManager([{
                    'thing': basics.HardCodedConfigSection({
                            'class': drawer, 'default': True,
                            'content': basics.HardCodedConfigSection({
                                    'class': 'spork'})}),
                    'thing2': basics.HardCodedConfigSection({
                            'class': broken, 'default': True})}])
        self.check_error(
            "Collapsing defaults for 'drawer':\n"
            "Collapsing section named 'thing':\n"
            "Failed collapsing section key 'content':\n"
            "Failed converting argument 'class' to callable:\n"
            "'spork' is not callable",
            manager.get_default, 'drawer')
        self.check_error(
            "Collapsing defaults for 'broken':\n"
            "Collapsing section named 'thing':\n"
            "Failed collapsing section key 'content':\n"
            "Failed converting argument 'class' to callable:\n"
            "'spork' is not callable",
            manager.get_default, 'broken')

    def test_instantiate_broken_ref(self):
        @configurable(typename='drawer')
        def broken():
            raise errors.ComplexInstantiationError('broken')
        manager = central.ConfigManager([{
                    'one': basics.HardCodedConfigSection({
                            'class': drawer,
                            'content': basics.HardCodedConfigSection({
                                    'class': broken})}),
                    'multi': basics.HardCodedConfigSection({
                            'class': drawer,
                            'contents': [basics.HardCodedConfigSection({
                                        'class': broken})]}),
                    }])
        self.check_error(
            "Failed instantiating section 'one':\n"
            "Instantiating reference 'content' pointing at None:\n"
            "Failed instantiating section None:\n"
            "Failed instantiating section None: exception caught from 'module.config.test_central.broken':\n"
            "'broken', callable unset!",
            manager.collapse_named_section('one').instantiate)
        self.check_error(
            "Failed instantiating section 'multi':\n"
            "Instantiating reference 'contents' pointing at None:\n"
            "Failed instantiating section None:\n"
            "Failed instantiating section None: exception caught from 'module.config.test_central.broken':\n"
            "'broken', callable unset!",
            manager.collapse_named_section('multi').instantiate)

    def test_autoload_instantiationerror(self):
        @configurable(typename='configsection')
        def broken():
            raise errors.ComplexInstantiationError('broken')
        self.check_error(
            "Failed loading autoload section 'autoload_broken':\n"
            "Failed instantiating section 'autoload_broken':\n"
            "Failed instantiating section 'autoload_broken': exception caught from 'module.config.test_central.broken':\n"
            "'broken', callable unset!",
            central.ConfigManager, [{
                    'autoload_broken': basics.HardCodedConfigSection({
                            'class': broken})}])

    def test_autoload_uncollapsable(self):
        self.check_error(
            "Failed collapsing autoload section 'autoload_broken':\n"
            "Collapsing section named 'autoload_broken':\n"
            "Failed converting argument 'class' to callable:\n"
            "'spork' is not callable",
            central.ConfigManager, [{
                    'autoload_broken': basics.HardCodedConfigSection({
                            'class': 'spork'})}])

    def test_autoload_wrong_type(self):
        self.check_error(
            "Section 'autoload_wrong' is marked as autoload but type is "
            'drawer, not configsection',
            central.ConfigManager, [{
                    'autoload_wrong': basics.HardCodedConfigSection({
                            'class': drawer})}])

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
                    }])
        self.check_error(
            "reference 'drawer' should be of type 'repo', got 'drawer'",
            manager.objects.repo['wrong'][0].collapse)
        self.assertEqual('repo!', manager.objects.repo['right'][0].instantiate())

        manager = central.ConfigManager([{
                    'myrepo': basics.HardCodedConfigSection({'class': myrepo}),
                    'drawer': basics.HardCodedConfigSection({'class': drawer}),
                    'right':  basics.AutoConfigSection({'class': reporefs,
                                                        'myrepo': 'myrepo'}),
                    'wrong':  basics.AutoConfigSection({'class': reporefs,
                                                        'myrepo': 'drawer'}),
                    }])
        self.check_error(
            "reference 'drawer' should be of type 'repo', got 'drawer'",
            manager.objects.repo['wrong'][0][0].collapse)
        self.assertEqual(
            ['repo!'],
            [c.instantiate() for c in manager.objects.repo['right'][0]])

    def test_inherited_default(self):
        manager = central.ConfigManager([{
                    'default': basics.HardCodedConfigSection({
                            'default': True,
                            'inherit': ['basic'],
                            }),
                    'uncollapsable': basics.HardCodedConfigSection({
                            'default': True,
                            'inherit': ['spork'],
                            'inherit-only': True,
                            }),
                    'basic': basics.HardCodedConfigSection({'class': drawer}),
                    }], [RemoteSource()])
        self.assertTrue(manager.get_default('drawer'))

    def test_section_names(self):
        manager = central.ConfigManager([{
                    'thing': basics.HardCodedConfigSection({'class': drawer}),
                    }], [RemoteSource()])
        collapsed = manager.collapse_named_section('thing')
        self.assertEqual('thing', collapsed.name)

    def test_inherit_only(self):
        manager = central.ConfigManager([{
                    'source': basics.HardCodedConfigSection({
                            'class': drawer,
                            'inherit-only': True,
                            }),
                    'target': basics.HardCodedConfigSection({
                            'inherit': ['source'],
                            })}], [RemoteSource()])
        self.check_error(
            "Collapsing section named 'source':\n"
            'cannot collapse inherit-only section',
            manager.collapse_named_section, 'source')
        self.assertTrue(manager.collapse_named_section('target'))

    def test_self_inherit(self):
        section = basics.HardCodedConfigSection({'inherit': ['self']})
        manager = central.ConfigManager([{
                    'self': basics.ConfigSectionFromStringDict({
                            'class': 'module.config.test_central.drawer',
                            'inherit': 'self'}),
                    }], [RemoteSource()])
        self.check_error(
            "Collapsing section named 'self':\n"
            "Self-inherit 'self' cannot be found",
            self.get_config_obj, manager, 'drawer', 'self')
        self.check_error(
            "Self-inherit 'self' cannot be found",
            manager.collapse_section, [section])

        manager = central.ConfigManager([{
                    'self': basics.HardCodedConfigSection({
                            'inherit': ['self'],
                            })}, {
                    'self': basics.HardCodedConfigSection({
                            'inherit': ['self'],
                            })}, {
                    'self': basics.HardCodedConfigSection({
                            'class': drawer})}])
        self.assertTrue(manager.collapse_named_section('self'))
        self.assertTrue(manager.collapse_section([section]))

    def test_prepend_inherit(self):
        manager = central.ConfigManager([{
                    'sect': basics.HardCodedConfigSection({
                            'inherit.prepend': ['self']})}])
        self.check_error(
            "Collapsing section named 'sect':\n"
            'Prepending or appending to the inherit list makes no sense',
            manager.collapse_named_section, 'sect')

    def test_list_prepend(self):
        @configurable({'seq': 'list'})
        def seq(seq):
            return seq
        manager = central.ConfigManager([{
                    'inh': basics.HardCodedConfigSection({
                            'inherit': ['sect'],
                            'seq.prepend': ['pre'],
                            }),
                    'sect': basics.HardCodedConfigSection({
                            'inherit': ['base'],
                            'seq': ['1', '2'],
                            })}, {
                    'base': basics.HardCodedConfigSection({
                            'class': seq,
                            'seq.prepend': ['-1'],
                            'seq.append': ['post'],
                            })}])
        self.assertEqual(['-1', 'post'], manager.objects.seq['base'])
        self.assertEqual(['1', '2'], manager.objects.seq['sect'])
        self.assertEqual(['pre', '1', '2'], manager.objects.seq['inh'])

    def test_str_prepend(self):
        @configurable({'string': 'str'})
        def sect(string):
            return string
        manager = central.ConfigManager([{
                    'inh': basics.HardCodedConfigSection({
                            'inherit': ['sect'],
                            'string.prepend': 'pre',
                            }),
                    'sect': basics.HardCodedConfigSection({
                            'inherit': ['base'],
                            'string': 'b',
                            })}, {
                    'base':
                        basics.HardCodedConfigSection({
                            'class': sect,
                            'string.prepend': 'a',
                            'string.append': 'c',
                            })}])
        self.assertEqual('a c', manager.objects.sect['base'])
        self.assertEqual('b', manager.objects.sect['sect'])
        self.assertEqual('pre b', manager.objects.sect['inh'])
