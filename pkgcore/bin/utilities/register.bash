#Set pythonpath, bit hackish but should be fine
export PYTHONPATH=${PYTHONPATH}:$(dirname "$0")/../../../
regscript=$(dirname "$0")/register_plugin.py

"${regscript}" -s fs_ops copyfile 1 pkgcore.fs.ops.default_copyfile
"${regscript}" -s fs_ops ensure_perms 1 pkgcore.fs.ops.default_ensure_perms
"${regscript}" -s fs_ops mkdir 1 pkgcore.fs.ops.default_mkdir
"${regscript}" -s format ebuild_built 0.0 pkgcore.ebuild.ebuild_built.generate_new_factory
"${regscript}" -s format ebuild_src 0.0 pkgcore.ebuild.ebuild_src.generate_new_factory
"${regscript}" -s fs_ops merge_contents 1 pkgcore.fs.ops.merge_contents
"${regscript}" -s fs_ops unmerge_contents 1 pkgcore.fs.ops.unmerge_contents

