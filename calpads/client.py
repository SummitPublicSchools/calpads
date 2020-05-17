import requests
import logging
from urllib.parse import urlencode, urlsplit, urlunsplit, parse_qs, urljoin
from bs4 import BeautifulSoup, Tag


class CALPADSClient:

    def __init__(self, username, password):
        self.host = "https://www.calpads.org"
        self.username = username
        self.password = password
        self.credentials = {'Username': self.username,
                            'Password': self.password}
        self.session = requests.Session()
        self.session.headers.update({'User-Agent': None})
        self.log = logging.getLogger(__name__)
        log_fmt = f'%(levelname)s: %(asctime)s {self.__class__.__name__}.%(funcName)s: %(message)s'
        stream_hdlr = logging.StreamHandler()
        stream_hdlr.setFormatter(logging.Formatter(fmt=log_fmt))
        self.log.addHandler(stream_hdlr)

    def login(self):
        init_response = self.session.get(self.host)
        self.session.cookies.update(init_response.cookies.get_dict())
        self.log.debug(init_response.url)

        init_bs = BeautifulSoup(init_response.content,
                                features='html.parser')

        #Filling the login form
        self.credentials['__RequestVerificationToken'] = init_bs.find('input',
                                                                      attrs={'name': "__RequestVerificationToken"}
                                                                      ).get('value')
        self.credentials['ReturnUrl'] = init_bs.find('input',
                                                     attrs={'id': 'ReturnUrl'}
                                                     ).get('value')
        self.credentials['AgreementConfirmed'] = "True"

        login_response = self.session.post(urljoin(self.host, init_response.url),
                                           data=self.credentials)
        
        self.session.cookies.update(login_response.cookies.get_dict())

        login_bs = BeautifulSoup(login_response.content,
                                 features='html.parser')
        self.log.debug(login_response.url)

        #Interstitial OpenID Page
        openid_form_data = {input_['name']: input_.get("value") for input_ in login_bs.find_all('input')}

        homepage_response = self.session.post(urljoin(self.host, login_bs.find('form')['action']),
                                              data=openid_form_data
                                              )
        self.log.info(homepage_response)

        return homepage_response.ok
