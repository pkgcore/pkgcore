class TestRestriction:

    def _assertMatch(self, obj, args, mode='match', negated=False, msg=None):
        if msg is None:
            msg = ''
        else:
            msg = "; msg=" + msg
        if negated:
            assert not getattr(obj, mode)(*args), "%r must not match %r, mode=%s, negated=%r%s" % \
                    (obj, args, mode, negated, msg)
        else:
            assert getattr(obj, mode)(*args), \
                "%r must match %r, mode=%s, not negated%s" % \
                    (obj, args, mode, msg)

    def assertMatch(self, obj, target, mode='match', negated=False, msg=None):
        return self._assertMatch(obj, (target,), mode=mode, negated=negated, msg=msg)

    def assertNotMatch(self, obj, target, mode='match', negated=False,
        msg=None):
        return self.assertMatch(obj, target, mode=mode, negated=not negated,
            msg=msg)


    def assertMatches(self, obj, target, force_args=None, negated=False,
        msg=None):
        if force_args is None:
            force_args = (target,)
        self.assertMatch(obj, target, negated=negated, msg=msg)
        self.assertForceTrue(obj, force_args, negated=negated, msg=msg)
        self.assertNotForceFalse(obj, force_args, negated=negated, msg=msg)

    def assertNotMatches(self, obj, target, force_args=None, negated=False,
        msg=None):
        if force_args is None:
            force_args = (target,)
        self.assertNotMatch(obj, target, negated=negated, msg=msg)
        self.assertNotForceTrue(obj, force_args, negated=negated, msg=msg)
        self.assertForceFalse(obj, force_args, negated=negated, msg=msg)

    def assertForceTrue(self, obj, target, negated=False, msg=None):
        return self._assertMatch(obj, target, mode='force_True',
            negated=negated, msg=msg)

    def assertNotForceTrue(self, obj, target, negated=False, msg=None):
        return self._assertMatch(obj, target, mode='force_True',
            negated=not negated, msg=msg)

    def assertForceFalse(self, obj, target, negated=False, msg=None):
        return self._assertMatch(obj, target, mode='force_False',
            negated=negated, msg=msg)

    def assertNotForceFalse(self, obj, target, negated=False, msg=None):
        return self._assertMatch(obj, target, mode='force_False',
            negated=not negated, msg=msg)
