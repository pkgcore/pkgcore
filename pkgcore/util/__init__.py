# Copyright: 2005 Brian Harring <ferringb@gmail.com>
# License: GPL2/BSD

"""misc. utility functions"""


def split_negations(data, func=str):
    """"Split iterable into negative and positive elements."""
    neg, pos = [], []
    for line in data:
        if line[0] == '-':
            if len(line) == 1:
                raise ValueError("'-' negation without a token")
            neg.append(func(line[1:]))
        else:
            pos.append(func(line))
    return (tuple(neg), tuple(pos))
