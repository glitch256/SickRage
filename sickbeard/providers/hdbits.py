# This file is part of Sick Beard.                                                                                                       
#                                                                                                                                        
# Sick Beard is free software: you can redistribute it and/or modify                                                                     
# it under the terms of the GNU General Public License as published by                                                                   
# the Free Software Foundation, either version 3 of the License, or                                                                      
# (at your option) any later version.                                                                                                    
#                                                                                                                                        
# Sick Beard is distributed in the hope that it will be useful,                                                                          
# but WITHOUT ANY WARRANTY; without even the implied warranty of                                                                         
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the                                                                          
#  GNU General Public License for more details.                                                                                          
#                                                                                                                                        
# You should have received a copy of the GNU General Public License                                                                      
# along with Sick Beard.  If not, see <http://www.gnu.org/licenses/>.                                                                    

import re
import time
import datetime
import urllib
import urlparse
import sys
import generic
import sickbeard

from lib import requests
from lib.requests import exceptions
from sickbeard import classes
from sickbeard import logger, tvcache, exceptions
from sickbeard import helpers
from sickbeard import clients
from sickbeard.common import cpu_presets
from sickbeard.exceptions import ex, AuthException
try:
    import json
except ImportError:
    from lib import simplejson as json


class HDBitsProvider(generic.TorrentProvider):
    def __init__(self):

        generic.TorrentProvider.__init__(self, "HDBits")

        self.supportsBacklog = True

        self.enabled = False
        self.username = None
        self.password = None
        self.uid = None
        self.hash = None
        self.ratio = None

        self.cache = HDBitsCache(self)

        self.url = 'http://hdbits.org'
        self.search_url = 'http://hdbits.org/api/torrents'
        self.rss_url = 'http://hdbits.org/api/torrents'
        self.download_url = 'http://hdbits.org/download.php?'

    def isEnabled(self):
        return self.enabled

    def _checkAuth(self):

        if not self.username or not self.password:
            raise AuthException("Your authentication credentials for " + self.name + " are missing, check your config.")

        return True

    def _checkAuthFromData(self, parsedJSON):

        if parsedJSON is None:
            return self._checkAuth()

        if 'status' in parsedJSON and 'message' in parsedJSON:
            if parsedJSON.get('status') == 5:
                logger.log(u"Incorrect authentication credentials for " + self.name + " : " + parsedJSON['message'],
                           logger.DEBUG)
                raise AuthException(
                    "Your authentication credentials for " + self.name + " are incorrect, check your config.")

        return True

    def _get_season_search_strings(self, ep_obj):
        season_search_string = [self._make_post_data_JSON(show=ep_obj.show, season=ep_obj.scene_season)]
        return season_search_string

    def _get_episode_search_strings(self, ep_obj, add_string=''):
        episode_search_string = [self._make_post_data_JSON(show=ep_obj.show, episode=ep_obj)]
        return episode_search_string

    def _get_title_and_url(self, item):

        title = item['name']
        if title:
            title = title.replace(' ', '.')

        url = self.download_url + urllib.urlencode({'id': item['id'], 'passkey': self.password})

        return (title, url)

    def getURL(self, url, post_data=None, headers=None, json=False):

        if not self.session:
            self.session = requests.Session()

        try:
            # Remove double-slashes from url
            parsed = list(urlparse.urlparse(url))
            parsed[2] = re.sub("/{2,}", "/", parsed[2])  # replace two or more / with one
            url = urlparse.urlunparse(parsed)

            if sickbeard.PROXY_SETTING:
                proxies = {
                    "http": sickbeard.PROXY_SETTING,
                    "https": sickbeard.PROXY_SETTING,
                }

                r = self.session.get(url, data=post_data, proxies=proxies, verify=False)
            else:
                r = self.session.get(url, data=post_data, verify=False)
        except (requests.exceptions.ConnectionError, requests.exceptions.HTTPError), e:
            logger.log(u"Error loading " + self.name + " URL: " + str(sys.exc_info()) + " - " + ex(e), logger.ERROR)
            return None

        if r.status_code != 200:
            logger.log(self.name + u" page requested with url " + url + " returned status code is " + str(
                r.status_code) + ': ' + clients.http_error_code[r.status_code], logger.WARNING)
            return None
        if json:
            return r.json()
        return r.content

    def _doSearch(self, search_params, epcount=0, age=0):
        results = []

        self._checkAuth()

        logger.log(u"Search url: " + self.search_url + " search_params: " + search_params, logger.DEBUG)

        parsedJSON = self.getURL(self.search_url, post_data=search_params, json=True)

        if parsedJSON is None:
            logger.log(u"Error trying to load " + self.name + " JSON data", logger.ERROR)
            return []

        if self._checkAuthFromData(parsedJSON):
            if parsedJSON and 'data' in parsedJSON:
                items = parsedJSON['data']
            else:
                logger.log(u"Resulting JSON from " + self.name + " isn't correct, not parsing it", logger.ERROR)
                items = []

            for item in items:
                results.append(item)

        return results

    def findPropers(self, search_date=None):
        results = []

        search_terms = [' proper ', ' repack ']

        for term in search_terms:
            for item in self._doSearch(self._make_post_data_JSON(search_term=term)):
                if item['utadded']:
                    try:
                        result_date = datetime.datetime.fromtimestamp(int(item['utadded']))
                    except:
                        result_date = None

                    if result_date:
                        if not search_date or result_date > search_date:
                            title, url = self._get_title_and_url(item)
                            results.append(classes.Proper(title, url, result_date))

        return results

    def _make_post_data_JSON(self, show=None, episode=None, season=None, search_term=None):

        post_data = {
            'username': self.username,
            'passkey': self.password,
            'category': [2],
            # TV Category
        }

        if episode:
            post_data['tvdb'] = {
                'id': show.indexerid,
                'season': episode.scene_season,
                'episode': episode.scene_episode
            }

        if season:
            if show.air_by_date or show.sports:
                post_data['tvdb'] = {
                    'id': show.indexerid,
                    'season': str(episode.airdate)[:7],
                }
            else:
                post_data['tvdb'] = {
                    'id': show.indexerid,
                    'season': season,
                }

        if search_term:
            post_data['search'] = search_term

        return json.dumps(post_data)

    def seedRatio(self):
        return self.ratio


