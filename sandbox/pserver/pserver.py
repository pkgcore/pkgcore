# Copyright: 2006 Marien Zwart <marienz@gentoo.org>
# License: GPL2/BSD


"""pkgcore XMLRPC server."""


from twisted.python import log
from twisted.internet import defer, task

from twisted.web import xmlrpc

from pkgcore.util import parserestrict
from pkgcore.scripts import pquery


class Resource(xmlrpc.XMLRPC):

    def __init__(self, repos, metakeys):
        xmlrpc.XMLRPC.__init__(self)
        self.repos = repos
        self.metakeys = metakeys

    def xmlrpc_match(self, match):
        d = defer.Deferred()
        restrict = parserestrict.parse_match(match)
        task.coiterate(self._match(restrict, d)).addErrback(log.err)
        d.addErrback(log.err)
        return d

    def xmlrpc_revdep(self, match):
        d = defer.Deferred()
        restrict = pquery.parse_revdep(match)
        task.coiterate(self._match(restrict, d)).addErrback(log.err)
        d.addErrback(log.err)
        return d

    def _match(self, restrict, d):
        result = []
        for repo in self.repos:
            for pkg in repo.itermatch(restrict, yield_none=True):
                if pkg is None:
                    yield None
                    continue
                values = {}
                for attr in self.metakeys:
                    values[attr] = str(getattr(pkg, attr, 'MISSING'))
                result.append(values)
                yield None
        d.callback(result)
