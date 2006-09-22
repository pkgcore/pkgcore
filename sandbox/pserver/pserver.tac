# Copyright: 2006 Marien Zwart <marienz@gentoo.org>
# License: GPL2


"""pkgcore XMLRPC server."""


from twisted.application import service, internet

from twisted.web import server, resource

from pkgcore.config import load_config

import pserver


application = service.Application('pkgcore server')

config = load_config()
repos = [config.repo['portdir']]

res = resource.Resource()
res.putChild('RPC2', pserver.Resource(repos, ['cpvstr', 'depends']))
site = server.Site(res)

server = internet.TCPServer(12345, site)
server.setServiceParent(application)
