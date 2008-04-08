# Copyright: 2005 Brian Harring <ferringb@gmail.com>
# License: GPL2

"""
template for sql backends- needs work
"""

from pkgcore.cache import template, errors

class SQLDatabase(template.database):
    """template class for RDBM based caches

    This class is designed such that derivatives don't have to change
    much code, mostly constant strings.

    _BaseError must be an exception class that all Exceptions thrown
    from the derived RDBMS are derived from.

    SCHEMA_INSERT_CPV_INTO_PACKAGE should be modified dependant on the
    RDBMS, as should SCHEMA_PACKAGE_CREATE- basically you need to deal
    with creation of a unique pkgid. If the dbapi2 rdbms class has a
    method of recovering that id, then modify _insert_cpv to remove
    the extra select.

    Creation of a derived class involves supplying _initdb_con, and
    table_exists. Additionally, the default schemas may have to be
    modified.
    """

    SCHEMA_PACKAGE_NAME = "package_cache"
    SCHEMA_PACKAGE_CREATE = (
        "CREATE TABLE %s ( "
        "pkgid INTEGER PRIMARY KEY, label VARCHAR(255), cpv VARCHAR(255), "
        "UNIQUE(label, cpv))" % SCHEMA_PACKAGE_NAME)
    SCHEMA_PACKAGE_DROP = "DROP TABLE %s" % SCHEMA_PACKAGE_NAME

    SCHEMA_VALUES_NAME = "values_cache"
    SCHEMA_VALUES_CREATE = (
        "CREATE TABLE %s ( "
        "pkgid integer references %s (pkgid) on delete cascade, "
        "key varchar(255), value text, UNIQUE(pkgid, key))" % (
            SCHEMA_VALUES_NAME, SCHEMA_PACKAGE_NAME))
    SCHEMA_VALUES_DROP = "DROP TABLE %s" % SCHEMA_VALUES_NAME
    SCHEMA_INSERT_CPV_INTO_PACKAGE = (
        "INSERT INTO %s (label, cpv) VALUES(%%s, %%s)" % SCHEMA_PACKAGE_NAME)

    _BaseError = ()
    _dbClass = None

    autocommits = False
