"""dapclient error response.

dapclient will capture exceptions returned by the system and return them properly
formated as a DAP error response.

"""

from importlib.metadata import version
from io import StringIO
from traceback import print_exception

from webob import Response

from dapclient.lib import encode


class ErrorResponse:
    """A specialized response for errors.

    This is a special response used when an exception is captured and passed to
    the user as an Opendap error message:

    """

    def __init__(self, info):
        # get exception message
        buf = StringIO()
        print_exception(*info, file=buf)
        message = encode(buf.getvalue())

        # build error message
        code = getattr(info[0], "code", -1)
        self.body = f"""Error {{
    code = {code};
    message = {message};
}}"""

    def __call__(self, environ, start_response):
        res = Response()
        res.text = self.body
        res.status = "500 Internal Error"
        res.content_type = "text/plain"
        res.charset = "utf-8"
        res.headers.add("Content-description", "dods_error")
        res.headers.add("XDODS-Server", f"dapclient/{version('dapclient')}")

        return res(environ, start_response)
