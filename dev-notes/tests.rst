
========
Testing
========
We use twisted.trial for our tests; To run the test framework:

 trial pkgcore

Writing your own tests, must be stored in pkgcore.test - further, test must 
pass when ran repeatedly (-u option).  You will want twisted 2.2 for that, <2.2
has a few false positives.

