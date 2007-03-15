# Copyright: 2006 Marien Zwart <marienz@gentoo.org>
# License: GPL2
# Based on filter-env by Brian Harring <ferringb@gmail.com>
# and Mike Vapier <spanky@gentoo.org>


"""Filter a bash environment dump."""


from pkgcore.util import demandload
demandload.demandload(
    globals(),
    're '
    'pkgcore.log:logger '
    )


COMMAND_PARSING, SPACE_PARSING = range(2)


def native_run(out, file_buff, vsr, fsr,
               desired_var_match, desired_func_match):
    """Print a filtered environment.

    @param out: file-like object to write to.
    @param file_buff: string containing the environment to filter.
        Should end in '\0'.
    @param vsr: result of build_regex_string or C{None}, for variables.
    @param vsr: result of build_regex_string or C{None}, for functions.
    @param desired_var_match: boolean indicating vsr should match or not.
    @param desired_func_match: boolean indicating fsr should match or not.
    """
    if fsr is None:
        func_match = None
    else:
        fsr = re.compile(fsr)
        if desired_func_match:
            func_match = fsr.match
        else:
            def func_match(data):
                return fsr.match(data) is None

    if vsr is None:
        var_match = None
    else:
        vsr = re.compile(vsr)
        if desired_var_match:
            var_match = vsr.match
        else:
            def var_match(data):
                return vsr.match(data) is None

    process_scope(out, file_buff, 0, var_match, func_match, '\0')


try:
    from pkgcore.ebuild._filter_env import run
except ImportError:
    cpy_run = None
    run = native_run
else:
    cpy_run = run


def build_regex_string(tokens):
    if not tokens:
        return None
    result = []
    for token in tokens:
        if not token:
            continue
        escaped = False
        l = []
        for ch in token:
            if ch == '.' and not escaped:
                l.append('[^= ]')
            else:
                l.append(ch)
            if ch == '\\':
                escaped = not escaped
            else:
                escaped = False
        result.append(''.join(l))
    if len(result) == 1:
        return '^%s$' % result[0]
    return '^(%s)$' % '|'.join(result)


FUNC_LEN = len('function')
def is_function(buff, pos):
    """@returns: start, end, pos or None, None, None tuple."""
    isspace = str.isspace
    while buff[pos] in ' \t':
        pos += 1
    if buff[pos:pos + FUNC_LEN] == 'function':
        pos += FUNC_LEN
    while isspace(buff[pos]):
        pos += 1
    start = pos
    while buff[pos] not in '\0 \t\n="\'()':
        pos += 1
    end = pos
    if end == start:
        return None, None, None
    while buff[pos] in ' \t':
        pos += 1
    if buff[pos] != '(':
        return None, None, None
    pos += 1
    while buff[pos] in ' \t':
        pos += 1
    if buff[pos] != ')':
        return None, None, None
    pos += 1
    while isspace(buff[pos]):
        pos += 1
    if buff[pos] != '{':
        return None, None, None
    return start, end, pos + 1


def is_envvar(buff, pos):
    """@returns: start, end, pos or None, None, None tuple."""
    while buff[pos] in ' \t':
        pos += 1
    start = pos
    while True:
        if buff[pos] in '\0"\'()- \t\n':
            return None, None, None
        if buff[pos] == '=':
            if pos == start:
                return None, None, None
            return start, pos, pos + 1
        pos += 1


