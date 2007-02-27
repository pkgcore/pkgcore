import re

from bzrlib.log import LogFormatter, register_formatter
from bzrlib.osutils import format_date

class MyLogFormatter(LogFormatter):

    def __init__(self, *args, **kwargs):
        LogFormatter.__init__(self, *args, **kwargs)
        self._last_date = None

    def show(self, revno, rev, delta):

        # skip commits that just pulled history in.
        if not (delta.renamed or delta.removed or delta.modified):
            return

        to_file = self.to_file
        rev_date = format_date(rev.timestamp, rev.timezone or 0,
                self.show_timezone, date_fmt="%Y-%m-%d",
                show_offset=False)
        if rev_date != self._last_date:
            if self._last_date is not None:
                print >>to_file, ''
            print >>to_file, '------------\n %s\n------------\n' % rev_date
            self._last_date = rev_date
        print >>to_file, "%s: %s" % (revno, self.short_committer(rev))
        if self.show_ids:
            print >>to_file,  'revision-id:', rev.revision_id

        # TODO: Why not show the modified files in a shorter form as
        # well? rewrap them single lines of appropriate length
        if delta is not None:
            delta.show(to_file, self.show_ids, short_status=True)
        if not rev.message:
            print >>to_file,  '(no message)'
        else:
            message = rev.message.rstrip('\r\n')
            for l in message.split('\n'):
                print >>to_file,  l
        print >>to_file, ''


register_formatter('pkgcore-changelog', MyLogFormatter)
