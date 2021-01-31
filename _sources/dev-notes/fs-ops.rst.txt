=====================
Filesystem Operations
=====================

Here we define types of operations that pkgcore will support, as well as the
stages where these operations occur.

---------------------------
- File Deletion ( Removal )
---------------------------
  - prerm
  - unmerge files
  - postrm

--------------------------------
- File Addition ( Installation )
--------------------------------
  - preinst
  - merge files
  - postinst

----------------------------------
- File Replacement ( Overwriting )
----------------------------------
  - preinst
  - merge
  - postinst
  - prerm
  - unmerge
  - postrm