class HDBitsCache(tvcache.TVCache):
    def __init__(self, provider):

        tvcache.TVCache.__init__(self, provider)

        # only poll HDBits every 15 minutes max                                                                                          
        self.minTime = 15

    def updateCache(self):

        # delete anything older then 7 days
        logger.log(u"Clearing " + self.provider.name + " cache")
        self._clearCache()

        if not self.shouldUpdate():
            return

        if self._checkAuth(None):

            data = self._getRSSData()

            # As long as we got something from the provider we count it as an update                                                     
            if data:
                self.setLastUpdate()
            else:
                return []

            parsedJSON = helpers.parse_json(data)

            if parsedJSON is None:
                logger.log(u"Error trying to load " + self.provider.name + " JSON feed", logger.ERROR)
                return []

            if self._checkAuth(parsedJSON):
                if parsedJSON and 'data' in parsedJSON:
                    items = parsedJSON['data']
                else:
                    logger.log(u"Resulting JSON from " + self.provider.name + " isn't correct, not parsing it",
                               logger.ERROR)
                    return []

                ql = []
                for item in items:

                    ci = self._parseItem(item)
                    if ci is not None:
                        ql.append(ci)

                    time.sleep(cpu_presets[sickbeard.CPU_PRESET])

                myDB = self._getDB()
                myDB.mass_action(ql)

            else:
                raise exceptions.AuthException(
                    "Your authentication info for " + self.provider.name + " is incorrect, check your config")

        else:
            return []

    def _getRSSData(self):
        return self.provider.getURL(self.provider.rss_url, post_data=self.provider._make_post_data_JSON())

    def _parseItem(self, item):

        (title, url) = self.provider._get_title_and_url(item)

        if title and url:
            logger.log(u"Adding item to results: " + title, logger.DEBUG)
            return self._addCacheEntry(title, url)
        else:
            logger.log(u"The data returned from the " + self.provider.name + " is incomplete, this result is unusable",
                       logger.ERROR)
            return None

    def _checkAuth(self, data):
        return self.provider._checkAuthFromData(data)


provider = HDBitsProvider()                                                                                                              
