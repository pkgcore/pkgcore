
"""Classes wrapping a file-like object to do fancy output on it."""

import os
import sys
import curses


class Formatter(object):

    """Abstract formatter base class.

    @ivar bold: object to pass to L{write} to switch to bold mode.
    @ivar underline: object to pass to L{write} to switch to underlined mode.
    @ivar reset: object to pass to L{write} to turn off bold and underline.
    @ivar nowrap: object to pass to L{write} to turn off word wrapping.
    @ivar wrap: object to pass to L{write} to turn word wrapping on (default).

    The types of these objects are undefined (they depend on the
    implementation of the particular Formatter subclass).
    """

    def __init__(self):
        self._autoline = True

    def autoline(self, mode):
        """Turn auto-newline mode on or off.

        With this on every write call inserts an extra newline at the end.
        It defaults to on.

        @type  mode: boolean.
        """
        self._autoline = mode

    def write(self, *args):
        """Write something to the stream.

        Acceptable arguments are:
        - Strings are simply written to the stream.
        - C{None} is ignored.
        - Functions are called with the formatter as argument.
          Their return value is then used the same way as the other arguments.
        - Formatter subclasses might special-case certain objects.

        The formatter has a couple of attributes that are useful as argument
        to write.
        """

    def fg(self, color=None):
        """Change foreground color.

        @type  color: a string or C{None}.
        @param color: color to change to. A default is used if omitted.
                      C{None} resets to the default color.
        """

    def bg(self, color=None):
        """Change background color.

        @type  color: a string or C{None}.
        @param color: color to change to. A default is used if omitted.
                      C{None} resets to the default color.
        """


class TerminfoColor(object):

    def __init__(self, mode, color):
        self.mode = mode
        self.color = color

    def __call__(self, formatter):
        if self.color is None:
            formatter._current_colors[self.mode] = None
            res = formatter._color_reset
            # slight abuse of boolean True/False and 1/0 equivalence
            other = formatter._current_colors[not self.mode]
            if other is not None:
                res = res + other
        else:
            if self.mode == 0:
                default = curses.COLOR_WHITE
            else:
                default = curses.COLOR_BLACK
            color = formatter._colors.get(self.color, default)
            # The curses module currently segfaults if handed a
            # bogus template so check explicitly.
            template = formatter._set_color[self.mode]
            if template:
                res = curses.tparm(template, color)
            else:
                res = ''
            formatter._current_colors[self.mode] = res
        return res


class TerminfoCode(object):
    def __init__(self, value):
        self.value = value

class TerminfoMode(TerminfoCode):
    def __call__(self, formatter):
        formatter._modes.add(self)
        return self.value

class TerminfoReset(TerminfoCode):
    def __call__(self, formatter):
        formatter._modes.clear()
        return self.value


class TerminfoFormatter(Formatter):

    """Terminfo formatter."""

    _colors = dict(
        black = curses.COLOR_BLACK,
        red = curses.COLOR_RED,
        green = curses.COLOR_GREEN,
        yellow = curses.COLOR_YELLOW,
        blue = curses.COLOR_BLUE,
        magenta = curses.COLOR_MAGENTA,
        cyan = curses.COLOR_CYAN,
        white = curses.COLOR_WHITE)

    def __init__(self, stream=None, term=None, forcetty=False):
        """Initialize.

        @type  stream: file-like object.
        @param stream: stream to output to, defaulting to C{sys.stdout}.
        @type  term: string.
        @param term: terminal type, pulled from the environment if omitted.
        @type  forcetty: bool
        @param forcetty: force output of colors even if the wrapped stream
                         is not a tty.
        """
        Formatter.__init__(self)
        if stream is None:
            stream = sys.stdout
        self.stream = stream
        fd = stream.fileno()
        curses.setupterm(fd=fd, term=term)
        if forcetty or os.isatty(fd):
            getter = curses.tigetstr
        else:
            def getter(attr):
                return ''

        self.reset = TerminfoReset(getter('sgr0'))
        self.bold = TerminfoMode(getter('bold'))
        self.underline = TerminfoMode(getter('smul'))
        self._color_reset = getter('op')
        self._set_color = (getter('setaf'), getter('setab'))
        self._width = getter('cols')
        # [fg, bg]
        self._current_colors = [None, None]
        self._modes = set()
        self._pos = 0
        self._wrap = True

    def nowrap(self, formatter):
        formatter._wrap = False

    def wrap(self, formatter):
        formatter._wrap = True

    def fg(self, color=None):
        return TerminfoColor(0, color)

    def bg(self, color=None):
        return TerminfoColor(1, color)

    def write(self, *args):
        for arg in args:
            while callable(arg):
                arg = arg(self)
            if isinstance(arg, unicode):
                arg = arg.encode(self.stream.encoding or 'ascii', 'replace')
            self.stream.write(str(arg))
        if self._autoline:
            self.stream.write('\n')
        if self._modes:
            self.stream.write(self.reset(self))
        if self._current_colors != [None, None]:
            self._current_colors = [None, None]
            self.stream.write(self._color_reset)


class _Attr(object):
    def __init__(self, toset, reset):
        self.set = toset
        self.reset = reset

class _StyleAttr(_Attr):
    def __init__(self, key, style):
        _Attr.__init__(self, '<span style="%s">' % (style,), '</span>')
        self.key = key


class _StyleReset(object):
    def __init__(self, key):
        self.key = key


class HTMLFormatter(Formatter):

    """HTML implementation of Formatter.

    This is experimental and the output is extremely ugly. You
    probably do not want to use this.
    """

    bold = _Attr('<b>', '</b>')
    underline = _Attr('<ul>', '</ul>')
    reset = object()

    _colors = dict(black = '#000000',
                   red = '#ff0000',
                   green = '#00ff00',
                   yellow = '#ffff00',
                   blue = '#0000ff',
                   magenta = '#ff00ff',
                   cyan = '#00ffff',
                   white = '#ffffff')

    def __init__(self, stream=None):
        """Initialize.

        @type  stream: file-like object.
        @param stream: stream to output to, defaulting to C{sys.stdout}.
        """
        Formatter.__init__(self)
        if stream is None:
            stream = sys.stdout
        self.stream = stream
        self.stack = []

    def fg(self, color=None):
        if color is None:
            return _StyleReset('fg')
        return _StyleAttr('fg', 'color: ' + self._colors.get(color, 'black'))

    def bg(self, color=None):
        if color is None:
            return _StyleReset('bg')
        return _StyleAttr(
            'fg', 'background: ' + self._colors.get(color, 'white'))

    def write(self, *args):
        for arg in args:
            if isinstance(arg, _Attr):
                self.stack.append(arg)
                self.stream.write(arg.set)
            elif arg is self.reset:
                toreset = []
                while self.stack:
                    # TODO should break once all bolds/underlines are popped
                    thing = self.stack.pop()
                    self.stream.write(thing.reset)
                    if thing not in (self.bold, self.underline):
                        toreset.append(thing)
                for thing in toreset:
                    self.stack.append(thing)
                    self.stream.write(thing.set)
            elif isinstance(arg, _StyleReset):
                toreset = []
                while self.stack:
                    # TODO should break once all colors are popped
                    thing = self.stack.pop()
                    self.stream.write(thing.reset)
                    if not (isinstance(thing, _StyleAttr)
                            and thing.key == arg.key):
                        toreset.append(thing)
                for thing in toreset:
                    self.stack.append(thing)
                    self.stream.write(thing.set)
            else:
                # XXX
                self.stream.write(arg)
        while self.stack:
            self.stream.write(self.stack.pop().reset)
