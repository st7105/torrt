import logging
import re
from datetime import datetime
from http.cookiejar import CookieJar
from itertools import chain
from locale import getlocale, setlocale, LC_ALL
from typing import List, Optional, Union
from urllib.parse import urlparse, urljoin, parse_qs

import torf
from furl import furl

from .exceptions import TorrtTrackerException
from .utils import (
    parse_torrent, make_soup, encode_value, WithSettings, TrackerObjectsRegistry, TorrentData,
    PageData, TrackerClassesRegistry, HttpClient, Response, BeautifulSoup
)

__log__ = logging.getLogger(__name__)


class BaseTracker(WithSettings):
    """Base torrent tracker handler class offering helper methods for its ancestors."""

    config_entry_name: str = 'trackers'

    alias: str = None
    """Tracker alias. Usually main tracker domain. See also `mirrors` attribute."""

    mirrors: List[str] = []
    """List of mirror domain names."""

    encoding: Optional[str] = None
    """Tracker html page encoding (cp1251 or other)."""

    test_urls: List[str] = []
    """Page URLs for automatic tests of torrent extraction."""

    raise_on_error_response: bool = False
    """Whether to raise an exception on request errors.
    Primary use is debug and testsuite.
    
    """

    def __init__(self, cookies: dict = None, query_string: str = None):

        if cookies is None:
            cookies = {}

        self.cookies = cookies
        self.query_string = query_string

        # Cached data for currently processed torrent.
        self._torrent_page_url: str = ''
        self._torrent_page: Optional[BeautifulSoup] = None

        self.client = HttpClient(
            silence_exceptions=not self.raise_on_error_response,
            dump_fname_tpl=f'%(ts)s_{self.__class__.__name__}.html'
        )

        super().__init__()

    def __init_subclass__(cls, **kwargs):
        if cls.alias:
            TrackerClassesRegistry.add(cls)

    def get_query_string(self) -> str:
        return self.query_string

    def encode_value(self, value: str) -> Union[bytes, str]:
        """Encodes a value.

        :param value:

        """
        return encode_value(value, self.encoding)

    def register(self):
        """Adds this object into TrackerObjectsRegistry."""

        TrackerObjectsRegistry.add(self)

    @classmethod
    def can_handle(cls, string: str) -> bool:
        """Returns boolean whether this tracker can handle torrent from string.

        :param string: String, describing torrent. E.g. URL from torrent comment.

        """
        for domain in chain([cls.alias], cls.mirrors):
            if domain in string:
                return True
        return False

    @classmethod
    def extract_scheme(cls, url: str) -> str:
        """Extracts scheme from a given URL.

        :param url:

        """
        return furl(url).scheme

    @classmethod
    def extract_domain(cls, url: str) -> str:
        """Extracts domain from a given URL.

        :param url:

        """
        return furl(url).netloc

    @classmethod
    def replace_domain(cls, url: str, domain: str) -> str:

        url = furl(url)

        url.netloc = domain

        return str(url)

    def get_response(
            self,
            url: str,
            form_data: dict = None,
            allow_redirects: bool = True,
            referer: str = None,
            cookies: Union[dict, CookieJar] = None,
            query_string: str = None,
            as_soup: bool = False

    ) -> Optional[Union[Response, BeautifulSoup]]:
        """Returns an HTTP resource object from given URL.

        If a dictionary is passed in `form_data` POST HTTP method
        would be used to pass data to resource (even if that dictionary is empty).

        :param url: URL to get data from

        :param form_data: data for POST

        :param allow_redirects: whether to follow server redirects

        :param referer: data to put into Referer header

        :param cookies: cookies to use

        :param query_string:  query string (GET parameters) to add to URL

        :param as_soup: whether to return BeautifulSoup object instead of Requests response

        """
        if query_string:
            delim = '?'
            if '?' in url:
                delim = '&'
            url = f'{url}{delim}{query_string}'

        result = self.client.request(
            url=url,
            data=form_data,
            referer=referer,
            allow_redirects=allow_redirects,
            cookies=cookies,
        )

        if result and as_soup:
            result = self.make_page_soup(result.text)

        return result

    @classmethod
    def make_page_soup(cls, html: str) -> BeautifulSoup:
        """Returns BeautifulSoup object from a html.

        :param html:

        """
        return make_soup(html)

    @classmethod
    def find_links(cls, url: str, page_soup: BeautifulSoup, definite: str = None) -> Union[Optional[str], List[str]]:
        """Returns a list with hyperlinks found in supplied page_soup
        or a definite link.

        :param url: page URL
        :param page_soup: page soup
        :param definite: regular expression to match link

        """
        if not page_soup:
            return None if definite else []

        if definite is not None:
            link = page_soup.find(href=re.compile(definite))

            if link:
                return cls.expand_link(url, link.get('href'))

            return link

        else:
            links = []

            for link in page_soup.find_all('a'):
                href = link.get('href')

                if href:
                    links.append(cls.expand_link(url, href))

            return links

    @classmethod
    def expand_link(cls, base_url: str, link: str) -> str:
        """Expands a given relative link using base URL if required.

        :param base_url:
        :param link: absolute or relative link

        """
        if not link.startswith('http'):
            link = urljoin(base_url, link)

        return link

    def test_configuration(self) -> bool:
        """This should implement a configuration test, e.g. make test login and report success."""
        return True

    def get_torrent(self, url: str) -> Optional[TorrentData]:
        """This method should be implemented in torrent tracker handler class
        and must return .torrent file contents.

        :param url: URL to download torrent file from

        """
        raise NotImplementedError  # pragma: nocover

    def extract_page_data(self) -> PageData:
        data = PageData(
            title=self.extract_page_title(),
            cover=self.extract_page_cover(),
            date_updated=f"{self.extract_page_date_updated() or ''}",
        )
        return data

    def extract_page_title(self) -> str:
        page = self._torrent_page

        if not page:
            return ''

        return getattr(page.select_one('title'), 'text', '')

    def extract_page_cover(self) -> str:
        return ''

    def extract_page_date_updated(self) -> Optional[datetime]:
        return None

    def parse_datetime(self, dt_str: str, fmt: str, *, locale: str = ''):
        old_locale = getlocale()

        if locale:
            setlocale(LC_ALL, (locale, 'UTF-8'))

        try:
            try:
                return datetime.strptime(dt_str, fmt)

            except ValueError:
                return None
        finally:
            setlocale(LC_ALL, old_locale)

    def get_torrent_page(self, url: str, *, drop_cache: bool = False) -> BeautifulSoup:
        """Get torrent page as soup for further data extraction.

        :param url:
        :param drop_cache: Do not use cached version if any.

        """
        torrent_page = self._torrent_page

        if url != self._torrent_page_url:
            drop_cache = True

        if drop_cache or not torrent_page:
            torrent_page = self.get_response(
                url,
                referer=url,
                cookies=self.cookies,
                query_string=self.get_query_string(),
                as_soup=True
            )
            self._torrent_page = torrent_page
            self._torrent_page_url = url

        return torrent_page

    def get_torrent_magnet(self, url: str) -> Optional[torf.Magnet]:
        raise NotImplementedError