#    cleanse_keys = True

    # boolean indicating if the derived RDBMS class supports replace syntax
    _supports_replace = False

    def __init__(self, location, label, auxdbkeys, *args, **config):
        """initialize the instance.
        derived classes shouldn't need to override this"""

        self.db = None
        super(SQLDatabase, self).__init__(location, label, auxdbkeys,
                                          *args, **config)

        config.setdefault("host","127.0.0.1")
        config.setdefault("autocommit", self.autocommits)
        self._initdb_con(config)

        self.label = self._sfilter(self.label)

    def _dbconnect(self, config):
        """Initialize the internal db connection and cursor.

        Should be overridden if the derived class needs special
        parameters for initializing the db connection or cursor.
        """
        self.db = self._dbClass(**config)
        self.con = self.db.cursor()

    def _initdb_con(self, config):
        """ensure needed tables are in place.

        If the derived class needs a different set of table creation
        commands, overload the approriate SCHEMA_ attributes. If it
        needs additional execution beyond that, override this.
        """

        self._dbconnect(config)
        if not self._table_exists(self.SCHEMA_PACKAGE_NAME):
            if self.readonly:
                raise errors.ReadOnly(
                    "table %s doesn't exist" % self.SCHEMA_PACKAGE_NAME)
            try:
                self.con.execute(self.SCHEMA_PACKAGE_CREATE)
            except self._BaseError, e:
                raise errors.InitializationError(self.__class__, e)

        if not self._table_exists(self.SCHEMA_VALUES_NAME):
            if self.readonly:
                raise errors.ReadOnly(
                    "table %s doesn't exist" % self.SCHEMA_VALUES_NAME)
            try:
                self.con.execute(self.SCHEMA_VALUES_CREATE)
            except self._BaseError, e:
                raise errors.InitializationError(self.__class__, e)

    def _table_exists(self, tbl):
        """return true if a table exists
        derived classes must override this"""
        raise NotImplementedError

    def _sfilter(self, string):
        """meta escaping, returns quoted string for use in sql statements"""
        return "\"%s\"" % string.replace("\\","\\\\").replace("\"","\\\"")

    def _getitem(self, cpv):
        try:
            self.con.execute(
                "SELECT key, value FROM %s NATURAL JOIN %s "
                "WHERE label=%s AND cpv=%s" % (
                    self.SCHEMA_PACKAGE_NAME, self.SCHEMA_VALUES_NAME,
                    self.label, self._sfilter(cpv)))
        except self._BaseError, e:
            raise errors.CacheCorruption(self, cpv, e)

        rows = self.con.fetchall()

        if not rows:
            raise KeyError(cpv)

        vals = dict((k,"") for k in self._known_keys)
        vals.update(dict(rows))
        return vals

    def _delitem(self, cpv):
        """delete a cpv cache entry
        derived RDBM classes for this *must* either support cascaded deletes, or
        override this method
        """

        try:
            try:
                self.con.execute("DELETE FROM %s WHERE label=%s AND cpv=%s" % \
                (self.SCHEMA_PACKAGE_NAME, self.label, self._sfilter(cpv)))
                if self.autocommits:
                    self.commit()
            except self._BaseError, e:
                raise errors.CacheCorruption(self, cpv, e)
            if self.con.rowcount <= 0:
                raise KeyError(cpv)
        except Exception:
            if not self.autocommits:
                self.db.rollback()
                # yes, this can roll back a lot more then just the delete. deal.
            raise

    def __del__(self):
        if self.db is not None:
            self.commit()
            self.db.close()

    def _setitem(self, cpv, values):
        try:
            # insert.
            try:
                pkgid = self._insert_cpv(cpv)
            except self._BaseError, e:
                raise errors.CacheCorruption(cpv, e)

            # __getitem__ fills out missing values,
            # so we store only what's handed to us and is a known key
            db_values = []
            for key in self._known_keys:
                if values.get(key, "") != "":
                    db_values.append({"key":key, "value":values[key]})

            if db_values:
                try:
                    self.con.executemany(
                        "INSERT INTO %s (pkgid, key, value) "
                        "VALUES(\"%s\", %%(key)s, %%(value)s)" %
                        (self.SCHEMA_VALUES_NAME, str(pkgid)), db_values)
                except self._BaseError, e:
                    raise errors.CacheCorruption(cpv, e)
            if self.autocommits:
                self.commit()

        except Exception:
            if not self.autocommits:
                try:
                    self.db.rollback()
                except self._BaseError:
                    pass
            raise


    def _insert_cpv(self, cpv):
        """Insert a cpv in the db.

        Uses SCHEMA_INSERT_CPV_INTO_PACKAGE, which must be overloaded
        if the table definition doesn't support auto-increment columns
        for pkgid.

        @return: the cpvs new pkgid

        note this doesn't commit the transaction.  The caller is expected to.
        """

        cpv = self._sfilter(cpv)
        if self._supports_replace:
            query_str = self.SCHEMA_INSERT_CPV_INTO_PACKAGE.replace(
                "INSERT", "REPLACE", 1)
        else:
            # just delete it.
            try:
                del self[cpv]
            except  (errors.CacheCorruption, KeyError):
                pass
            query_str = self.SCHEMA_INSERT_CPV_INTO_PACKAGE

        try:
            self.con.execute(query_str % (self.label, cpv))
        except self._BaseError:
            self.db.rollback()
            raise

        self.con.execute("SELECT pkgid FROM %s WHERE label=%s AND cpv=%s" % \
            (self.SCHEMA_PACKAGE_NAME, self.label, cpv))

        if self.con.rowcount != 1:
            raise errors.CacheCorruption(
                cpv, "Tried to insert the cpv, but found "
                " %i matches upon the following select!" % (
                    self.con.rowcount))
        return self.con.fetchone()[0]

    def __contains__(self, cpv):
        if not self.autocommits:
            try:
                self.commit()
            except self._BaseError, e:
                raise errors.GeneralCacheCorruption(e)

        try:
            self.con.execute("SELECT cpv FROM %s WHERE label=%s AND cpv=%s" % \
                (self.SCHEMA_PACKAGE_NAME, self.label, self._sfilter(cpv)))
        except self._BaseError, e:
            raise errors.GeneralCacheCorruption(e)
        return self.con.rowcount > 0

    def iterkeys(self):
        if not self.autocommits:
            try:
                self.commit()
            except self._BaseError, e:
                raise errors.GeneralCacheCorruption(e)

        try:
            self.con.execute("SELECT cpv FROM %s WHERE label=%s" %
                (self.SCHEMA_PACKAGE_NAME, self.label))
        except self._BaseError, e:
            raise errors.GeneralCacheCorruption(e)

        for x in self.con.fetchall():
            yield x[0]

    def iteritems(self):
        try:
            self.con.execute(
                "SELECT cpv, key, value FROM %s NATURAL JOIN %s WHERE label=%s"
                % (self.SCHEMA_PACKAGE_NAME, self.SCHEMA_VALUES_NAME,
                   self.label))
        except self._BaseError, e:
            # XXX this makes no sense
            raise errors.CacheCorruption(self, 'iteritems', e)

        oldcpv = None
        l = []
        for cpv, key, v in self.con.fetchall():
            if oldcpv != cpv:
                if oldcpv is not None:
                    d = dict(l)
                    if "_eclasses_" in d:
                        d["_eclasses_"] = self.reconstruct_eclasses(
                            oldcpv, d["_eclasses_"])
                    yield oldcpv, d
                l = []
                oldcpv = cpv
            l.append((key, v))

        if oldcpv is not None:
            d = dict(l)
            if "_eclasses_" in d:
                d["_eclasses_"] = self.reconstruct_eclasses(
                    oldcpv, d["_eclasses_"])
            yield oldcpv, d

    def commit(self):
        self.db.commit()

    def get_matches(self, match_dict):
        query_list = []
        for k, v in match_dict.items():
            if k not in self._known_keys:
                raise errors.InvalidRestriction(
                    k, v, "key isn't known to this cache instance")
            v = v.replace("%","\\%")
            v = v.replace(".*","%")
            query_list.append(
                "(key=%s AND value LIKE %s)" % (
                    self._sfilter(k), self._sfilter(v)))

        if query_list:
            query = " AND "+" AND ".join(query_list)
        else:
            query = ''

        print (
            "query = SELECT cpv from package_cache natural join values_cache "
            "WHERE label=%s %s" % (self.label, query))
        try:
            self.con.execute(
                "SELECT cpv from package_cache natural join values_cache "
                "WHERE label=%s %s" % (self.label, query))
        except self._BaseError, e:
            raise errors.GeneralCacheCorruption(e)

        return [ row[0] for row in self.con.fetchall() ]
