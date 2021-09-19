from typing import List

from ..base_tracker import GenericPublicTracker


class TestTracker(GenericPublicTracker):

    alias: str = 'test.st7105.ru'

    def get_id_from_link(self, url: str) -> str:
        """Returns forum thread identifier from full thread URL."""
        splitted = url.rstrip('/').split('/')

        result = splitted[-1]

        if not result.isdigit():  # URL contains SEO name in the last chunk
            for result in splitted:
                if result.isdigit():
                    break
        return result

    def get_download_link(self, url: str) -> str:
        """Tries to find .torrent file download link at forum thread page and return that one."""

        page_soup = self.get_torrent_page(url)

        download_link = self.find_links(url, page_soup, definite=r'\.torrent')

        return download_link or ''
