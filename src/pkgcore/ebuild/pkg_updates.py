from collections import defaultdict, deque
from operator import itemgetter

from snakeoil.demandload import demand_compile_regexp
from snakeoil.osutils import listdir_files, pjoin
from snakeoil.sequences import iflatten_instance

from ..log import logger
from .atom import atom

demand_compile_regexp('valid_updates_re', r'^([1-4])Q-(\d{4})$')


def _scan_directory(path):
    files = []
    for filename in listdir_files(path):
        match = valid_updates_re.match(filename)
        if match is not None:
            files.append(((match.group(2), match.group(1)), filename))
        else:
            logger.error(f'incorrectly named update file: {filename!r}')
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
    # Afterwards, we flatten it to get a per cp chain of commands.
    # no need to do lookups basically, although we do need to
    # watch for cycles.
    mods = defaultdict(f)
    moved = {}

    try:
        for fp in _scan_directory(path):
            with open(pjoin(path, fp)) as f:
                data = (line.rstrip('\n') for line in f)
                _process_updates(data, fp, mods, moved)
    except FileNotFoundError:
        pass

    # force a walk of the tree, flattening it
    commands = {k: list(iflatten_instance(v[0], tuple)) for k,v in mods.items()}
    # filter out empty nodes.
    commands = {k: v for k,v in commands.items() if v}

    return commands


def _process_updates(sequence, filename, mods, moved):
    for lineno, raw_line in enumerate(sequence, 1):
        line = raw_line.strip()
        if not line:
            logger.error(f'file {filename!r}: empty line {lineno}')
            continue
        elif line != raw_line:
            logger.error(
                f'file {filename!r}: extra whitespace in {raw_line!r} on line {lineno}')

        line = line.split()
        if line[0] == 'move':
            if len(line) != 3:
                logger.error(
                    f'file {filename!r}: {raw_line!r} on line {lineno}: bad move form')
                continue
            src, trg = atom(line[1]), atom(line[2])
            if src.fullver is not None:
                logger.error(
                    f"file {filename!r}: {raw_line!r} on line {lineno}: "
                    f"atom {src} must be versionless")
                continue
            elif trg.fullver is not None:
                logger.error(
                    f"file {filename!r}: {raw_line!r} on line {lineno}: "
                    f"atom {trg} must be versionless")
                continue

            if src.key in moved:
                logger.warning(
                    f"file {filename!r}: {raw_line!r} on line {lineno}: "
                    f"{src} was already moved to {moved[src.key]}, "
                    "this line is redundant")
                continue

            d = deque()
            mods[src.key][1].extend([('move', src, trg), d])
            # start essentially a new checkpoint in the trg
            mods[trg.key][1].append(d)
            mods[trg.key][1] = d
            moved[src.key] = trg

        elif line[0] == 'slotmove':
            if len(line) != 4:
                logger.error(
                    f"file {filename!r}: {raw_line!r} on line {lineno}: "
                    "bad slotmove form")
                continue
            src = atom(line[1])

            if src.key in moved:
                logger.warning(
                    f"file {filename!r}: {raw_line!r} on line {lineno}: "
                    f"{src} was already moved to {moved[src.key]}, "
                    "this line is redundant")
                continue
            elif src.slot is not None:
                logger.error(
                    f"file {filename!r}: {raw_line!r} on line {lineno}: "
                    "slotted atom makes no sense for slotmoves")
                continue

            src_slot = atom(f'{src}:{line[2]}')
            trg_slot = atom(f'{src.key}:{line[3]}')

            mods[src.key][1].append(('slotmove', src_slot, line[3]))
        else:
            logger.error(
                f'file {filename!r}: {raw_line!r} on line {lineno}: unknown command')
