from . import get_cookies


def setup_session(username, password, check_url=None, session=None, verify=True):
    """Call to get_cookies.setup_session for URS EARTHDATA at NASA credentials.

    Parameters
    ----------
    username : str
        The username to use for authentication.
    password : str
        The password to use for authentication.
    check_url : str, optional
        The url to check the authentication on.
    session : requests.Session, optional
        The session to use for authentication.
    verify : bool, optional
        Whether to verify the connection.
    """
    if session is not None:
        # URS connections cannot be kept alive at the moment.
        session.headers.update({"Connection": "close"})
    session = get_cookies.setup_session(
        "https://urs.earthdata.nasa.gov",
        username=username,
        password=password,
        session=session,
        check_url=check_url,
        verify=verify,
    )
    return session