def process_scope(out, buff, pos, var_match, func_match, endchar):
    window_start = pos
    window_end = None
    isspace = str.isspace
    end = len(buff)
    while pos < end and buff[pos] != endchar:
        # Wander forward to the next non space.
        if window_end is not None:
            if out is not None:
                out.write(buff[window_start:window_end])
            window_start = pos
            window_end = None
        com_start = pos
        ch = buff[pos]
        if isspace(ch):
            pos += 1
            continue

        # Ignore comments.
        if ch == '#':
            pos = walk_statement_pound(buff, pos, endchar)
            continue

        new_start, new_end, new_p = is_function(buff, pos)
        if new_p is not None:
            func_name = buff[new_start:new_end]
            logger.debug('matched func name %r', func_name)
            new_p = process_scope(None, buff, new_p, None, None, '}')
            logger.debug('ended processing %r', func_name)
            if func_match is not None and func_match(func_name):
                logger.debug('filtering func %r', func_name)
                window_end = com_start
            pos = new_p
            pos += 1
            continue
        # Check for env assignment.
        new_start, new_end, new_p = is_envvar(buff, pos)
        if new_p is None:
            # Non env assignment.
            pos = walk_command_complex(buff, pos, endchar, COMMAND_PARSING)
            # icky icky icky icky
            if pos < end and buff[pos] != endchar:
                pos+=1
        else:
            # Env assignment.
            var_name = buff[new_start:new_end]
            pos = new_p
            logger.debug('matched env assign %r', var_name)

            if var_match is not None and var_match(var_name):
                # This would be filtered.
                logger.info("filtering var '%s'", var_name)
                window_end = com_start

            if pos >= end:
                return pos

            while (pos < end and not isspace(buff[pos])
                   and buff[pos] != ';'):
                if buff[pos] == "'":
                    pos = walk_statement_no_parsing(buff, pos + 1, "'") + 1
                elif buff[pos] in '"`':
                    pos = walk_command_escaped_parsing(buff, pos + 1,
                                                       buff[pos]) + 1
                elif buff[pos] == '(':
                    pos = walk_command_escaped_parsing(buff, pos + 1, ')') + 1
                elif buff[pos] == '$':
                    pos += 1
                    if pos >= end:
                        continue
                    pos = walk_dollar_expansion(buff, pos, end, endchar)
                    continue
                else:
                    # blah=cah ; single word
                    pos = walk_command_complex(buff, pos, ' ', SPACE_PARSING)

    if out is not None:
        if window_end is None:
            window_end = pos
        if window_end > end:
            window_end = end
        out.write(buff[window_start:window_end])

    return pos


def walk_statement_no_parsing(buff, pos, endchar):
    pos = buff.find(endchar, pos)
    if pos == -1:
        pos = len(buff) - 1
    return pos


def walk_statement_dollared_quote_parsing(buff, pos, endchar):
    end = len(buff)
    while pos < end:
        if buff[pos] == endchar:
            return pos
        elif buff[pos] == '\\':
            pos += 1
        pos += 1
    return pos


def walk_here_statement(buff, pos):
    pos += 1
    logger.debug('starting here processing for COMMAND for level 2 at p == %.10s',
                 pos)
    if buff[pos] == '<':
        logger.debug(
            "correction, it's a third level here. Handing back to command "
            'parsing')
        return pos + 1
    isspace = str.isspace
    end = len(buff)
    while pos < end and (isspace(buff[pos]) or buff[pos] == '-'):
        pos += 1
    if buff[pos] in "'\"":
        end_here = walk_statement_no_parsing(buff, pos + 1, buff[pos])
        pos += 1
    else:
        end_here = walk_command_complex(buff, pos, ' ', SPACE_PARSING)
    here_word = buff[pos:end_here]
    logger.debug('matched len(%s)/%r for a here word',
                 len(here_word), here_word)
    # XXX watch this. Potential for horkage. Need to do the quote
    # removal thing. This sucks.
    end_here += 1
    if end_here >= end:
        return end_here

    here_len = len(here_word)
    end_here = buff.find(here_word, end_here)
    while end_here != -1:
        i = here_len + end_here
        if buff[i] in ';\n\r})':
            i = end_here - 1
            while i >= 0 and buff[i] in '\t ':
                i -= 1
            if i >= 0 and buff[i] == '\n':
                break
        end_here = buff.find(here_word, end_here + here_len)
            
    if end_here == -1:
        return end
    return end_here + len(here_word)


def walk_statement_pound(buff, pos, endchar=None):
    if pos and not buff[pos-1].isspace():
        return pos + 1
    if endchar == '`':
        i = buff.find('\n', pos)
        i2 = buff.find(endchar, pos)
        if i == -1:
            if i2 != -1:
                return i2
        else:
            if i2 != -1:
                return min(i, i2)
            return i
        return len(buff) - 1

    pos = buff.find('\n', pos)
    if pos == -1:
        pos = len(buff) - 1
    return pos


