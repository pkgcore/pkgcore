#!/usr/bin/python

from pkgcore.config import load_config
from pkgcore.package.atom import atom
from pkgcore.util.lists import flatten, stable_unique
from pkgcore.util.repo_utils import get_raw_repos
from pkgcore.util.commandline import generate_restriction, collect_ops
from pkgcore.ebuild import resolver
import sys


def pop_paired_args(args, arg, msg):
	rets = []
	if not isinstance(arg, (tuple, list)):
		arg = [arg]
	for a in arg:
		try:
			while True:
				i = args.index(a)
				args.pop(i)
				if len(args) == i:
					raise Exception("%s needs to be followed by an arg: %s" % (a, msg))
				rets.append(args.pop(i))
		except ValueError:
			pass
	return rets

def pop_arg(args, *arg):

	ret = False
	for a in arg:
		try:
			while True:
				args.remove(a)
				ret = True
		except ValueError:
			pass
	return ret
	

class Failure(Exception):
	pass


class AmbiguousQuery(Failure):

	def __init__(self, raw_atom, matches, rewritten_atom):
		self.raw_atom, self.matches, self.rewritten_atom = raw_atom, matches, rewritten_atom

	def __str__(self):
		if self.raw_atom == self.rewritten_atom:
			return "multiple pkg matches found for %s: %s" % (self.raw_atom, ", ".join(sorted(self.matches)))
		return "multiple pkg matches found for %s: %s, %s" % (self.raw_atom, ", ".join(sorted(self.matches)), self.rewritten_atom)


class NoMatches(Failure):

	def __init__(self, raw_atom, rewritten):
		self.raw_atom, self.rewritten = raw_atom, rewritten
	
	def __str__(self):
		if self.raw_atom == self.rewritten_atom:
			return "no matches found to %s (rewritten into %s)" % (self.raw_atom, self.rewitten_atom)
		return "no matches found to %s" % self.raw_atom


def parse_atom(repos, ignore_failures, *tokens):
	""""
	parse a list of strings returning a list of atoms, filling in categories as needed

	@param repo: L{pkgcore.prototype.tree} instance
	@param tokens: list of strings to parse
	"""
	atoms = []
	for x in tokens:
		a = generate_restriction(x)
		if isinstance(a, atom):
			atoms.append(a)
			continue
		matches = set(pkg.key for pkg in repos.itermatch(a))
		if not matches:
			e = NoMatches(x, a)
			if not ignore_failures:
				raise e
			print e
			print "skipping"
			continue
		elif len(matches) > 1:
			raise AmbiguousQuery(x, matches, a)
		# else we rebuild an atom to include category
		key = list(matches)[0]
		ops, text = collect_ops(x)
		if not ops:
			atoms.append(atom(key))
		else:
			atoms.append(atom(key))
	return atoms	


