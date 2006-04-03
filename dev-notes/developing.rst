So... you've got a checkout, how do you hack on it, how do you get it setup so
you can actually work on this framework?

1) PYTHONPATH is your friend, first of all.  Set it to the directory you've 
checked pkgcore out into.  For example, I've got '/home/bharring/savior' as my
checkout- I want python to use the checkout's pkgcore code, so I need:

 export PYTHONPATH="/home/bharring/savior/"

Upon a python -c'import pkgcore', python will scan pkgcore, see the pkgcore 
directory in it (and that it has __init__.py), and use that.

Stable portage still is accessible/usable via normal emerge/repoman calls; if 
you unset PYTHONPATH, python -c'import portage' will pull from 
'/usr/lib/portage/pym/' (unless you have a portage.py in your current directory
or you're current dir is the pkgcore checkout).

PYTHONPATH makes the new code accessible to the python namespace; next you need
to tweak the new pkgcore code's default paths.

Second, you're likely developing this in your home dir.  Everything hinges on
PORTAGE_BASE_PATH.

If a portage_custom_path module exists, it is loaded.  It is the hook for 
defining your own constants.  The three important ones are:

- PORTAGE_BIN_PATH can be defined
- DEFAULT_CONF_FILE can be defined (this is the new config, the example config
  in this directory)
- CONF_DEFAULTS is the meta configuration definition, conf_default_types

These settings all default to PORTAGE_BASE_PATH; if you define it in 
portage_custom_path, the settings above will be based off of it.  If no 
portage_custom_path, then it defaults to "/home/bharring/new/" which probably
isn't what you want.

 An example portage_custom_path.py is available at
 ``http://gentooexperimental.org/~ferringb/portage_custom_path.py``

So, where to place this file?

- '/usr/lib/portage/pym' OR
- '/usr/lib/python2.*/site-packages/' OR
- Any other location that python will check on an 'import' statement

Wherever your conf is assigned to, you need to have a configuration defined.
Harring's configuration is available via

http://gentooexperimental/~ferringb/config

It's recommended you start with it as the base, and customize it.

Plugin Registration
-------------------
pkgcore is a pluggable, so even to get the basis working some plugins must be 
registered.

- pkgcore/bin/utilities/register_plugin.py -s fs_ops copyfile 1 \
  pkgcore.fs.ops.default_copyfile
- pkgcore/bin/utilities/register_plugin.py -s fs_ops ensure_perms 1 \
  pkgcore.fs.ops.default_ensure_perms
- pkgcore/bin/utilities/register_plugin.py -s fs_ops mkdir 1 \
  pkgcore.fs.ops.default_mkdir
- pkgcore/bin/utilities/register_plugin.py -s format ebuild_built 0.0 \
  pkgcore.ebuild.ebuild_built.generate_new_factory
- pkgcore/bin/utilities/register_plugin.py -s format ebuild_src 0.0 \
  pkgcore.ebuild.ebuild_src.generate_new_factory

You'll need to have PYTHONPATH set as root, note that sudo cleanses the env
normally.  If that fails, you're PYTHONPATH is invalid; otherwise it'll spit 
back a registering message.  So far, good to go.

Drop back to normal user, and try:

 >>> import pkgcore.config
 >>> conf=pkgcore.config.load_config()
 >>> tree=conf.repo["rsync repo"]
 >>> pkg=tree["dev-util/diffball-0.6.5"]
 >>> print pkg.depends
 >=dev-libs/openssl-0.9.6j >=sys-libs/zlib-1.1.4 >=app-arch/bzip2-1.0.2


If you've changed your tree name (my tree name is "rsync repo"), you'll have to
change what you try above.  If load_config() fails, then you have your paths 
wrong.  If you see an error message upon the initial import stating you're 
going to get '/home/bharring/new/' , you've defined portage_custom_path.py 
incorrectly, or it can't be read/found in a python directory; or, you've 
defined the variables wrong, look at pkgcore/const.py and grok what's going on.

If it fails in the pkg instantiation, either your tree is incomplete (no tree 
at defined path in config), or that version of openssl no longer exists.  
Anything else, track down ferringb in #pkgcore on freenode, or email 
'ferringb (at) gmail.com' with the traceback and I'll get ya going.

Finally, you need filter-env for the ebuild daemon.

 cd src/filter-env
 make filter-env
 cp filter-env ../../bin/ebuild-env/

Beyond that, you'll probably want to override path defaults; an example of this
is in the configuration on gentooexperimental noted above.  The required path 
override, and portage_custom_path override will be likely removed once this 
beast is autotooled, and will have those settings defined upon installation; in
the meantime, this is the route since the source isn't autotooled.
