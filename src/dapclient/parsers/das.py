"""A parser for the Dataset Attribute Structure (DAS) response.

This module implements a DAS parser. The ``parse_das`` function will convert a
DAS response into a dictionary of attributes, which can be applied to an
existing dataset using the ``add_attributes`` function.

"""

import ast
import operator
import re
from functools import reduce

from dapclient.lib import walk
from dapclient.parsers import SimpleParser


class DASParser(SimpleParser):
    """A parser for the Dataset Attribute Structure response."""

    def __init__(self, das):
        super().__init__(das, re.IGNORECASE | re.VERBOSE | re.DOTALL)

    def consume(self, regexp):
        """Return a token from the buffer.

        Not that it will Ignore white space when consuming tokens.

        """
        token = super().consume(regexp)
        self.buffer = self.buffer.lstrip()
        return token

    def parse(self):
        """Start the parsing, returning a nested dictionary of attributes."""
        out = {}
        self.consume("attributes")
        self.container(out)
        return out

    def container(self, target):
        """Collect the attributes for a DAP variable."""
        self.consume("{")
        while not self.peek("}"):
            if self.peek(r"[^\s]+\s+{"):
                name = self.consume(r"[^\s]+")
                target[name] = {}
                self.container(target[name])
            else:
                name, values = self.attribute()
                target[name] = values
        self.consume("}")

    def attribute(self):
        """Parse attributes.

        The function will parse attributes from the DAS, converting them to the
        corresponding Python object. Returns the name of the attribute and the
        attribute(s).

        """
        ltype = self.consume(r"[^\s]+")
        name = self.consume(r"[^\s]+")

        values = []
        while not self.peek(";"):
            value = self.consume(
                r"""
                    ""          # empty attribute
                    |           # or
                    ".*?[^\\]"  # from quote up to an unquoted quote
                    |           # or
                    [^;,]+      # up to semicolon or comma
                """
            )

            if ltype.lower() in ("string", "url"):
                value = str(value).strip('"')
            elif value.lower() in ("nan", "nan.", "-nan"):
                value = float("nan")
            elif value.lower() in ("inf", "inf."):
                value = float("inf")
            elif value.lower() in ("-inf", "-inf."):
                value = float("-inf")
            else:
                value = ast.literal_eval(value)

            values.append(value)
            if self.peek(","):
                self.consume(",")

        self.consume(";")

        if len(values) == 1:
            values = values[0]

        return name, values


def parse_das(das):
    """Parse the DAS, returning nested dictionaries."""
    return DASParser(das).parse()


def add_attributes(dataset, attributes):
    """Add attributes from a parsed DAS to a dataset.

    Returns the dataset with added attributes.

    """
    dataset.attributes["NC_GLOBAL"] = attributes.get("NC_GLOBAL", {})
    dataset.attributes["DODS_EXTRA"] = attributes.get("DODS_EXTRA", {})

    for var in list(walk(dataset))[::-1]:
        # attributes can be flat, eg, "foo.bar" : {...}
        if var.id in attributes:
            var.attributes.update(attributes.pop(var.id))

        # or nested, eg, "foo" : { "bar" : {...} }
        try:
            nested = reduce(operator.getitem, [attributes] + var.id.split(".")[:-1])
            k = var.id.split(".")[-1]
            value = nested.pop(k)
        except KeyError:
            pass
        else:
            try:
                var.attributes.update(value)
            except (TypeError, ValueError):
                # This attribute should be given to the parent.
                # Keep around:
                nested.update({k: value})

    # add attributes that don't belong to any child
    for k, v in attributes.items():
        dataset.attributes[k] = v

    return dataset
