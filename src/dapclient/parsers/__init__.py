"""Parsing related functions.

This module defines functions to parse DAP objects, including a base parser for
DDS and DAS responses.

"""

import ast
import operator
import re
from urllib.parse import unquote

from dapclient.exceptions import ConstraintExpressionError
from dapclient.lib import get_var


def parse_projection(inputstr):
    """Split a projection into items.

    The function takes into account server-side functions, and parse slices
    into Python slice objects.

    Parameters
    ----------
    inputstr : str
        A string representing a projection.

    Returns
    -------
    projection : list
        list of names and slices.
    """

    def tokenize(inputstr):
        start = pos = count = 0
        for char in inputstr:
            if char == "(":
                count += 1
            elif char == ")":
                count -= 1
            elif char == "," and count == 0:
                yield inputstr[start:pos]
                start = pos + 1
            pos += 1
        yield inputstr[start:]

    def parse(token):
        if "(" not in token:
            token = token.split(".")
            token = [re.match(r"(.*?)(\[.*\])?$", part).groups() for part in token]
            token = [(name, parse_hyperslab(slice_ or "")) for (name, slice_) in token]
        return token

    return list(map(parse, tokenize(inputstr)))


def parse_selection(expression, dataset):
    """Parse a selection expression into its elements.

    This function will parse a selection expression into three tokens: two
    variables or values and a comparison operator. Variables are returned as
    dapclient objects from a given dataset, while values are parsed using
    ``ast.literal_eval``.
    """
    id1, op, id2 = re.split("(<=|>=|!=|=~|>|<|=)", expression, 1)

    op = {
        "<=": operator.le,
        ">=": operator.ge,
        "!=": operator.ne,
        "=": operator.eq,
        ">": operator.gt,
        "<": operator.lt,
    }[op]

    try:
        id1 = get_var(dataset, id1)
    except Exception:
        id1 = ast.literal_eval(id1)

    try:
        id2 = get_var(dataset, id2)
    except Exception:
        id2 = ast.literal_eval(id2)

    return id1, op, id2


def parse_ce(query_string):
    """Extract the projection and selection from the QUERY_STRING.

        >>> parse_ce('a,b[0:2:9],c&a>1&b<2')  # doctest: +NORMALIZE_WHITESPACE
        ([[('a', ())], [('b', (slice(0, 10, 2),))], [('c', ())]],
                ['a>1', 'b<2'])
        >>> parse_ce('a>1&b<2')
        ([], ['a>1', 'b<2'])

    This function can also handle function calls in the URL, according to the
    DAP specification:

        >>> ce = 'time&bounds(0,360,-90,90,0,500,00Z01JAN1970,00Z04JAN1970)'
        >>> print(parse_ce(ce))  # doctest: +NORMALIZE_WHITESPACE
        ([[('time', ())]],
                ['bounds(0,360,-90,90,0,500,00Z01JAN1970,00Z04JAN1970)'])

        >>> ce = 'time,bounds(0,360,-90,90,0,500,00Z01JAN1970,00Z04JAN1970)'
        >>> print(parse_ce(ce))  # doctest: +NORMALIZE_WHITESPACE
        ([[('time', ())],
            'bounds(0,360,-90,90,0,500,00Z01JAN1970,00Z04JAN1970)'], [])
        >>> parse_ce('mean(g,0)')
        (['mean(g,0)'], [])
        >>> parse_ce('mean(mean(g.a,1),0)')
        (['mean(mean(g.a,1),0)'], [])

    Parameters
    ----------
    query_string : str
        The QUERY_STRING from the URL.

    Returns
    -------
    projection : tuple
        Returns a tuple with the projection and the selection.
    """
    tokens = [token for token in unquote(query_string).split("&") if token]
    if not tokens:
        projection = []
        selection = []
    elif re.search("<=|>=|!=|=~|>|<|=", tokens[0]):
        projection = []
        selection = tokens
    else:
        projection = parse_projection(tokens[0])
        selection = tokens[1:]

    return projection, selection


def parse_hyperslab(hyperslab):
    """Parse a hyperslab.

    Parameters
    ----------
    hyperslab : str
        A string representing a hyperslab.

    Returns
    -------
    hyperslab : tuple
        Python tuple of slices.
    """
    exprs = [expr for expr in hyperslab[1:-1].split("][") if expr]

    out = []
    for expr in exprs:
        tokens = list(map(int, expr.split(":")))
        start = tokens[0]
        step = 1

        if len(tokens) == 1:
            stop = start + 1
        elif len(tokens) == 2:
            stop = tokens[1] + 1
        elif len(tokens) == 3:
            step = tokens[1]
            stop = tokens[2] + 1
        else:
            raise ConstraintExpressionError(f"Invalid hyperslab {hyperslab}")

        out.append(slice(start, stop, step))

    return tuple(out)


class SimpleParser:
    """A very simple parser."""

    def __init__(self, inputstr, flags=0):
        self.buffer = inputstr
        self.flags = flags

    def peek(self, regexp):
        """Check if a token is present and return it."""
        p = re.compile(regexp, self.flags)
        m = p.match(self.buffer)
        return m.group() if m else ""

    def consume(self, regexp):
        """Consume a token from the buffer and return it."""
        p = re.compile(regexp, self.flags)
        m = p.match(self.buffer)
        if not m:
            raise Exception(f"Unable to parse token: {self.buffer[:10]}")
        token = m.group()
        self.buffer = self.buffer[len(token) :]
        return token