def main():
	import time
	args = sys.argv[1:]

	if pop_arg(args, "-h", "--help"):
		print "args supported, [-D || --deep], [[-u || --upgrade]] and -s (system|world) [-d || --debug] [ --ignore-failures ] [ --preload-vdb-state ]"
		print "[[-p || --pretend] || [-f || --fetchonly]] [ -i || --ignore-cycles ]"
		print "can specify additional atoms when specifying -s, no atoms/sets available, defaults to sys-apps/portage"
		return 1

	if pop_arg(args, "-d", "--debug"):
		resolver.plan.limiters.add(None)
	
	ignore_cycles = pop_arg(args, "-i", "--ignore-cycles")
	pretend = pop_arg(args, "-p", "--pretend")
	fetchonly = pop_arg(args, "-f", "--fetchonly")
	
	trigger_pdb = pop_arg(args, "-p", "--pdb")
	empty_vdb = pop_arg(args, "-e", "--empty")
	upgrade = pop_arg(args, "-u", "--upgrade")
	preload_vdb_state = pop_arg(args, None, "--preload-vdb-state")
	ignore_failures = pop_arg(args, None, "--ignore-failures")
	if max and max == upgrade:
		print "can only choose max, or upgrade"
		return 1
	if upgrade:
		resolver_kls = resolver.upgrade_resolver
	else:
		resolver_kls = resolver.min_install_resolver

	deep = bool(pop_arg(args, "-D", "--deep"))

	conf = load_config()

	set_targets = pop_paired_args(args, ["--set", "-s"], "pkg sets to enable")
	if set_targets:
		print "using pkgset(s): %s" % (", ".join("'%s'" % x.strip() for x in set_targets))
	set_targets = [a for t in set_targets for a in conf.pkgset[t]]
	#map(atom, conf.pkgset[l]) for l in set_targets], restriction.base)
	
	domain = conf.domain["livefs domain"]
	vdb, repos = domain.all_vdbs, domain.all_repos
	if not args:
		if set_targets:
			atoms = []
		else:
			print "resolving sys-apps/portage since no atom supplied"
			atoms = [atom("sys-apps/portage")]
	else:
		atoms = parse_atom(repos, ignore_failures, *args)

	if set_targets:
		atoms += set_targets

	atoms = stable_unique(atoms)

	if empty_vdb:
		resolver_inst = resolver_kls(vdb, repos, verify_vdb=deep, resolver_cls=resolver.empty_tree_merge_plan, drop_cycles=ignore_cycles)
	else:
		resolver_inst = resolver_kls(vdb, repos, verify_vdb=deep, drop_cycles=ignore_cycles)

	if preload_vdb_state:
		vdb_time = time.time()
		resolver_inst.load_vdb_state()
		vdb_time = time.time() - vdb_time
	else:
		vdb_time = 0.0
	ret = True
	failures = []
	resolve_time = time.time()
	for restrict in atoms:
#		print "\ncalling resolve for %s..." % restrict
		ret = resolver_inst.add_atom(restrict)
		if ret:
			print "ret was",ret
			print "resolution failed"
			failures.append(restrict)
			if not ignore_failures:
				break
	resolve_time = time.time() - resolve_time
	if failures:
		print "\nfailures encountered-"
		for restrict in failures:
			print "failed '%s'\npotentials-" % restrict
			match_count = 0
			for r in get_raw_repos(repos):
				l = r.match(restrict)
				if l:
					print "repo %s: [ %s ]" % (r, ", ".join(str(x) for x in l))
					match_count += len(l)
			if not match_count:
				print "no matches found in %s" % repo
			print
			if not ignore_failures:
				return 2

	print "\nbuildplan"
	plan = list(resolver_inst.state.iter_pkg_ops())
	changes = []
	for op, pkgs in plan:
		if pkgs[-1].repo.livefs and op != "replace":
			continue
		elif not pkgs[-1].package_is_real:
			continue
		changes.append((op, pkgs))
		print "%s %s" % (op.ljust(8), ", ".join(str(y) for y in reversed(pkgs)))
		
	print "result was successfull, 'parently- spent %.2f seconds resolving" % (resolve_time)
	if vdb_time:
		print "spent %.2f seconds preloading vdb state" % vdb_time
	if pretend:
		return 0
	elif not fetchonly:
		vdb = vdb.trees[0]
		vdb.frozen = False
	for op, pkgs in changes:
		print "processing %s" % pkgs[0]
		buildop = pkgs[0].build()
		if fetchonly:
			print "\n%i files required-" % len(pkgs[0].fetchables)
			try:
				ret = build_op.fetch()
			except Exception, e:
				ret = e
		else:
			print "building..."
			f = buildop.finalize()
			if f is not False:
				print "\nmerge op: %s" % op,pkgs
				if op == "add":
					i = vdb.install(f)
				elif op == "replace":
					i = vdb.replace(pkgs[1], f)
				ret = i.finish()
				buildop.clean()
			else:
				print "failure building %s", pkgs[0]
				if not ignore_failures:
					sys.exit(1)

			# force this explicitly- can hold onto a helluva lot more then we would like.
			del f
		if ret != True:
			print "got %s for a phase execution for %s" % (ret, pkgs[0])
			if not ignore_failures:
				return 1
		elif not fetchonly:
			buildop.clean()
	
	return 0

if __name__ == "__main__":
	main()
