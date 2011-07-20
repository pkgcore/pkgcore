========
Testing
========

We use twisted.trial for our tests, to run the test framework run:

 trial pkgcore

Your own tests must be stored in pkgcore.test - furthermore, tests must
pass when ran repeatedly (-u option). You will want at least twisted-2.2
for that, <2.2 has a few false positives.

Testing for negative assertions
===============================

When coding it's easy to write test cases asserting that you get result xyz
from foo, usually asserting the correct flow. This is ok if nothing goes
wrong, but that doesn't normally happen. :)

Negative assertions (there probably is a better term for it) means asserting
failure conditions and ensuring that the code handles zyx properly when it
gets thrown at it. Most test cases seem to miss this, resulting in bugs
being able to hide away for when things go wrong.

Using --coverage
================

When writing tests for your code (or for existing code without any tests), it
is very useful to use --coverage. Run `trial --coverage <path/to/test>`, and
then check <cwd>/_trial_temp/coverage/<test/module/name>. Any lines prefixed
with '>>>>>' have not been covered by your tests. This should be rectified
before your code is merged to mainline (though this is not always possible).
Those lines prefixed with a number show the number of times that line of code
is evaluated.
