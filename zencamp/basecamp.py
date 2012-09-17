__version__ = "0.1"

from httplib import responses

import httplib2
import urllib
import base64
import re

try:
    import simplejson as json
except:
    import json


class BasecampException(Exception):
    """
    Basecamp returns a 401 response for authentication errors during a call.
    """
    def __init__(self, msg, error_code=None):
        self.msg = msg
        self.error_code = error_code
        if self.error_code == 401:
            raise AuthenticationError(self.msg)

    def __str__(self):
        return repr('%s: %s' % (self.error_code, self.msg))


class AuthenticationError(BasecampException):
    def __init__(self, msg):
        self.msg = msg

    def __str__(self):
        return repr(self.msg)


re_identifier = re.compile(r".*/(?P<identifier>\d+)\.(json|xml)")
def get_id_from_url(url):
    match = re_identifier.match(url)
    if match and match.group('identifier'):
        return match.group('identifier')


API_MAPPING = {
    # Projects
    'list_projects': {
        'path': '/api/v1/projects.json',
        'method': 'GET',
        'status': 200,
    },
}


class Basecamp(object):
    def __init__(self, basecamp_id, username=None, password=None,
            use_api_token=False, headers=None,  client_args={}):
        """
        Instantiates an instance of Basecamp. Takes optional parameters for
        HTTP Basic Authentication

        Parameters:
        username - Specific to your Zendesk account (typically email)
        password - Specific to your Zendesk account or your account's
            API token if use_api_token is True
        use_api_token - use api token for authentication instead of user's
            actual password
        headers - Pass headers in dict form. This will override default.
        client_args - Pass arguments to http client in dict form.
            {'cache': False, 'timeout': 2}
            or a common one is to disable SSL certficate validation
            {"disable_ssl_certificate_validation": True}
        """
        self.data = None

        # API requirements
        self.bc_uri = "https://basecamp.com/%s" % basecamp_id
        self.username = username
        if use_api_token:
            self.username += "/token"
        self.password = password

        # Headers
        self.headers = headers
        if self.headers is None:
            self.headers = {
                # XXX: Make e-mail address configurable
                'User-agent': 'zencamp %s (support@propdata.net)' % __version__,
                'Content-Type': 'application/json'
            }

        # Handle auth
        self.client = httplib2.Http(**client_args)
        if self.username and self.password:
            self.client.add_credentials(self.username, self.password)

    def __getattr__(self, api_call):
        """
        __getattr__ is used as callback method implemented so that
        when an object tries to call a method which is not defined here,
        it looks to find a relationship in the the mapping table.  The
        table provides the structure of the API call and parameters passed
        in the method will populate missing data.
        """
        def call(self, **kwargs):
            api_map = API_MAPPING[api_call]
            method = api_map['method']
            path = api_map['path']
            status = api_map['status']
            valid_params = api_map.get('valid_params', ())
            # Body can be passed from data or in args
            body = kwargs.pop('data', None) or self.data
            # Substitute mustache placeholders with data from keywords
            url = re.sub(
                '\{\{(?P<m>[a-zA-Z_]+)\}\}',
                # Optional pagination parameters will default to blank
                lambda m: "%s" % kwargs.pop(m.group(1), ''),
                self.bc_uri + path
            )
            # Validate remaining kwargs against valid_params and add
            # params url encoded to url variable.
            for kw in kwargs:
                if kw not in valid_params:
                    raise TypeError("%s() got an unexpected keyword argument "
                                    "'%s'" % (api_call, kw))
            else:
                url += '?' + urllib.urlencode(kwargs)

            # the 'search' endpoint in an open Zendesk site doesn't return a 401
            # to force authentication. Inject the credentials in the headers to
            # ensure we get the results we're looking for
            if re.match("^/search\..*", path):
                self.headers["Authorization"] = "Basic %s" % (
                    base64.b64encode(self.username + ':' +
                                     self.password))
            elif "Authorization" in self.headers:
                del(self.headers["Authorization"])

            # Make an http request (data replacements are finalized)
            response, content = self.client.request(url, method,
                    body=json.dumps(body), headers=self.headers)

            # Use a response handler to determine success/fail
            return self._response_handler(response, content, status)

        # Missing method is also not defined in our mapping table
        if api_call not in API_MAPPING:
            raise AttributeError('Method "%s" Does Not Exist' % api_call)

        # Execute dynamic method and pass in keyword args as data to API call
        return call.__get__(self)

    @staticmethod
    def _response_handler(response, content, status):
        """
        Handle response as callback

        If the response status is different from status defined in the
        mapping table, then we assume an error and raise proper exception

        Zendesk's response is sometimes the url of a newly created user/
        ticket/group/etc and they pass this through 'location'.  Otherwise,
        the body of 'content' has our response.
        """
        # Just in case
        if not response:
            raise BasecampException('Response Not Found')

        response_status = int(response.get('status', 0))

        if response_status != status:
            raise BasecampException(content, response_status)

        # Deserialize json content if content exist. In some cases Zendesk
        # returns ' ' strings. Also return false non strings (0, [], (), {})
        if response.get('location'):
            return response.get('location')
        elif content.strip():
            return json.loads(content)
        else:
            return responses[response_status]
