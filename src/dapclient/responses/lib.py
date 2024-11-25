"""Fundamental functions for dapclient responses.

dapclient responses are WSGI applications that convert a dataset into different
representations, like the DDS, DAS and DODS responses described in the DAP
specification.

In addition to the official responses, dapclient also has responses that generate
KML, WMS, JSON, etc., installed as third-party Python packages that declare the
"dapclient.response" entry point.

"""

from importlib.metadata import entry_points, version

from dapclient.lib import load_from_entry_point_relative
from dapclient.model import DatasetType


def load_responses():
    """Load all available responses from the system, returning a dictionary."""
    # Relative import of responses:
    package = "dapclient"
    group_name = "dapclient.response"

    entry_points_impl = entry_points()
    if hasattr(entry_points_impl, "select"):
        eps = entry_points_impl.select(group=group_name)
    else:
        eps = entry_points_impl.get(group_name, [])
    base_dict = dict(
        load_from_entry_point_relative(r, package)
        for r in eps
        if r.module_name.startswith(package)
    )
    opts_dict = {r.name: r.load() for r in eps if not r.module_name.startswith(package)}
    base_dict.update(opts_dict)
    return base_dict


class BaseResponse:
    """A base class for dapclient responses.

    A dapclient response is a WSGI application that converts a dataset into any
    other representation. The most know responses are the DDS, DAS and DODS
    responses from the DAP spec, which describe the dataset structure,
    attributes and data, respectively.

    According to the WSGI specification, WSGI applications must returned an
    iterable object when called. While this is traditionally a list of strings
    representing an HTML response, this is not the case for dapclient. dapclient will
    return an object (the response instance itself), which is an iterable that
    yields the corresponding output (a DDS response, eg).

    In practice, this means that the generation of the response is delayed
    until the data is being sent to the client. But since the response object
    also carries the original dataset, this means it's possible to write WSGI
    middleware that modifies the dataset directly. A WSGI middleware can add
    additional metadata to a dataset, eg, by adding attributes directly to the
    dataset object, without having to generate a new response.

    """

    def __init__(self, dataset):
        self.dataset = dataset
        self.headers = [("XDODS-Server", f"dapclient/{version('dapclient')}")]

    def __call__(self, environ, start_response):
        start_response("200 OK", self.headers)
        return self

    def x_wsgiorg_parsed_response(self, ltype):
        r"""Avoid serialization of datasets.

        This function will return the contained dataset if ``ltype`` is a
        ``dapclient.model.DatasetType`` object. Based on this proposal:

        http://wsgi.readthedocs.org/en/latest/specifications/avoiding_serialization.html
        """
        if ltype is DatasetType:
            return self.dataset

    def __iter__(self):
        raise NotImplementedError("Subclasses must implement __iter__")
