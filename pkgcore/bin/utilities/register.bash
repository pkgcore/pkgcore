#Set pythonpath, bit hackish but should be fine
export PYTHONPATH="../../../"

./register_plugin.py -s fs_ops copyfile 1 pkgcore.fs.ops.default_copyfile
/register_plugin.py -s fs_ops ensure_perms 1 pkgcore.fs.ops.default_ensure_perms
./register_plugin.py -s fs_ops mkdir 1 pkgcore.fs.ops.default_mkdir
./register_plugin.py -s format ebuild_built 0.0 pkgcore.ebuild.ebuild_built.generate_new_factory
./register_plugin.py -s format ebuild_src 0.0 pkgcore.ebuild.ebuild_src.generate_new_factory
./register_plugin.py -s fs_ops merge_contents 1 pkgcore.fs.ops.merge_contents
./register_plugin.py -s fs_ops unmerge_contents 1 pkgcore.fs.ops.unmerge_contents

