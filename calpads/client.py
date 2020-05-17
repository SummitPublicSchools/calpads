import requests
import logging
from bs4 import BeautifulSoup, Tag


class CALPADSClient:

    def __init__(self, username, password):
        self.username = username
        self.password = password
        self.credentials = {'Username': self.username,
                            'Password': self.password}
        self.session = requests.Session()
        self.session.headers.update({'User-Agent': None})

    def login(self):
        init_response = self.session.get("https://www.calpads.org")
        self.session.cookies.update(init_response.cookies)
        logging.info(init_response.url)

        init_bs = BeautifulSoup(init_response.content)

        #Filling the login form
        self.credentials['__RequestVerificationToken'] = init_bs.find('input',
                                                                      attrs={'name': "__RequestVerificationToken"}
                                                                      )['value']
        self.credentials['ReturnUrl'] = init_bs.find('input',
                                                     attrs={'id': 'ReturnUrl'}
                                                     )['value']
        self.credentials['AgreementConfirmed'] = "True"

        login_response = self.session.post(init_response.url,
                                           data=self.credentials)
        self.session.cookies.update(login_response)

        login_bs = BeautifulSoup(login_response.content)
        logging.info(login_response)

        #Interstitial OpenID Page
        openid_form_data = {input_['name']: input_["value"] for input_ in login_bs.find_all('input')}

        homepage_response = self.session.post(login_bs.find('form')['action'],
                                              data=openid_form_data
                                              )
        logging.info(homepage_response)

        return homepage_response.ok
