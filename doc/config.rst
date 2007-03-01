=====================
 Configuring pkgcore
=====================

Note for portage users
======================

If you already know how to configure portage you can probably just
skip this file. As long as you do not have an /etc/pkgcore.conf or
~/.pkgcore.conf pkgcore will read portage's configuration files.

Basics, querying
================

There are multiple ways to configure pkgcore. No matter which method
you pick, the pconfig utility will allow you to check if pkgcore
interprets the configuration the way you intend. Part of a
configuration dump could look like::

 $ pconfig dump
 <lots of output snipped>

 '/usr/local/portage/private' {
     # typename of this section: repo
     class pkgcore.ebuild.repository.UnconfiguredTree;
     # type: refs:cache
     cache {
         # typename of this section: cache
         class pkgcore.cache.flat_hash.database;
 <some stuff snipped>
         # type: str
         label '/usr/local/portage/private';
         # type: str
         location '/var/cache/edb/dep';
     };
     # type: list
     default_mirrors 'http://ftp.easynet.nl/mirror/gentoo//distfiles';
     # type: ref:eclass_cache
     eclass_cache 'eclass stack';
     # type: str
     location '/usr/local/portage/private';
 }
 <lots of output snipped>

Starting at the top this means there is a "repo" known to pkgcore as
"/usr/local/portage/private", of the class
"pkgcore.ebuild.repository.UnconfiguredTree". The "repo" type means it
is something containing packages. The "class" means that this
particular repo contains unbuilt ebuilds. Below that are various
parameters specific to this class. The "type" comment tells you how
the argument is interpreted (this depends on the class).

The first is "cache". This is a nested section: it defines a new
object of the type "cache", class "pkgcore.cache.flat_hash.database".
Below that are the parameters given to this cache class. It is import
to understand that the ebuild repository does not care about the exact
class of the cache. All it needs is one or more things of type
"cache". There could have been some db-based cache here for example.

The next argument to the repo is "default_mirrors" which is handled as
a list of strings. "location" is a single string.

"eclass_cache" is a section reference pointing to the named section
"eclass stack" defined elsewhere in the dump (omitted here).

If your configuration defines a section that does not show up in
dump you can use uncollapsable to figure out why::

 $ pconfig uncollapsable
 Collapsing section named 'ebuild-repo-common':
 type pkgcore.ebuild.repository.UnconfiguredTree needs settings for 'location'

 Collapsing section named 'cache-common':
 type pkgcore.cache.flat_hash.database needs settings for 'label'

Unfortunately the configuration system cannot distinguish between
sections that are only meant as a base for other sections and actual
configuration mistakes. The messages you see here are harmless. If you
are debugging a missing section you should look for "Collapsing
section named 'the-broken-section'" in the output.

Portage compatibility mode
==========================

If you do not have a global (/etc/pkgcore.conf) or local
(~/.pkgcore.conf) configuration file pkgcore will automatically fall
back to reading make.conf and the other portage configuration files.
A noticable difference is pkgcore does not support picking up
variables like USE from the environment. Apart from that things should
just work the way you're used to.

Beyond portage compatibility mode
=================================

Basics
------

If you want to define extra repositories pkgcore should know about but
portage should not you will need a minimal configuration file. pkgcore
reads two configuration files: ~/.pkgcore.conf and /etc/pkgcore.conf.
Settings in the former override the ones in the latter.

If one of them exists this completely disables portage configuration
file parsing. The first thing you will probably want to do is
re-enable that, by putting in one of the configuration files::

 [autoload-portage]
 class=pkgcore.ebuild.portage_conf.config_from_make_conf

If you then run pconfig dump you should see among other things::

 'autoload-portage' {
    # typename of this section: configsection
    class pkgcore.ebuild.portage_conf.config_from_make_conf;
 }

Section names are usually arbitrary but sections that load extra
configuration data are an exception: they have to start with
"autoload" or they will not be processed. If you change the section
name to just "portage" you will still see it show up in pconfig dump
but all other things defined in make.conf will disappear.

pconfig can tell you what arguments a class takes::

 $ pconfig describe-class pkgcore.config.basics.parse_config_file
 typename is configsection

 parser: callable (required)
 path: str (required)

If you wanted to remove the overlay mentioned at the top of this
document from make.conf but keep it available to pkgcore you would
add::

 [/usr/local/portage/private]
 class=pkgcore.ebuild.repository.UnconfiguredTree
 cache=private-cache
 default_mirrors='http://ftp.easynet.nl/mirror/gentoo//distfiles'
 eclass_cache='eclass stack'
 location='/usr/local/portage/private'

 [private-cache]
 class=pkgcore.cache.flat_hash.database
 ; All the stuff snipped earlier
 label='/usr/local/portage/private'
 location='/var/cache/edb/dep'

Because the ini file format does not allow nesting sections we had to
put the cache in a named section and refer to that. The dump output
will reflect this but everything else will work just like it did
before.

Inherits
--------

If you have a lot of those overlays you can avoid repeating the common
bits::

 [stuff-common-to-repos]
 class=pkgcore.ebuild.repository.UnconfiguredTree
 default_mirrors='http://ftp.easynet.nl/mirror/gentoo//distfiles'
 eclass_cache='eclass stack'
 inherit-only=true

 [/usr/local/portage/private]
 inherit=stuff-common-to-repos
 location='/usr/local/portage/private'
 cache=private-cache

 [/usr/local/portage/other-overlay]
 inherit=stuff-common-to-repos
 location='/usr/local/portage/other-overlay'
 cache=other-overlay-cache

 ; And do the same thing for the caches.

There is nothing special about sections used as target for "inherit".
They can be complete sections, although they do not have to be. If
they are not complete sections you should set inherit-only to true for
them, to make pconfig uncollapsable ignore errors in them.

Actually the portage emulation mode uses inherit targets too, so you
could just have inherited "ebuild-repo-common". Inherit targets do not
have to live in the same file as they are inherited from.

One last special features: things marked as "incremental" get their
inherited value appended instead of overriding it.

Different config format
-----------------------

If you have pyparsing installed pkgcore supports a second
configuration file format that is very similar to the dump output
(not entirely identical: the string escaping rules are different). It
does not try to detect what format your config file is in:
pkgcore.conf is always in "ini" format. But you can load a second
configuration file from there::

 [autoload-dhcpformat]
 class=pkgcore.config.parse_config_file
 parser=pkgcore.config.dhcpformat.config_from_file
 path=/home/<you>/.pkgcore.dhcpconf

If you use "pkgcore.config.cparser.config_from_file" as "parser" you
can use this to load a second ini-style file. The loaded file can also
contain autoloads of its own, loading more config files or
portage_conf. For example, if .pkgcore.dhcpconf looks like::

 "autoload-portage" {
     class pkgcore.ebuild.portage_conf.config_from_make_conf;
 }

it will load make.conf.

If you want to get rid of make.conf entirely you can start from the
output of pconfig dump. But be careful: pconfig does not escape
strings exactly the same way dhcpformat parses them, so make sure you
check the dump after you disable portage_conf for mistakes.

Aliases
-------

You may have seen something called "section_alias" in a portage
compatibility configuration. These are used to make an existing named
section show up under a second name. You probably do not need them if
you write your own configuration.
