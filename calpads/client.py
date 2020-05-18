import requests
import logging
import json
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

    def get_leas(self):
        """Returns the list of LEAs provided by CALPADS
        Returns:
            list of LEA dictionaries with the keys Disabled, Group, Selected, Text, Value
        """
        response = self.session.get(urljoin(self.host, 'Leas?format=JSON'))
        return json.loads(response.content)

    def get_enrollment_history(self, ssid):
        """Returns a JSON object with the Enrollment history for the provided SSID

        Returns:
            a JSON object with Data and Total Count keys. Expected data is under Data as a List where each
            item is a "row" of data
        """
        response = self.session.get(urljoin(self.host, f'/Student/{ssid}/Enrollment?format=JSON'))
        return json.loads(response.content)

    def get_demographics_history(self, ssid):
        """Returns a JSON object with the Demographics history for the provided SSID

        Returns:
            a JSON object with Data and Total Count keys. Expected data is under Data as a List where each
            item is a "row" of data
        """
        response = self.session.get(urljoin(self.host, f'/Student/{ssid}/Demographics?format=JSON'))
        return json.loads(response.content)

    def get_address_history(self, ssid):
        """Returns a JSON object with the Address history for the provided SSID

        Returns:
            a JSON object with Data and Total Count keys. Expected data is under Data as a List where each
            item is a "row" of data
        """
        response = self.session.get(urljoin(self.host, f'/Student/{ssid}/Address?format=JSON'))
        return json.loads(response.content)

    def get_elas_history(self, ssid):
        """Returns a JSON object with the English Language Acquisition Status (ELAS) history for the provided SSID

        Returns:
            a JSON object with Data and Total Count keys. Expected data is under Data as a List where each
            item is a "row" of data
        """
        response = self.session.get(urljoin(self.host, f'/Student/{ssid}/EnglishLanguageAcquisition?format=JSON'))
        return json.loads(response.content)

    def get_program_history(self, ssid):
        """Returns a JSON object with the Program history for the provided SSID

        Returns:
            a JSON object with Data and Total Count/Total keys. Expected data is under Data as a List where each
            item is a "row" of data
        """
        response = self.session.get(urljoin(self.host, f'/Student/{ssid}/Program?format=JSON'))
        return json.loads(response.content)

    def get_student_course_section_history(self, ssid):
        """Returns a JSON object with the Student Course Section history (SCSE, SCSC) for the provided SSID

        Returns:
            a JSON object with Data and Total Count keys. Expected data is under Data as a List where each
            item is a "row" of data
        """
        response = self.session.get(urljoin(self.host, f'/Student/{ssid}/StudentCourseSection?format=JSON'))
        return json.loads(response.content)

    def get_cte_history(self, ssid):
        """Returns a JSON object with the Career Technical Education (CTE) history for the provided SSID

        Returns:
            a JSON object with Data and Total Count keys. Expected data is under Data as a List where each
            item is a "row" of data
        """
        response = self.session.get(urljoin(self.host, f'/Student/{ssid}/CareerTechnicalEducation?format=JSON'))
        return json.loads(response.content)

    def get_stas_history(self, ssid):
        """Returns a JSON object with the Student Absence Summary (STAS) history for the provided SSID

        Returns:
            a JSON object with Data and Total Count keys. Expected data is under Data as a List where each
            item is a "row" of data
        """
        response = self.session.get(urljoin(self.host, f'/Student/{ssid}/StudentAbsenceSummary?format=JSON'))
        return json.loads(response.content)

    def get_sirs_history(self, ssid):
        """Returns a JSON object with the Student Incident Result (SIRS) history for the provided SSID

        Returns:
            a JSON object with Data and Total Count keys. Expected data is under Data as a List where each
            item is a "row" of data
        """
        response = self.session.get(urljoin(self.host, f'/Student/{ssid}/StudentIncidentResult?format=JSON'))
        return json.loads(response.content)

    def get_soff_history(self, ssid):
        """Returns a JSON object with the Student Offense (SOFF) history for the provided SSID

        Returns:
            a JSON object with Data and Total Count keys. Expected data is under Data as a List where each
            item is a "row" of data
        """
        response = self.session.get(urljoin(self.host, f'/Student/{ssid}/Offense?format=JSON'))
        return json.loads(response.content)

    def get_sped_history(self, ssid):
        """Returns a JSON object with the Special Education (SPED) history for the provided SSID

        Returns:
            a JSON object with Data and Total Count keys. Expected data is under Data as a List where each
            item is a "row" of data
        """
        response = self.session.get(urljoin(self.host, f'/Student/{ssid}/SPED?format=JSON'))
        return json.loads(response.content)

    def get_ssrv_history(self, ssid):
        """Returns a JSON object with the Student Services (SSRV) history for the provided SSID

        Returns:
            a JSON object with Data and Total Count keys. Expected data is under Data as a List where each
            item is a "row" of data
        """
        response = self.session.get(urljoin(self.host, f'/Student/{ssid}/SSRV?format=JSON'))
        return json.loads(response.content)

    def get_psts_history(self, ssid):
        """Returns a JSON object with the Postsecondary Transition Status (PSTS) history for the provided SSID

        Returns:
            a JSON object with Data and Total Count keys. Expected data is under Data as a List where each
            item is a "row" of data
        """
        response = self.session.get(urljoin(self.host, f'/Student/{ssid}/PSTS?format=JSON'))
        return json.loads(response.content)

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


