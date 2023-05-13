from urllib.parse import quote_plus

from . import get_cookies


def setup_session(
    openid, password, username=None, check_url=None, session=None, verify=False
):
    """Call to get_cookies.setup_session that is setup for ESGF credentials.

    Parameters
    ----------
    openid : str
        The openid to use for authentication.
    password : str
        The password to use for authentication.
    username : str, optional
        The username to use for authentication.
        `username` should only be necessary for a CEDA openid.
    check_url : str, optional
        The url to check the authentication on.
    session : requests.Session, optional
        The session to use for authentication.
    verify : bool, optional
        Whether to verify the connection.
    """
    session = get_cookies.setup_session(
        _uri(openid),
        username=username,
        password=password,
        check_url=check_url,
        session=session,
        verify=verify,
    )
    # Connections can be kept alive on the ESGF:
    session.headers.update([("Connection", "keep-alive")])
    return session


def _uri(openid):
    """Create ESGF authentication url.

    This function might be sensitive to a future evolution of the ESGF
    security.

    Parameters
    ----------
    openid : str
        The openid to use for authentication.
    """

    def generate_url(dest_url):
        """Generate the url to authenticate to the ESGF.

        Parameters
        ----------
        dest_url : str
            The url to authenticate to.
        """
        dest_node = _get_node(dest_url)

        try:
            url = (
                dest_node + "/esg-orp/j_spring_openid_security_check.htm?"
                "openid_identifier=" + quote_plus(openid)
            )
        except TypeError:
            raise UserWarning("OPENID was not set. " "ESGF connection cannot succeed.")
        if _get_node(openid) == "https://ceda.ac.uk":
            return [url, None]
        else:
            return url

    return generate_url


def _get_node(url):
    """Get the node of the url.

    Parameters
    ----------
    url : str
        The url to get the node from.
    """
    return "/".join(url.split("/")[:3]).replace("http:", "https:")
