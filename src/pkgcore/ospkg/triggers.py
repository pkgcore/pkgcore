from snakeoil.osutils import pjoin, ensure_dirs

from pkgcore.merge import triggers
from pkgcore.ospkg import deb


class SaveDeb(triggers.base):

    required_csets = ('raw_new_cset',)
    priority = 95
    _hooks = ('sanity_check',)
    _engine_types = triggers.INSTALLING_MODES

    def __init__(self, basepath, maintainer='', postfix='', platform=''):
        self.basepath = basepath
        self.maintainer = maintainer
        self.postfix = postfix
        self.platform = platform

    def trigger(self, engine, cset):
        pkg = engine.new
        filename = "%s_%s%s.deb" % (pkg.package, pkg.version, self.postfix)
        tmp_path = pjoin(engine.tempdir, filename)
        final_path = pjoin(self.basepath, filename)
        ensure_dirs(tmp_path)
        deb.write(tmp_path, final_path, pkg,
            cset=cset,
            platform=self.platform, maintainer=self.maintainer)
