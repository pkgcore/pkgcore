# Copyright: 2011 Brian Harring <ferringb@gmail.com>
# License: GPL2/BSD 3 clause

from operator import itemgetter
from collections import deque, defaultdict
from snakeoil.osutils import listdir_files, pjoin
from snakeoil.fileutils import readlines
from snakeoil.iterables import chain_from_iterable
from pkgcore.ebuild.atom import atom
from snakeoil.lists import iflatten_instance
from snakeoil import demandload
demandload.demandload(globals(),
    'pkgcore.log:logger',
)

demandload.demand_compile_regexp(globals(), "valid_updates_re", "^(\d)Q-(\d{4})$")


def _scan_directory(path):
    files = []
    for x in listdir_files(path):
        match = valid_updates_re.match(x)
        if match is not None:
            files.append(((match.group(2), match.group(1)), x))
    files.sort(key=itemgetter(0))
    return [x[1] for x in files]

def read_updates(path):
    def f():
        d = deque()
        return [d,d]
    # mods tracks the start point [0], and the tail, [1].
    # via this, pkg moves into a specific pkg can pick up
    # changes past that point, while ignoring changes prior
    # to that point.
    # Aftwards, we flatten it to get a per cp chain of commands.
    # no need to do lookups basically, although we do need to
    # watch for cycles.
    mods = defaultdict(f)
    moved = {}

    for fp in _scan_directory(path):
        fp = pjoin(path, fp)

        _process_update(readlines(fp), fp, mods, moved)

    # force a walk of the tree, flattening it
    commands = dict((k, list(iflatten_instance(v[0], tuple))) for k,v in mods.iteritems())
    # filter out empty nodes.
    commands = dict((k,v) for k,v in commands.iteritems() if v)

    return commands


def _process_update(sequence, filename, mods, moved):
    for raw_line in sequence:
        line = raw_line.split()
        if line[0] == 'move':
            if len(line) != 3:
                raise ValueError("move line %r isn't of proper form" % (raw_line,))
            src, trg = atom(line[1]), atom(line[2])
            if src.fullver is not None:
                raise ValueError("file %r, line %r; atom %s must be versionless"
                    % (filename, raw_line, src))
            elif trg.fullver is not None:
                raise ValueError("file %r, line %r; atom %s must be versionless"
                    % (filename, raw_line, trg))

            if src.key in moved:
                logger.warning("file %r, line %r: %s was already moved to %s,"
                    " this line is redundant." % (filename, raw_line, src, moved[src.key]))
                continue

            d = deque()
            mods[src.key][1].extend([('move', src, trg), d])
            # start essentially a new checkpoint in the trg
            mods[trg.key][1].append(d)
            mods[trg.key][1] = d
            moved[src.key] = trg

        elif line[0] == 'slotmove':
            if len(line) != 4:
                raise ValueError("slotmove line %r isn't of proper form" % (raw_line,))
            src = atom(line[1])

            if src.key in moved:
                logger.warning("file %r, line %r: %s was already moved to %s,"
                    " this line is redundant.", filename, raw_line, src, moved[src.key])
                continue
            elif src.slot is not None:
                logger.warning("file %r, line %r: slotted atom makes no sense for slotmoves, ignoring",
                    filename, raw_line)

            src_slot = atom("%s:%s" % (src, line[2]))
            trg_slot = atom("%s:%s" % (src.key, line[3]))

            mods[src.key][1].append(('slotmove', src_slot, line[3]))
