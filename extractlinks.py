from sgmllib import SGMLParser
from urlparse import urlparse
from urlparse import urljoin

import logging


class LinkExtractor(SGMLParser):
    """A simple LinkExtractor class"""

    def set_base_url(self, base_url=None):
        self.base_url = base_url

    def make_absolute_and_add(self, dict_feed=None):
        if 'href' in dict_feed:
            p = urlparse(dict_feed['href'])
            if p.scheme != "":
                self.links.append(dict_feed)
            else:
                dict_feed['href'] = urljoin(self.base_url, dict_feed['href'])
                self.links.append(dict_feed)

    def reset(self):
        SGMLParser.reset(self)
        self.links = []

    def start_link(self, attrs):
        if not ('rel', 'alternate') in attrs: return
        if('type', 'application/rss+xml') in attrs:
          self.make_absolute_and_add(dict(attrs))
        if('type', 'application/atom+xml') in attrs:
          self.make_absolute_and_add(dict(attrs))
