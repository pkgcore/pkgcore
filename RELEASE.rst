Release process
---------------

#. Add new entry in NEWS.rst along with changelog updates for the release.

#. Make sure dependency versions are correct in requirements/install.txt. Also,
   if requirements/pyproject.toml exists make sure dependency versions match
   those in requirements/install.txt for matching dependencies.

#. Run a test release build by force pushing to a temporary "deploy" branch.
   This triggers the release workflow to run on Github, but doesn't actually
   upload any of the generated files to PyPI or Github.

#. Verify the test build looks correct and passes tests then tag the new
   release and push the tag. If everything works as expected, both PyPI and
   Github should automatically get the release files pushed to them once the
   action completes.

#. At this point, it's good to remove the temporary deploy branch from the
   upstream repo.

#. Make a commit bumping the package version via __version__ in the base module
   and push the commit.
