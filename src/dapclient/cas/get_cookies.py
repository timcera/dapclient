import copy
import warnings
from urllib.parse import urlsplit, urlunsplit

import requests
from bs4 import BeautifulSoup
from requests.packages.urllib3.exceptions import (
    InsecurePlatformWarning,
    InsecureRequestWarning,
)

from dapclient import lib

ssl_verify_categories = [InsecureRequestWarning, InsecurePlatformWarning]


def setup_session(
    uri,
    username=None,
    password=None,
    check_url=None,
    session=None,
    verify=True,
    username_field="username",
    password_field="password",
):
    """Set-up requests session with cookies.

    Uses beautifulsoup and by calling the right url.

    Parameters
    ----------
    uri : str or callable
        The uri to use for authentication.
    username : str, optional
        The username to use for authentication.
    password : str, optional
        The password to use for authentication.
    check_url : str, optional
        The url to check the authentication on.
    session : requests.Session, optional
        The session to use for authentication.
    verify : bool, optional
        Whether to verify the connection.
    username_field : str, optional
        The username field to use for authentication.
    password_field : str, optional
        The password field to use for authentication.
    """
    if session is None:
        # Connections must be closed since some CAS
        # will cough when connections are kept alive:
        headers = [
            ("User-agent", f"dapclient/{lib.__version__}"),
            ("Connection", "close"),
        ]
        session = requests.Session()
        session.headers.update(headers)

    if uri is None:
        return session

    if not verify:
        verify_flag = session.verify
        session.verify = False

    url = uri if isinstance(uri, str) else uri(check_url)
    if password is None or password == "":
        warnings.warn(
            "password was not set. "
            "this was likely unintentional "
            "but will result is much fewer datasets."
        )
        if not verify:
            session.verify = verify_flag
        return session

    # Allow for several subsequent security layers:
    full_url = copy.copy(url)
    if isinstance(full_url, list):
        url = full_url[0]

    with warnings.catch_warnings():
        if not verify:
            # Catch warnings. It is assumed that the
            # user that explicitly uses verify=False
            # is either fully aware of the risks
            # or cannot avoid the risks because of
            # an improperly configured server.
            # This error will usually occur with
            # ESGF authentication.
            for category in ssl_verify_categories:
                warnings.filterwarnings("ignore", category=category)

        response = soup_login(
            session,
            url,
            username,
            password,
            username_field=username_field,
            password_field=password_field,
        )

        # If there are further security levels.
        # At the moment only used for CEDA OPENID:
        if isinstance(full_url, list) and len(full_url) > 1:
            for _ in full_url[1:]:
                response = soup_login(
                    session,
                    response.url,
                    username,
                    password,
                    username_field=None,
                    password_field=None,
                )
        response.close()

        if check_url:
            if username is not None and password is not None:
                res = session.get(check_url, auth=(username, password))
                if res.status_code == 401:
                    res = session.get(res.url, auth=(username, password))
                res.close()
            raise_if_form_exists(check_url, session)

    if not verify:
        session.verify = verify_flag
    return session


def raise_if_form_exists(url, session):
    """This function raises a UserWarning if the link has forms

    Parameters
    ----------
    url : str
        The url to check.
    session : requests.Session
        The session to use for checking.
    """

    user_warning = f"""Navigate to {url}, login and follow instructions.
It is likely that you have to perform some one-time
registration steps before accessing this data."""

    resp = session.get(url)
    soup = BeautifulSoup(resp.content, "lxml")
    if len(soup.select("form")) > 0:
        raise UserWarning(user_warning)


def soup_login(
    session,
    url,
    username,
    password,
    username_field="username",
    password_field="password",
):
    """Login using beautifulsoup.

    Parameters
    ----------
    session : requests.Session
        The session to use for authentication.
    url : str
        The url to use for authentication.
    username : str
        The username to use for authentication.
    password : str
        The password to use for authentication.
    username_field : str, optional
        The username field to use for authentication.
    password_field : str, optional
        The password field to use for authentication.
    """
    resp = session.get(url)

    soup = BeautifulSoup(resp.content, "lxml")
    login_form = soup.select("form")[0]

    def get_to_url(current_url, to_url):
        """Get the url to use for authentication.

        Parameters
        ----------
        current_url : str
            The current url.
        to_url : str
            The url to use for authentication.
        """
        split_current = urlsplit(current_url)
        split_to = urlsplit(to_url)
        comb = [
            val2 if val1 == "" else val1 for val1, val2 in zip(split_to, split_current)
        ]
        return urlunsplit(comb)

    to_url = get_to_url(resp.url, login_form.get("action"))

    session.headers["Referer"] = resp.url

    payload = {}
    if (
        username_field is not None
        and len(login_form.findAll("input", {"name": username_field})) > 0
    ):
        payload[username_field] = username

    if password_field is not None:
        if len(login_form.findAll("input", {"name": password_field})) > 0:
            payload[password_field] = password
        else:
            # If there is no password_field, it might be because
            # something should be handled in the browser
            # for the first attempt. This is common when using
            # dapclient with the ESGF for the first time.
            raise Exception(
                f"""Navigate to {url}.
If you are unable to
login, you must either
wait or use authentication
from another service."""
            )

    # Replicate all other fields:
    for input in login_form.findAll("input"):
        if input.get("name") not in payload and input.get("name") is not None:
            payload[input.get("name")] = input.get("value")

    # Remove other submit fields:
    submit_type = "submit"
    submit_names = [
        input.get("name")
        for input in login_form.findAll("input", {"type": submit_type})
    ]
    for input in login_form.findAll("input", {"type": submit_type}):
        if "submit" in submit_names and input.get("name").lower() != "submit":
            payload.pop(input.get("name"), None)

    return session.post(to_url, data=payload)