class GenericTracker(BaseTracker):
    """Generic torrent tracker handler class implementing most common tracker handling methods."""

    def get_mirrors(self, url: str) -> List[str]:
        original_domain = self.extract_domain(url)
        mirrors = [self.alias] + self.mirrors
        if original_domain in mirrors:
            mirrors.remove(original_domain)
        return [original_domain] + mirrors

    def get_id_from_link(self, url: str) -> str:
        """Returns forum thread identifier from full thread URL.

        :param url:

        """
        return url.split('=')[1]

    def iter_mirrors(self, url: str):
        mirrors = self.get_mirrors(url)

        for mirror_domain in mirrors:
            yield self.replace_domain(url, mirror_domain)

    def get_torrent(self, url: str) -> Optional[TorrentData]:
        """This is the main method which returns torrent file contents
        of file located at URL.

        :param url: URL to find and get torrent from

        """
        for mirror_url in self.iter_mirrors(url):

            try:
                download_link = self.get_download_link(mirror_url)

                if not download_link:
                    raise TorrtTrackerException(f'Cannot find torrent file download link at {mirror_url}')

                page_data = self.extract_page_data()

                __log__.debug(f'Torrent download link found: {download_link}')

                torrent_contents = self.download_torrent(download_link, referer=mirror_url)

                if torrent_contents is None:
                    raise TorrtTrackerException(f'Torrent download from `{download_link}` has failed')

                parsed = parse_torrent(torrent_contents)

                if not parsed:
                    raise TorrtTrackerException(f'Torrent download from `{download_link}` parsed has failed')

                return TorrentData(
                    url=url,
                    url_file=download_link,
                    parsed=parsed,
                    raw=torrent_contents,
                    page=page_data,
                )
            except BaseException as e:
                __log__.warning(f'Cannot find torrent file download link at mirror {mirror_url}: {e}')

        __log__.error(f'Cannot find torrent file download link at {url}')

    def get_magnet(self, url: str) -> Optional[torf.Magnet]:

        for mirror_url in self.iter_mirrors(url):

            try:
                torrent_hash = self.get_torrent_magnet(mirror_url)

                if not torrent_hash:
                    raise TorrtTrackerException('Response torrent hash is empty')

                __log__.debug(f'Torrent hash found {torrent_hash}: {mirror_url}')
                return torrent_hash

            except (BaseException, ) as e:
                __log__.warning(f'Cannot find torrent hash at mirror {mirror_url}: {e}')

        __log__.error(f'Cannot find torrent hash at {url}')

    def get_download_url(self, url: str) -> Optional[str]:
        for mirror_url in self.iter_mirrors(url):
            try:
                torrent_url = self.get_download_link(mirror_url)

                if not torrent_url:
                    raise TorrtTrackerException('Response torrent download url is empty')

                __log__.debug(f'Torrent download url found {torrent_url}: {mirror_url}')
                return torrent_url

            except (BaseException,) as e:
                __log__.warning(f'Cannot find torrent download url at mirror {mirror_url}: {e}')

        __log__.error(f'Cannot find torrent download url at {url}')

    def get_download_link(self, url: str) -> str:
        """Tries to find .torrent file download link on page and return it.

        :param url: URL to find a download link at.

        """
        raise NotImplementedError  # pragma: nocover

    def download_torrent(self, url: str, referer: str = None) -> bytes:
        """Returns .torrent file contents from the given URL.

        :param url: torrent file URL
        :param referer: Referer header value

        """
        raise NotImplementedError  # pragma: nocover


