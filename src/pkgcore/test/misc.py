# misc things useful for tests.

from snakeoil.mappings import AttrAccessible

from .. import plugin
from ..ebuild.atom import atom
from ..ebuild.conditionals import DepSet
from ..ebuild.cpv import CPV
from ..ebuild.eapi import get_eapi
from ..ebuild.ebuild_src import package
from ..ebuild.misc import collapsed_restrict_to_data
from ..ebuild.repo_objs import RepoConfig
from ..package.metadata import factory
from ..repository.util import SimpleTree
from ..restrictions import packages

default_arches = set(["x86", "ppc", "amd64", "ia64"])

Options = AttrAccessible


class FakePkgBase(package):

    __slots__ = ()

    def __init__(self, cpvstr, data=None, shared=None, repo=None):
        if data is None:
            data = {}

        for x in ("DEPEND", "RDEPEND", "PDEPEND", "IUSE", "LICENSE"):
            data.setdefault(x, "")

        data.setdefault("KEYWORDS", ' '.join(default_arches))

        cpv = CPV(cpvstr, versioned=True)
        super().__init__(shared, repo, cpv.category, cpv.package, cpv.fullver)
        object.__setattr__(self, "data", data)


class FakeProfile:

    def __init__(self, masked_use={}, forced_use={},
                 provides={}, masks=[], virtuals={}, arch='x86', name='none'):
        self.provides_repo = SimpleTree(provides)
        self.masked_use = {atom(k): v for k, v in masked_use.items()}
        self.forced_use = {atom(k): v for k, v in forced_use.items()}
        self.masks = tuple(map(atom, masks))
        self.virtuals = SimpleTree(virtuals)
        self.arch = arch
        self.name = name

        self.forced_data = collapsed_restrict_to_data(
            [(packages.AlwaysTrue, (self.arch,))],
            self.forced_use.items())

        self.masked_data = collapsed_restrict_to_data(
            [(packages.AlwaysTrue, default_arches)],
            self.masked_use.items())

    def make_virtuals_repo(self, repo):
        return self.virtuals


class FakeRepo:

    def __init__(self, pkgs=(), repo_id='', location='', masks=(), **kwds):
        self.pkgs = pkgs
        self.repo_id = repo_id or location
        self.location = location
        self.masks = masks

        for k, v in kwds.items():
            setattr(self, k, v)

    def itermatch(self, restrict, sorter=iter, pkg_cls=lambda x: x, **kwargs):
        return filter(restrict.match, list(map(pkg_cls, sorter(self.pkgs))))

    def match(self, restrict, **kwargs):
        return list(self.itermatch(restrict, **kwargs))

    @property
    def masked(self):
        return packages.OrRestriction(*self.masks)

    def __iter__(self):
        return self.itermatch(packages.AlwaysTrue)

    def __contains__(self, obj):
        """Determine if a path or a package is in a repo."""
        if isinstance(obj, str):
            if self.location and path.startswith(self.location):
                return True
            return False
        else:
            for pkg in self.itermatch(obj):
                return True
            return False


class FakeEbuildRepo(FakeRepo):

    def __init__(self, *args, **kwds):
        self.config = kwds.pop('config', RepoConfig('nonexistent'))
        self.trees = (self,)
        super().__init__(*args, **kwds)


class FakePkg(FakePkgBase):
    def __init__(self, cpv, eapi="0", slot="0", subslot=None, iuse=None, use=(),
                 repo=FakeRepo(), restrict='', keywords=None, **kwargs):
        if isinstance(repo, str):
            repo = FakeRepo(repo)
        elif isinstance(repo, (tuple, list)) and len(repo) < 3:
            repo = FakeRepo(*repo)
        super().__init__(cpv, repo=factory(repo), **kwargs)
        if keywords is not None:
            object.__setattr__(self, "keywords", set(keywords))
        object.__setattr__(self, "slot", str(slot))
        if subslot is None:
            subslot = slot
        object.__setattr__(self, "subslot", subslot)
        object.__setattr__(self, "restrict", DepSet.parse(restrict, str))
        object.__setattr__(self, "fetchables", [])
        object.__setattr__(self, "use", set(use))
        object.__setattr__(self, 'eapi', get_eapi(eapi, False))
        if iuse is not None:
            object.__setattr__(self, "iuse", set(iuse))


class DisablePlugins:

    default_state = {}
    wipe_plugin_state = True

    def force_plugin_state(self, wipe=True, **packages):
        if wipe:
            plugin._cache.clear()
        plugin._cache.update(packages)

    def setUp(self):
        self._plugin_orig_initialize = plugin.initialize_cache
        self._plugin_orig_cache = plugin._cache.copy()
        if self.wipe_plugin_state:
            plugin._cache = {}
        plugin.initialize_cache = lambda p: ()

    def tearDown(self):
        plugin._cache = self._plugin_orig_cache
        plugin.initialize_cache = self._plugin_orig_initialize


# misc setup code for generating glsas for testing

glsa_template = \
"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE glsa SYSTEM "http://www.gentoo.org/dtd/glsa.dtd">
<?xml-stylesheet href="/xsl/glsa.xsl" type="text/xsl"?>
<?xml-stylesheet href="/xsl/guide.xsl" type="text/xsl"?>

<glsa id="%s">
  <title>generated glsa for %s</title>
  <synopsis>
    foon
  </synopsis>
  <product type="ebuild">foon</product>
  <announced>2003-11-23</announced>
  <revised>2003-11-23: 01</revised>
  <bug>33989</bug>
  <access>remote</access>
  <affected>%s</affected>
  <background>
    <p>FreeRADIUS is a popular open source RADIUS server.</p>
  </background>
  <description>
    <p>foon</p>
  </description>
  <impact type="normal">
    <p>
    impact-rific
    </p>
  </impact>
  <workaround>
    <p>redundant if no workaround</p>
  </workaround>
  <resolution>
    <p>blarh</p>
  </resolution>
  <references>
    <uri link="http://www.securitytracker.com/alerts/2003/Nov/1008263.html">SecurityTracker.com Security Alert</uri>
  </references>
</glsa>
"""

ops = {'>': 'gt', '<': 'lt'}
ops.update((k + '=', v[0] + 'e') for k, v in list(ops.items()))
ops.update(('~' + k, 'r' + v) for k, v in list(ops.items()))
ops['='] = 'eq'


def convert_range(text, tag, slot):
    i = 0
    while text[i] in "><=~":
        i += 1
    op = text[:i]
    text = text[i:]
    range = ops[op]
    slot = f' slot="{slot}"' if slot else ''
    return f'<{tag} range="{range}"{slot}>{text}</{tag}>'


def mk_glsa(*pkgs, **kwds):
    id = kwds.pop("id", None)
    if kwds:
        raise TypeError("id is the only allowed kwds; got %r" % kwds)
    id = str(id)
    horked = ''
    for data in pkgs:
        if len(data) == 4:
            pkg, slot, ranges, arch = data
        elif len(data) == 3:
            pkg, ranges, arch = data
            slot = ''
        else:
            pkg, ranges = data
            slot = ''
            arch = '*'
        horked += '<package name="%s" auto="yes" arch="%s">%s%s\n</package>' \
            % (pkg, arch,
                '\n'.join(convert_range(x, 'unaffected', slot) for x in ranges[0]),
                '\n'.join(convert_range(x, 'vulnerable', slot) for x in ranges[1]))
    return glsa_template % (id, id, horked)
