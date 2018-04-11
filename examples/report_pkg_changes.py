#!/usr/bin/env python3

import os
import sys

from snakeoil.bash import iter_read_bash
from snakeoil.osutils import listdir_files

from pkgcore.config import load_config
from pkgcore.ebuild.atom import atom
# we use a WorldFile since it *currently* forces unversioned atoms.
from pkgcore.pkgsets.filelist import WorldFile


def main(target_repo, seen, moves):
    # could build the atom from categories/packages, but prefer this;
    # simpler.
    new_seen = set(atom("%s/%s" % x) for x in target_repo.versions)

    new_pkgs = new_seen.difference(seen)
    # this is simpler if pkgsets are... actually sets. ;)
    # can't rely on it however since <0.2 lacks it.
    seen_set = set(seen)
    removed = seen_set.difference(new_seen)

    finished_moves = removed.intersection(moves)
    removed.difference_update(moves)
    in_transit = seen_set.intersection(moves)
    in_transit.difference_update(finished_moves)

    d = {}
    for x in in_transit:
        if moves[x] in new_seen:
            d[x] = moves[x]
    in_transit = d

    for l, prefix in ((new_pkgs, "added pkgs"), (removed, "removed pkgs")):
        if l:
            sys.stdout.write("%s:\n  %s\n\n" %
                (prefix, "\n  ".join(str(x) for x in sorted(l))))

    if finished_moves:
        sys.stdout.write("moved pkgs:\n  %s\n\n" %
            "\n  ".join("%s -> %s" % (k, moves[k])
                for k in sorted(finished_moves)))
    if in_transit:
        sys.stdout.write("pkg moves in transit:\n  %s\n\n" %
            "\n  ".join("%s -> %s" % (k, in_transit[k])
                for k in sorted(in_transit)))

    # just flush the seen fully, simplest.
    for x in seen_set:
        seen.remove(x)
    for x in new_seen:
        seen.add(x)
    return True


def apply_updates(moves, atom_set):
    d = {}
    for src, trg in moves.items():
        if src in atom_set:
            d[src] = trg
            atom_set.remove(src)
            atom_set.add(trg)
    return d


def parse_moves(location):
    pjoin = os.path.join

    # schwartzian comparison, convert it into YYYY-QQ
    def get_key(fname):
        return tuple(reversed(fname.split('-')))

    moves = {}
    for update_file in sorted(listdir_files(location), key=get_key):
        for line in iter_read_bash(pjoin(location, update_file)):
            line = line.split()
            if line[0] != 'move':
                continue
            moves[atom(line[1])] = atom(line[2])
    return moves


if __name__ == '__main__':
    args = sys.argv[1:]
    if len(args) not in (2,3) or "--help" in args or "-h" in args:
        sys.stderr.write("need two args; repository to scan, and "
            "file to store the state info in.\nOptional third arg is "
            "a profiles update directory to scan for moves.\n")
        sys.exit(-1)

    conf = load_config()
    try:
        repo = conf.repo[args[0]]
    except KeyError:
        sys.stderr.write("repository %r wasn't found- known repos\n%r\n" %
            (args[0], list(conf.repo.keys())))
        sys.exit(-2)

    if not os.path.exists(args[1]):
        open(args[1], "w")
    filelist = WorldFile(args[1])
    moves = {}
    if len(args) == 3:
        moves = parse_moves(args[2])
    if main(repo, filelist, moves):
        filelist.flush()
        sys.exit(0)
    sys.exit(1)