class GenericPublicTracker(GenericTracker):
    """Generic torrent tracker handler class implementing most common handling methods for public trackers."""

    login_required: bool = False

    def get_id_from_link(self, url: str) -> str:
        return url.split('/')[-1]

    def download_torrent(self, url: str, referer: str = None) -> Optional[bytes]:
        __log__.debug(f'Downloading torrent file from {url} ...')
        # That was a check that user himself visited torrent's page ;)
        response = self.get_response(url, referer=referer)
        return getattr(response, 'content', None)

    def get_torrent_magnet(self, url: str) -> Optional[torf.Magnet]:

        page_soup = self.get_torrent_page(url, drop_cache=True)

        pattern = re.compile(r'magnet:\?xt=urn:btih:(.*)')

        if element := page_soup.find(href=pattern):
            match = pattern.match(element.attrs.get('href'))

            return torf.Magnet.from_string(match.group(0))


class GenericPrivateTracker(GenericPublicTracker):
    """Generic torrent tracker handler class implementing most common handling methods
    for private trackers (that require user registration).

    """

    login_required: bool = True

    login_url: str = None
    """URL where with login form.
    This can include `%(domain)s` marker in place of a domain name when domain mirrors are used
    (see `mirrors` attribute of BaseTracker).

    """

    auth_cookie_name: str = None
    """Cookie name to verify that a log in was successful."""

    auth_qs_param_name: str = None
    """HTTP GET (query string) parameter name to verify that a log in was successful. Probably session ID."""

    def __init__(self, username: str = None, password: str = None, cookies: dict = None, query_string: str = None):

        super(GenericPrivateTracker, self).__init__(
            cookies=cookies,
            query_string=query_string,
        )

        self.logged_in = False
        # Stores a number of login attempts to prevent recursion.
        self.login_counter = 0

        self.username = username
        self.password = password

    def get_encode_form_data(self, data: dict) -> dict:
        """Encode dictionary from get_login_form_data using Tracker page encoding.

        :param dict data:

        """
        return {key: self.encode_value(value) for key, value in data.items()}

    def get_login_form_data(self, login: str, password: str) -> dict:
        """Should return a dictionary with data to be pushed to authorization form.

        :param login:
        :param password:

        """
        return {'username': login, 'password': password}

    def test_configuration(self) -> bool:
        return self.login(self.alias)

    def login(self, domain: str) -> bool:
        """Implements tracker login procedure. Returns success bool."""

        login_url = self.login_url % {'domain': domain}

        __log__.debug(f'Trying to login at {login_url} ...')

        if self.logged_in:
            raise TorrtTrackerException(f'Consecutive login attempt detected at `{self.__class__.__name__}`')

        if not self.username or self.password is None:
            return False

        self.login_counter += 1

        # No recursion wanted.
        if self.login_counter > 1:
            return False

        allow_redirects = False  # Not to loose cookies on the redirect.

        if self.auth_qs_param_name:
            allow_redirects = True  # To be able to get Session ID from query string.

        form_data = self.get_login_form_data(self.username, self.password)
        form_data = self.get_encode_form_data(form_data)

        response = self.get_response(
            login_url, form_data,
            allow_redirects=allow_redirects,
            cookies=self.cookies
        )

        if not response:  # e.g. Connection aborted.
            return False

        # Login success checks.
        parsed_qs = parse_qs(urlparse(response.url).query)

        if self.auth_cookie_name in response.cookies or self.auth_qs_param_name in parsed_qs:

            self.logged_in = True

            if parsed_qs:
                self.query_string = parsed_qs[self.auth_qs_param_name][0]

            self.cookies = response.cookies

            # Save auth info to config.
            self.save_settings()
            __log__.debug('Login is successful')

        else:
            __log__.warning('Login with given credentials failed')

        return self.logged_in

    def before_download(self, url: str):
        """Used to perform some required actions right before .torrent download.
        E.g.: to set a sentinel cookie that allows the download.

        :param url: torrent file URL

        """

    def get_query_string(self) -> str:
        """Returns an auth query string to be passed to get_response()
        for auth purposes.

        :return: auth string, e.g. sid=1234567890

        """
        query_string = super().get_query_string()

        if self.auth_qs_param_name:
            query_string = f'{self.auth_qs_param_name}={self.query_string}'

        return query_string

    def download_torrent(self, url: str, referer: str = None) -> Optional[bytes]:
        __log__.debug(f'Downloading torrent file from {url} ...')

        self.before_download(url)

        response = self.get_response(
            url,
            cookies=self.cookies,
            query_string=self.get_query_string(),
            referer=referer
        )

        return getattr(response, 'content', None)
