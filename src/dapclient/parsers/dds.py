"""A DDS parser."""

import re

import numpy as np

from ..lib import LOWER_DAP2_TO_NUMPY_PARSER_TYPEMAP, quote
from ..model import BaseType, DatasetType, GridType, SequenceType, StructureType
from . import SimpleParser

constructors = ("grid", "sequence", "structure")
name_regexp = r'[\w%!~"\'\*-]+'


def DAP2_parser_typemap(type_string):
    """Maps a numpy dtype object to a DAP2 compatible dtype object.

    Parameters
    ----------
    type_string : str
        A string representing a numpy dtype object.

    Returns
    -------
    DAP2_parser_typemap : str
        A string representing a numpy dtype object that is
        compatible with the DAP2 specification.
    """
    dtype_str = LOWER_DAP2_TO_NUMPY_PARSER_TYPEMAP[type_string.lower()]
    return np.dtype(dtype_str)


class DDSParser(SimpleParser):
    """A parser for the DDS."""

    def __init__(self, dds):
        super().__init__(dds, re.IGNORECASE)
        self.dds = dds

    def consume(self, regexp):
        """Consume and return a token."""
        token = super().consume(regexp)
        self.buffer = self.buffer.lstrip()
        return token

    def parse(self):
        """Parse the DAS, returning a dataset."""
        dataset = DatasetType("nameless")

        self._extracted_from_structure_5("dataset", dataset)
        dataset._set_id(dataset.name)
        self.consume(";")

        return dataset

    def declaration(self):
        """Parse and return a declaration."""
        token = self.peek(r"\w+").lower()

        lmap = {
            "grid": self.grid,
            "sequence": self.sequence,
            "structure": self.structure,
        }
        method = lmap.get(token, self.base)
        return method()

    def base(self):
        """Parse a base variable, returning a ``BaseType``."""
        data_type_string = self.consume(r"\w+")

        parser_dtype = DAP2_parser_typemap(data_type_string)
        name = quote(self.consume(r"[^;\[]+"))

        shape, dimensions = self.dimensions()
        self.consume(r";")

        data = DummyData(parser_dtype, shape)
        return BaseType(name, data, dimensions=dimensions)

    def dimensions(self):
        """Parse variable dimensions, returning tuples of dimensions/names."""
        shape = []
        names = []
        while not self.peek(";"):
            self.consume(r"\[")
            token = self.consume(name_regexp)
            if self.peek("="):
                names.append(token)
                self.consume("=")
                token = self.consume(r"\d+")
            shape.append(int(token))
            self.consume(r"\]")
        return tuple(shape), tuple(names)

    def sequence(self):
        """Parse a DAS sequence, returning a ``SequenceType``."""
        sequence = SequenceType("nameless")
        return self._extracted_from_structure_4("sequence", sequence)

    def structure(self):
        """Parse a DAP structure, returning a ``StructureType``."""
        structure = StructureType("nameless")
        return self._extracted_from_structure_4("structure", structure)

    # TODO Rename this here and in `parse`, `sequence` and `structure`
    def _extracted_from_structure_4(self, arg0, arg1):
        self._extracted_from_structure_5(arg0, arg1)
        self.consume(";")
        return arg1

    # TODO Rename this here and in `parse`, `sequence` and `structure`
    def _extracted_from_structure_5(self, arg0, arg1):
        self.consume(arg0)
        self.consume("{")
        while not self.peek("}"):
            var = self.declaration()
            arg1[var.name] = var
        self.consume("}")
        arg1.name = quote(self.consume("[^;]+"))

    def grid(self):
        """Parse a DAP grid, returning a ``GridType``."""
        grid = GridType("nameless")
        self.consume("grid")
        self.consume("{")

        self.consume("array")
        self.consume(":")
        array = self.base()
        grid[array.name] = array

        self.consume("maps")
        self.consume(":")
        while not self.peek("}"):
            var = self.base()
            grid[var.name] = var
        self.consume("}")

        grid.name = quote(self.consume("[^;]+"))
        self.consume(";")

        return grid


def dds_to_dataset(dds):
    """Return a dataset object from a DDS representation."""
    return DDSParser(dds).parse()


class DummyData:
    def __init__(self, dtype, shape):
        self.dtype = dtype
        self.shape = shape
