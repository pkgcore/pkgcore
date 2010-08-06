#!/usr/bin/python
from snakeoil.modules import load_module
import inspect, exceptions, sys, os, errno

def gen_segment(name, targets):
    l = ["    .. rubric:: %s" % (name,)]
    l.append('')
    l.append("    .. autosummary::")
    l.append('')
    l.extend("       %s" % x for x in sorted(targets))
    l.append("")
    return "\n".join(l)

def generate_rst(modpath, module, handle=None):
    if handle is None:
        handle = sys.stdout
    target_names = [x for x in dir(module) if not (x.startswith("_")
        or inspect.ismodule(getattr(module, x)))]
    target_names = getattr(module, '__all__', target_names)
    klasses, funcs, exceptions, others = [], [], [], []
    modules = []
    base_exception = globals().get("BaseException", Exception)
    for target in target_names:
        try:
            obj = getattr(module, target)
        except AttributeError, a:
            sys.stderr.write("failed processing %s, accessing %s: %s\n" %
                (modpath, target, a))
            raise
        if inspect.isclass(obj):
            if issubclass(obj, base_exception):
                exceptions.append(target)
            else:
                klasses.append(target)
        elif callable(obj):
            funcs.append(target)
        elif inspect.ismodule(obj):
            modules.append(target)
        else:
            others.append(target)

    handle.write("%s\n" % modpath)
    handle.write('-' * len(modpath))
    handle.write("\n\n.. automodule:: %s\n\n" % (modpath,))
    if funcs:
        handle.write(gen_segment("Functions", funcs))
        handle.write("\n")
    if klasses:
        handle.write(gen_segment("Classes", klasses))
        handle.write("\n")
    if exceptions:
        handle.write(gen_segment("Exceptions", exceptions))
    if modules:
        handle.write(gen_segment("Submodules", modules))
        handle.write("\n")
    if others:
        handle.write(gen_segment("Data", others))
        handle.write("\n")

def regen_if_needed(src, out_path):
    module = load_module(src)
    cur_time = int(os.stat(module.__file__).st_mtime)
    try:
        trg_time = int(os.stat(out_path).st_mtime)
    except EnvironmentError, e:
        if e.errno != errno.ENOENT:
            raise
        trg_time = -1

    if cur_time != trg_time:
        sys.stdout.write("regenerating rst for %s\n" % (src,))
        generate_rst(src, module, open(out_path, "w"))
    os.chmod(out_path, 0644)
    os.utime(out_path, (cur_time, cur_time))


if __name__ == '__main__':
    import sys
    for x in sys.stdin:
        regen_if_needed(*x.rstrip("\n").split(" ", 1))
