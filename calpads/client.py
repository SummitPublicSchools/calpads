import requests
import logging
import json
import re
import unicodedata
from urllib.parse import urlencode, urlsplit, urlunsplit, parse_qsl, urljoin
from collections import deque
from bs4 import BeautifulSoup, Tag
from lxml import etree
from .reports_form import ReportsForm


class CALPADSClient:

    def __init__(self, username, password):
        self.host = "https://www.calpads.org/"
        self.username = username
        self.password = password
        self.credentials = {'Username': self.username,
                            'Password': self.password}
        self.visit_history = deque(maxlen=10)
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


    def login(self):
        #Dance the OAuth Dance
        self.session.get(self.host)
        # self.log.debug(homepage_response.url)
        # self.log.debug(self.session.cookies)
        # self.log.debug(self.session.get(self.host + 'Leas?format=JSON').content) # Easy check if logging in happened
        return self.visit_history[-1].status_code == 200 and self.visit_history[-1].url == self.host

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

    def download_ods_report(self, report_code, file_name, form_data=None, dry_run=False):
        with self.session as session:
            report_url = self._get_report_link(report_code.lower())
            if report_url:
                session.get(report_url)
            else:
                raise Exception("Report Not Found")
            iframe_url = BeautifulSoup(self.visit_history[-1].text, parser="lxml").find('iframe').get('src')
            session.get(iframe_url)
            #Parse Form Data Hereabouts
            form = ReportsForm(self.visit_history[-1].text)
            if dry_run:
                return form.filtered_parse


            all_with_names = BeautifulSoup(self.visit_history[-1].text, parser="lxml").find_all(lambda x: x.has_attr('name'))

            form_inputs_to_keep = ['__VIEWSTATE', '__VIEWSTATEGENERATOR', '__EVENTVALIDATION']
            form_inputs_endings = ('HiddenIndices', 'txtValue', 'ddValue')

            in_expected_keys = [tag for tag in all_with_names if tag['name'] in form_inputs_to_keep
                                or tag['name'].endswith(form_inputs_endings)]
            in_expected_keys_names = [tag['name'] for tag in in_expected_keys]
            values_in_expected_key_tags = [tag.get('value', '') for tag in in_expected_keys]
            form_data = dict(zip(in_expected_keys_names, values_in_expected_key_tags))
            prefilled_values = {"ReportViewer1$ctl08$ctl03$ddValue": 3,
                                "ReportViewer1$ctl08$ctl05$ddValue": 5,
                                "ReportViewer1$ctl08$ctl07$ddValue": 19,
                                "ReportViewer1$ctl08$ctl09$ddValue": 1,
                                "ReportViewer1$ctl08$ctl23$ddValue": 1,
                                "ReportViewer1$ctl08$ctl11$divDropDown$ctl01$HiddenIndices": '0,1',
                                "ReportViewer1$ctl08$ctl13$divDropDown$ctl01$HiddenIndices": '2',
                                "ReportViewer1$ctl08$ctl15$divDropDown$ctl01$HiddenIndices": '5,6,7',
                                "ReportViewer1$ctl08$ctl17$divDropDown$ctl01$HiddenIndices": '0',
                                "ReportViewer1$ctl08$ctl19$divDropDown$ctl01$HiddenIndices": '0,1',
                                "ReportViewer1$ctl08$ctl21$divDropDown$ctl01$HiddenIndices": '0,1,2,3'
                                }
            form_data.update(prefilled_values)

            # TODO: Test how form data treats None or False diferently from empty string
            form_data = {k: v for k, v in form_data.items() if v != ''}

            session.post(self.visit_history[-1].url,
                         data=form_data)

            regex = re.compile('(?<="ExportUrlBase":")[^"]+(?=")')  # Look for text sandwitched between the lookbehind and
            # the lookahead, but EXCLUDE the double quotes (i.e. find the first double quotes as the upper limit of the text)

            split_query = None
            if regex.search(self.visit_history[-1].text):
                self.log.debug('Found ExportUrlBase in the URL')
                export_url_base = regex.search(self.visit_history[-1].text).group(0)
                q = urlsplit(urljoin("https://reports.calpads.org",
                                     export_url_base)
                             .replace('\\u0026', '&')
                             .replace('%3a', ':')
                             .replace('%2f', '/')
                             ).query
                split_query = parse_qsl(q)

            if split_query:
                self.log.debug("Adding Format parameter to the URL")
                split_query.append(('Format', "PDF"))
                self.log.debug("Rejoining the query elements again again")
                scheme, netloc, path, query, frag = urlsplit(urljoin("https://reports.calpads.org",
                                                                     export_url_base))

                report_dl_url = urlunsplit([scheme, netloc, path, urlencode(split_query), frag])
                session.get(report_dl_url)
                with open(file_name, 'wb') as f:
                    f.write(self.visit_history[-1].content)
                    return "We did that yo!"

    def _get_report_link(self, report_code, is_snapshot=False):
        #TODO: Lowercase report_code either here or in whatever ends up calling it
        with self.session as session:
            if is_snapshot:
                session.get('https://www.calpads.org/Report/Snapshot')
            else:
                session.get('https://www.calpads.org/Report/ODS')
            response = self.visit_history[-1]
            if report_code == '8.1eoy3' and is_snapshot:
                # TODO: Might add another variable and if-condition to re-use for ODS as well as Snapshot
                return 'https://www.calpads.org/Report/Snapshot/8_1_StudentProfileList_EOY3_'
            else:
                root = etree.fromstring(response.text, parser=etree.HTMLParser(encoding='utf8'))
                elements = root.xpath("//*[@class='num-wrap-in']")
                for element in elements:
                    if report_code == element.text:
                        return urljoin(self.host, element.xpath('./../../a')[0].attrib['href'])
                #TODO: Write this exception in an exceptions.py
                #raise ReportNotFound('{} report code cannot be found on the webpage'.format(report_code))

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
            self.visit_history.append(r)
            return r