def walk_command_complex(buff, pos, endchar, interpret_level):
    start = pos
    isspace = str.isspace
    end = len(buff)
    while pos < end:
        ch = buff[pos]
        if ch == endchar or (
            (interpret_level == COMMAND_PARSING and ch in ';\n') or
            (interpret_level == SPACE_PARSING and isspace(ch))):
            return pos
        elif ch == '\\':
            pos += 1
        elif ch == '<':
            if (pos < end - 1 and buff[pos + 1] == '<' and
                interpret_level == COMMAND_PARSING):
                pos = walk_here_statement(buff, pos + 1)
                # we continue immediately; walk_here deposits us at the end
                # of the here op, not consuming the final delimiting char
                # since it may be an endchar
                continue
            else:
                logger.debug('noticed <, interpret_level=%s', interpret_level)
        elif ch == '#':
            if start == pos or isspace(buff[pos - 1]) or buff[pos - 1] == ';':
                pos = walk_statement_pound(buff, pos)
                continue
        elif ch == '$':
            pos = walk_dollar_expansion(buff, pos + 1, end, endchar)
            continue
        elif ch == '{':
            pos = walk_command_escaped_parsing(buff, pos + 1, '}')
        elif ch == '(' and interpret_level == COMMAND_PARSING:
            pos = walk_command_escaped_parsing(buff, pos + 1, ')')
        elif ch in '`"':
            pos = walk_command_escaped_parsing(buff, pos + 1, ch)
        elif ch == "'" and endchar != '"':
            pos = walk_statement_no_parsing(buff, pos +1, "'")
        pos += 1
    return pos

def raw_walk_command_escaped_parsing(buff, pos, endchar):
    end = len(buff)
    while pos < end:
        ch = buff[pos]
        if ch == endchar:
            return pos
        elif ch == '\\':
            pos += 1
        elif ch == '{':
            if endchar != '"':
                pos = raw_walk_command_escaped_parsing(
                    buff, pos + 1, '}')
        elif ch == '(':
            if endchar != '"':
                pos = raw_walk_command_escaped_parsing(
                    buff, pos + 1, ')')
        elif ch in '`"':
            pos = raw_walk_command_escaped_parsing(buff, pos + 1, ch)
        elif ch == "'" and endchar != '"':
            pos = walk_statement_no_parsing(buff, pos + 1, "'")
        elif ch == '$':
            pos = walk_dollar_expansion(buff, pos + 1, end, endchar,
                disable_quote = endchar == '"')
            continue
        elif ch == '#' and endchar != '"':
            pos = walk_statement_pound(buff, pos, endchar)
            continue
        pos += 1
    return pos

walk_command_escaped_parsing = raw_walk_command_escaped_parsing

def walk_dollar_expansion(buff, pos, end, endchar, disable_quote=False):
    if buff[pos] == '(':
        return process_scope(None, buff, pos + 1, None, None, ')') + 1
    if buff[pos] == "'" and not disable_quote:
        return walk_statement_dollared_quote_parsing(buff, pos +1, "'") + 1
    if buff[pos] != '{':
        if buff[pos] == '$':
            # short circuit it.
            return pos + 1
        while pos < end and buff[pos] != endchar:
            if buff[pos].isspace():
                return pos
            if buff[pos] == '$':
                # shouldn't this be passing disable_quote ?
                return walk_dollar_expansion(buff, pos + 1, end, endchar)
            if not buff[pos].isalnum():
                if buff[pos] != '_':
                    return pos
            pos += 1

        if pos >= end:
            return end
        return pos
    
    pos += 1
    # shortcut ${$} to avoid going too deep. ${$a} isn't valid, so no concern
    if pos == '$':
        return pos + 1
    while pos < end and buff[pos] != '}':
        if buff[pos] == '$':
            # disable_quote?
            pos = walk_dollar_expansion(buff, pos + 1, end, endchar)
        else:
            pos += 1
    return pos + 1
