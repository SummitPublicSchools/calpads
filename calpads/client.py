import requests
import logging
from urllib.parse import urlencode, urlsplit, urlunsplit, parse_qs, urljoin
from bs4 import BeautifulSoup, Tag


class CALPADSClient:

    def __init__(self, username, password):
        self.host = "https://www.calpads.org/"
        self.username = username
        self.password = password
        self.credentials = {'Username': self.username,
                            'Password': self.password}
        self.session = requests.Session()
        self.session.headers.update({'User-Agent': "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 \
        (KHTML, like Gecko) Chrome/70.0.3538.77 Safari/537.36"})
        self.session.hooks['response'].append(self._handle_event_hooks)
        self.log = logging.getLogger(__name__)
        log_fmt = f'%(levelname)s: %(asctime)s {self.__class__.__name__}.%(funcName)s: %(message)s'
        stream_hdlr = logging.StreamHandler()
        stream_hdlr.setFormatter(logging.Formatter(fmt=log_fmt))
        self.log.addHandler(stream_hdlr)
        try:
            self.__connection_status = self.login()
        except RecursionError:
            self.log.info("Looks like the provided credentials might be incorrect. Confirm credentials.")
        #TODO: Find out what error happens when CALPADS is closed for nightly process.

    def login(self):
        #Dance the OAuth Dance
        self.session.get(self.host)
        #If you hit every beat, fetching the host again should return the host url
        homepage_response = self.session.get(self.host)
        # self.log.debug(homepage_response.url)
        # self.log.debug(self.session.cookies)
        # self.log.debug(self.session.get(self.host + 'Leas?format=JSON').content) # Easy check if logging in happened
        return homepage_response.ok and homepage_response.url == self.host

    @property
    def is_connected(self):
        return self.__connection_status #Unclear, but there is a chance this returns a false positive

    def _handle_event_hooks(self, r, *args, **kwargs):
        self.log.debug(("Response STATUS CODE: {}\nChecking hooks for: \n{}\n"
                        .format(r.status_code, r.url)
                        )
                       )
        scheme, netloc, path, query, frag = urlsplit(r.url)
        if path == '/Account/Login' and r.status_code == 200:
            self.log.debug("Handling /Account/Login")
            self.session.cookies.update(r.cookies.get_dict()) #Update the cookies for future requests
            init_bs = BeautifulSoup(r.content,
                                    features='html.parser')
            # Filling the login form
            self.credentials['__RequestVerificationToken'] = init_bs.find('input',
                                                                          attrs={'name': "__RequestVerificationToken"}
                                                                          ).get('value')
            self.credentials['ReturnUrl'] = init_bs.find('input',
                                                         attrs={'id': 'ReturnUrl'}
                                                         ).get('value')
            self.credentials['AgreementConfirmed'] = "True"

            # self.log.debug(self.credentials)
            # Was helpful in debugging bad username & password, but that should probably not hang out on the console :)
            self.session.post(r.url,
                              data=self.credentials
                              )

        elif path in ['/connect/authorize/callback', '/connect/authorize'] and r.status_code == 200:
            self.log.debug("Handling /connect/authorize/callback")
            self.session.cookies.update(r.cookies.get_dict()) #Update the cookies for future requests
            login_bs = BeautifulSoup(r.content,
                                     features='html.parser')

            # Interstitial OpenID Page
            openid_form_data = {input_['name']: input_.get("value") for input_ in login_bs.find_all('input')}

            #A check for the when to try to join on self.host
            if (not urlsplit(login_bs.find('form')['action']).scheme
                and not urlsplit(login_bs.find('form')['action']).netloc):
                self.session.post(urljoin(self.host, login_bs.find('form')['action']),
                                  data=openid_form_data
                                )
            else:
                self.log.debug("Using the action URL from the OpenID interstitial page")
                self.session.post(login_bs.find('form')['action'],
                                  data=openid_form_data
                                  )
        else:
            self.log.debug("No response hook needed for: {}\n".format(r.url))
            return r


