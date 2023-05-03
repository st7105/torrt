import re
from typing import List, Optional

import torf
from furl import furl

from ..base_tracker import GenericPrivateTracker


class KinozalTracker(GenericPrivateTracker):
    """This class implements .torrent files downloads for http://kinozal.tv/ tracker."""

    alias: str = 'kinozal.tv'
    login_url: str = 'https://%(domain)s/takelogin.php'
    auth_cookie_name: str = 'uid'
    mirrors: List[str] = ['kinozal-tv.appspot.com', 'kinozal.me']
    encoding: str = 'cp1251'

    def get_login_form_data(self, login: str, password: str) -> dict:
        """Returns a dictionary with data to be pushed to authorization form."""
        return {'username': login, 'password': password, 'returnto': ''}

    def get_id_from_link(self, url: str) -> str:
        """Returns forum thread identifier from full thread URL."""
        return url.split('=')[1]

    def get_download_link(self, url: str) -> str:
        """Tries to find .torrent file download link at forum thread page and return that one."""

        page_soup = self.get_torrent_page(url)

        is_anonymous = self.find_links(url, page_soup, 'signup') is not None

        if is_anonymous:
            domain = self.extract_domain(url)

            self.login(domain)

            page_soup = self.get_torrent_page(url, drop_cache=True)

        expected_link = rf'/download.+\={self.get_id_from_link(url)}'
        download_link = self.find_links(url, page_soup, definite=expected_link)

        return download_link or ''

    @classmethod
    def get_torrent_id(cls, url: str):
        f_url = furl(url)

        return f_url.args.get('id')

    def get_torrent_magnet(self, url: str) -> Optional[torf.Magnet]:
        torrent_id = self.get_torrent_id(url)

        domain = self.extract_domain(url)

        hash_url = f"https://{domain}/get_srv_details.php?id={torrent_id}&action=2"

        page_soup = self.get_torrent_page(hash_url, drop_cache=True)

        pattern = re.compile(r"Инфо хеш: (.*)")

        if element := page_soup.find('li', text=pattern):
            match = pattern.match(element.text)

            return torf.Magnet(match.group(1).lower())
