import requests
import logging
import json
import re
import time
from urllib.parse import urlencode, urlsplit, urlunsplit, parse_qsl, urljoin
from collections import deque
from json import JSONDecodeError
from lxml import etree
from .reports_form import ReportsForm, REPORTS_DL_FORMAT
from .extracts_form import ExtractsForm
from .files_upload_form import FilesUploadForm


class CALPADSClient:
    def __init__(
        self,
        username=None,
        password=None,
        session=None
    ):
        self.host = "https://www.calpads.org/"
        self.timeout = 30
        self.username = username
        self.password = password
        self.credentials = {
            "Username": self.username,
            "Password": self.password,
        }
        self.visit_history = deque(maxlen=10)

        if session is None:
            self.session = requests.Session()
            self.session.headers.update(
                {
                    "User-Agent": (
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/70.0.3538.77 Safari/537.36"
                    )
                }
            )
        else:
            self.session = session

        if self._handle_event_hooks not in self.session.hooks["response"]:
            self.session.hooks["response"].append(self._handle_event_hooks)

        self.log = logging.getLogger(__name__)
        log_fmt = (
            f"%(levelname)s: %(asctime)s {self.__class__.__name__}.%(funcName)s: %(message)s"
        )
        logging.basicConfig(format=log_fmt, level=logging.INFO)

        self.__connection_status = False
        if session is None:
            try:
                self.__connection_status = self._login()
            except RecursionError:
                self.log.info(
                    "Looks like the provided credentials might be incorrect. Confirm credentials."
                )
    def _get(self, url, **kwargs):
        kwargs.setdefault("timeout", self.timeout)
        return self.session.get(url, **kwargs)

    def _post(self, url, **kwargs):
        kwargs.setdefault("timeout", self.timeout)
        return self.session.post(url, **kwargs)

    @property
    def is_connected(self):
        """User exposed attribute to check whether the client successfully connected."""
        return self.__connection_status

    def validate_session(self):
        """Best-effort check that the current session is authenticated."""
        response = self._get(urljoin(self.host, "Extract"), allow_redirects=True)
        text = response.text.lower()
        good_markers = [
            "extract home",
            "realtime extracts",
            "/extract/odsextract",
        ]
        bad_markers = [
            "interim dual login page",
            "identity.calpads.org",
            "forgot new username?",
            "login/openidconnect",
            "login/azureopenid",
        ]
        return (
            response.status_code == 200
            and any(marker in text for marker in good_markers)
            and not any(marker in text for marker in bad_markers)
        )

    def get_leas(self):
        response = self._get(urljoin(self.host, "Leas?format=JSON"))
        return safe_json_load(response)

    def get_all_schools(self, lea_code):
        response = self._get(urljoin(self.host, f"/SchoolListingAll?lea={lea_code}&format=JSON"))
        return safe_json_load(response)

    def get_submitter_names(self, lea_code):
        response = self._get(urljoin(self.host, f"/GetSubmitterNames?leaCdsCode={lea_code}&format=JSON"))
        return safe_json_load(response)

    def get_user_orgs(self, lea_code, email):
        self._select_lea(lea_code)
        response = self._get(urljoin(self.host, f"/GetUserOrgs/{email}?format=JSON"))
        if response.status_code == 200:
            return safe_json_load(response)
        return {"Data": [], "Total Count": 0}

    def get_homepage_important_messages(self):
        response = self._get(
            urljoin(self.host, "/HomepageImportantMessages?format=JSON&skip=0&take=5&undefined=0")
        )
        return safe_json_load(response)

    def get_homepage_anomaly_status(self):
        response = self._get(urljoin(self.host, "/HomepageAnomalyStatus?format=JSON"))
        return safe_json_load(response)

    def get_homepage_certification_status(self):
        response = self._get(urljoin(self.host, "/HomepageCertificationStatus?format=JSON"))
        return safe_json_load(response)

    def get_homepage_submission_status(self):
        response = self._get(urljoin(self.host, "/HomepageSubmissions?format=JSON"))
        return safe_json_load(response)

    def get_homepage_extract_status(self):
        response = self._get(urljoin(self.host, "/HomepageNotifications?format=JSON"))
        return safe_json_load(response)

    def get_enrollment_history(self, ssid):
        response = self._get(urljoin(self.host, f"/Student/{ssid}/Enrollment?format=JSON"))
        return safe_json_load(response)

    def get_demographics_history(self, ssid):
        response = self._get(urljoin(self.host, f"/Student/{ssid}/Demographics?format=JSON"))
        return safe_json_load(response)

    def get_address_history(self, ssid):
        response = self._get(urljoin(self.host, f"/Student/{ssid}/Address?format=JSON"))
        return safe_json_load(response)

    def get_elas_history(self, ssid):
        response = self._get(urljoin(self.host, f"/Student/{ssid}/EnglishLanguageAcquisition?format=JSON"))
        return safe_json_load(response)

    def get_program_history(self, ssid):
        response = self._get(urljoin(self.host, f"/Student/{ssid}/Program?format=JSON"))
        return safe_json_load(response)

    def get_student_course_section_history(self, ssid):
        response = self._get(urljoin(self.host, f"/Student/{ssid}/StudentCourseSection?format=JSON"))
        return safe_json_load(response)

    def get_cte_history(self, ssid):
        response = self._get(urljoin(self.host, f"/Student/{ssid}/CareerTechnicalEducation?format=JSON"))
        return safe_json_load(response)

    def get_stas_history(self, ssid):
        response = self._get(urljoin(self.host, f"/Student/{ssid}/StudentAbsenceSummary?format=JSON"))
        return safe_json_load(response)

    def get_sirs_history(self, ssid):
        response = self._get(urljoin(self.host, f"/Student/{ssid}/StudentIncidentResult?format=JSON"))
        return safe_json_load(response)

    def get_soff_history(self, ssid):
        response = self._get(urljoin(self.host, f"/Student/{ssid}/Offense?format=JSON"))
        return safe_json_load(response)

    def get_assessment_history(self, ssid):
        response = self._get(urljoin(self.host, f"/Student/{ssid}/Assessment?format=JSON"))
        return safe_json_load(response)

    def get_sped_history(self, ssid):
        response = self._get(urljoin(self.host, f"/Student/{ssid}/SPED?format=JSON"))
        return safe_json_load(response)

    def get_serv_history(self, ssid):
        response = self._get(urljoin(self.host, f"/Student/{ssid}/SERV?format=JSON"))
        return safe_json_load(response)

    def get_swds_history(self, ssid):
        response = self._get(urljoin(self.host, f"/Student/{ssid}/SWDS?format=JSON"))
        return safe_json_load(response)

    def get_ssrv_history(self, ssid):
        response = self._get(urljoin(self.host, f"/Student/{ssid}/SSRV?format=JSON"))
        return safe_json_load(response)

    def get_meet_history(self, ssid):
        response = self._get(urljoin(self.host, f"/Student/{ssid}/MEET?format=JSON"))
        return safe_json_load(response)

    def get_psts_history(self, ssid):
        response = self._get(urljoin(self.host, f"/Student/{ssid}/PSTS?format=JSON"))
        return safe_json_load(response)

    def get_plan_history(self, ssid):
        response = self._get(urljoin(self.host, f"/Student/{ssid}/PLAN?format=JSON"))
        return safe_json_load(response)

    def get_plan_record_details(self, ssid, plan_key):
        self._get(urljoin(self.host, f"Student/{ssid}/PLAN/{plan_key}"))
        root = etree.fromstring(self.visit_history[-1].text, etree.HTMLParser())
        return {
            "GeneralEducationParticipationPercentage": self._get_input_value(
                root, "GeneralEducationParticipationPercentage"
            ),
            "SpecialTransportationIndicator": self._get_radio_value(
                root, "SpecialTransportationIndicator"
            ),
        }

    def get_requested_extracts(self, lea_code):
        """Returns a dictionary object with the a list of extracts at the provided lea_code
        Args:
            lea_code (str): string of the seven digit number found next to your LEA name in the org select menu. For most LEAs,
                this is the CD part of the County-District-School (CDS) code. For independently reporting charters, it's the S.
        Returns:
            a JSON object with a Data key and a total record count key (the name of this key can vary)
            Expected data is under Data as a List where each item is a "row" of data
        """
        response = self._get(urljoin(self.host, f"/Extract?SelectedLEA={lea_code}&format=JSON"))
        return safe_json_load(response)

    def get_staff_demographics_history(self, seid):
        response = self._get(urljoin(self.host, f"/Staff/{seid}/StaffDemographics?format=JSON"))
        return safe_json_load(response)

    def get_staff_assignments_history(self, seid):
        response = self._get(urljoin(self.host, f"/Staff/{seid}/StaffAssignments?format=JSON"))
        return safe_json_load(response)

    def get_staff_courses_history(self, seid):
        response = self._get(urljoin(self.host, f"/Staff/{seid}/StaffCourses?format=JSON"))
        return safe_json_load(response)

    def download_report(
        self,
        lea_code,
        report_code,
        file_name=None,
        is_snapshot=False,
        download_format="CSV",
        form_data=None,
        dry_run=False,
        url_override=None,
    ):
        if not REPORTS_DL_FORMAT.get(download_format.upper()):
            self.log.info(
                "%s is not a supported reports download format. Try: %s",
                download_format,
                " ".join(REPORTS_DL_FORMAT.keys()),
            )
            raise Exception("Bad download format")

        if not file_name:
            file_name = "data"

        self._select_lea(lea_code)
        report_url = url_override or self._get_report_link(report_code.lower(), is_snapshot)
        if not report_url:
            raise Exception("Report Not Found")

        self._get(report_url)
        report_page_root = etree.fromstring(
            self.visit_history[-1].text,
            parser=etree.HTMLParser(encoding="utf8"),
        )
        iframe_url = report_page_root.xpath(
            "//iframe[@src and not(contains(@src, 'KeepAlive'))]"
        )[0].attrib["src"]
        self._get(iframe_url)

        form = ReportsForm(self.visit_history[-1].text)
        if dry_run:
            return form.filtered_parse

        if form_data:
            formatted_form_data = form.get_final_form_data(form_data)
        else:
            self.log.warning(
                "Most report forms require at least some input, especially for Select form fields."
            )
            formatted_form_data = form.get_final_form_data({})

        submitted_form_data = {k: v for k, v in formatted_form_data.items() if v != ""}
        self._post(self.visit_history[-1].url, data=submitted_form_data)

        regex = re.compile(r'(?<="ExportUrlBase":")[^"]+(?=")')
        split_query = None
        if regex.search(self.visit_history[-1].text):
            export_url_base = regex.search(self.visit_history[-1].text).group(0)
            scheme, netloc, path, query, frag = urlsplit(
                urljoin("https://reports.calpads.org", export_url_base)
                .replace("\\u0026", "&")
                .replace("%3a", ":")
                .replace("%2f", "/")
            )
            split_query = parse_qsl(query)

        print(split_query, flush=True)
        print(form_data, flush=True)
        print(formatted_form_data, flush=True)

        if split_query:
            split_query.append(("Format", REPORTS_DL_FORMAT[download_format.upper()]))
            report_dl_url = urlunsplit([scheme, netloc, path, urlencode(split_query), frag])
            self._get(report_dl_url)
            with open(file_name, "wb") as file_handle:
                file_handle.write(self.visit_history[-1].content)
            return True

        self.log.info("Failed to download the report.")
        return False

    def request_extract(self, lea_code, extract_name, form_data=None, by_date_range=False,
                        by_as_of_date=False, dry_run=False):
        """
        Request an extract with the extract_name from CALPADS.
        For Direct Certification Extract, pass in extract_name='DirectCertification'.
        For DSEA Extract, pass in extract_name='DSEAExtract'
        For the others, use their abbreviated acronym, e.g. SENR, SELA, etc.
        When dry_run is true, this returns a dict with suggestions for form_data inputs. The keys are the keys,
        the values are options for valid values. If the value is str, then any string is allowed. Date parameters
        will provide a value with formatting instructions (namely, MM/DD/YYYY). Select fields have dict values in
        the form of: {'FieldName': {'_allows_multiple': True, 'val1': 'internal_val'}. The expected input should
        look like form_data = [('FieldName', 'internal_val')], that is take the key of dict, and the value of the
        nested dict. 'val1' is the value dispalyed in the UI. If '_allows_multiple' is False, then only one of those
        field keys should be sent in the request. If '_allows_multiple' is True, then the key can have multiple values.
        A common example is schools: [('School', '0000001'), ('School', '0000002')] for NPS and Private schools.
        Args:
            lea_code (str): string of the seven digit number found next to your LEA name in the org select menu. For most LEAs,
                this is the CD part of the County-District-School (CDS) code. For independently reporting charters, it's the S.
            extract_name (str): generally the four letter acronym of the extract. e.g. SENR, SELA, etc.
                For Direct Certification Extract, pass in extract_name='DirectCertification'.
                Spelling matters, capitalization does not. Silently fails if report name is unrecognized/not supported.
            form_data (list of iterables, optional): a list of the (key, value) pairs to send in the POST request body. To know
                which keys and values are expected, set dry_run=True. Technically optional, but will silently fail if
                a required key is missing.
            by_date_range (bool, optional): some extracts can be requested with a date range parameter.
                Set to True to use date range.
            by_as_of_date (bool, optional): used only in CENR to fill out the As of Date form. If by_date_range is True,
                this is ignored.
            dry_run (bool): when False, it downloads the report. When True, it doesn't download the report and instead
                returns a dict with the form fields and their expected inputs.
        Returns:
            bool: True if extract request was successful, False if it was not successful.
            dict: when dry_run=True, it returns a dict of the form fields and their expected inputs for report manipulation
        """
        extract_name = extract_name.upper()
        if not form_data:
            form_data = list()
        with self.session as session:
            self._select_lea(lea_code)
            self._get(self._get_extract_request_url(extract_name))
            root = etree.fromstring(self.visit_history[-1].text, etree.HTMLParser(encoding='utf8'))

            #In the past, for SPED and SSRV extracts, CALPADS showed SELPA and NonSELPA form options.
            #They have either removed or only show by permission levels, so we won't add that extra layer, for now.
            if by_date_range:
                try:
                    if extract_name != 'CENR':
                        chosen_form = root.xpath('//form[contains(@action, "Extract") and contains(@action, "Date")]')[0]
                    else:
                        chosen_form = root.xpath('//form[contains(@action, "Extract") and contains(@action, "DateRange")]')[0]
                except IndexError:
                    self.log.info("There is no By Date Range request option. Falling back to the default form option.")
                    chosen_form = root.xpath('//form[contains(@action, "Extract") and not(contains(@action, "Date"))]')[0]
            elif extract_name == 'CENR' and by_as_of_date:
                chosen_form = root.xpath('//form[contains(@action, "Extract") and contains(@action, "AsofDate")]')[0]
            else:
                chosen_form = root.xpath('//form[contains(@action, "Extract") and not(contains(@action, "Date"))]')[0]

            extracts_form = ExtractsForm(chosen_form)
            if dry_run:
                return extracts_form.get_parsed_form_fields()

            default_filled_fields = extracts_form.prefilled_fields.copy() #Safe to do shallow copy; list contents are immutable
            # print('default_filled_fields:', default_filled_fields)

            # Remove any tuples in the default_filled_fields whose keys appear in the user-provided form_data list
            if form_data is not None and dry_run == False:
                keys_in_form_data = {key for key, _ in form_data}
                keys_in_form_data.add('ReportingLEA') # This will be added below based on lea_code
                # print('keys_in_form_data:', keys_in_form_data)
                filtered_filled_fields = [item for item in default_filled_fields if item[0] not in keys_in_form_data]
                # print('filtered_filled_fields:', filtered_filled_fields)
            else:
                filtered_filled_fields = default_filled_fields

            filtered_filled_fields.extend(form_data + [('ReportingLEA', lea_code)])
            filled_fields = filtered_filled_fields

            # Text inputs are not able to submit multiple key values, particularly a problem for Date Range
            filled_fields = extracts_form._filter_text_input_fields(filled_fields)
            #self.log.debug('The submitted form data: {}'.format(filled_fields))
            if extract_name in ['REJECTEDRECORDS', 'CANDIDATELIST',
                                'SPEDDISCREPANCYEXTRACT', 'SSID']:
                check_submitter = [field for field in filled_fields if field[0] == 'Submitter' and field[1] is not None]
                if not check_submitter:
                    #If no submitter field is provided, default to the current user
                    filled_fields.extend([('Submitter', self._get_submitter_id(lea_code, self.username))])
                check_jobid = [field for field in filled_fields if field[0] == 'JobID' and field[1] is not None]
                if not check_jobid:
                    #If no jobid is provided, default to the latest job's job id
                    filled_fields.extend([('JobID', self.get_homepage_submission_status().get('Data')[-1]['JobID'])])

            # print('filled_fields:', filled_fields)

            #self.log.debug('Posting extract request to: {}'.format(urljoin(self.host, chosen_form.attrib['action'])))
            session.post(urljoin(self.host, chosen_form.attrib['action']),
                         data=filled_fields)
            self.log.info("Attempted to request the extract.")
            success_text = 'Extract request made successfully.  Please check back later for download.'
            request_response = etree.fromstring(self.visit_history[-1].text, parser=etree.HTMLParser(encoding='utf8'))
            try:
                #self.log.debug(request_response.xpath('//p')[0].text)
                success = (success_text == request_response.xpath('//p')[0].text)
            except IndexError:
                #self.log.debug('Was not able to find a paragraph tag')
                success = False

            return success

    def download_extract(
        self,
        lea_code,
        file_name=None,
        timeout=60,
        poll=30,
        return_bytes=True
    ):
        #TODO: Check also for type and download date, all that good stuff
        with self.session as session:
            self._select_lea(lea_code)
            time_start = time.time()
            extract_request_id = None
            
            while (time.time() - time_start) < timeout:
                result = self.get_requested_extracts(lea_code).get('Data')
                self.log.debug(result)
                print(result)
                
                #Currently only pulling the first result to check against, assuming it's the latest
                if result[0]['ExtractStatus'] == 'Complete':
                    extract_request_id = result[0]['ExtractRequestID']
                    self.log.info("Found an extract request ID")
                    break
               
                time.sleep(poll)

            if extract_request_id and not return_bytes:
                with open(file_name, 'wb') as f:
                    f.write(self._get_extract_bytes(extract_request_id))
                    return True
            elif extract_request_id and return_bytes:
                return self._get_extract_bytes(extract_request_id)
            else:
                self.log.info("Download request timed out. The download might have taken too long.")
                return False

    def upload_file(self, lea_code, file_path=None, form_data=None, dry_run=False):
        if not dry_run:
            assert file_path and form_data, "File Path and Form Data are required inputs."

        self._select_lea(lea_code)
        self._get("https://www.calpads.org/FileSubmission/FileUpload")
        root = etree.fromstring(self.visit_history[-1].text, etree.HTMLParser(encoding="utf8"))
        root_form = root.xpath("//div[@id='fileUpload']//form")[0]
        upload_form = FilesUploadForm(root_form)
        if dry_run:
            return upload_form.get_parsed_form_fields()

        prefilled_form = upload_form.prefilled_fields.copy()
        prefilled_form.extend(form_data)
        prefilled_dict = dict(prefilled_form)
        cleaned_filled_form = {k: v for k, v in prefilled_dict.items() if v != "" and v is not None}
        with open(file_path, "rb") as file_handle:
            file_input = {"FilesUploaded[0].FileName": file_handle}
            self._post(
                urljoin(self.visit_history[-1].url, root_form.attrib["action"]),
                files=file_input,
                data=cleaned_filled_form,
            )
            self.log.info("Attempted to upload the file.")

        response = etree.fromstring(self.visit_history[-1].text, etree.HTMLParser(encoding="utf8"))
        return bool(response.xpath('//*[contains(@class, "alert alert-success")]'))

    def post_file(
        self,
        lea_code,
        ignore_rejections=False,
        get_errors=False,
        submitter_email=None,
        timeout=180,
        poll=30,
    ):
        if poll < 10:
            poll = 10
        errors = b""

        self._select_lea(lea_code)
        start_time = time.time()
        while (time.time() - start_time) < timeout:
            submissions = self.get_homepage_submission_status().get("Data") or []
            if not submissions:
                time.sleep(poll)
                continue

            get_job_status = submissions[-1]
            if get_job_status["SubmissionStatus"] == "Ready for Review":
                if get_job_status["Rejected"] == "0":
                    self._get(f"https://www.calpads.org/FileSubmission/Detail/{get_job_status['JobID']}")
                    if self._post_file_post_action().xpath('//*[contains(@class, "alert alert-success")]'):
                        self.log.info("Successfully posted the file.")
                        return True, errors
                    self.log.info("Attempted and failed to post the file.")
                    return False, errors

                if ignore_rejections:
                    self.log.info("There were rejections, but ignoring those rejections.")
                    if get_errors:
                        errors = self._get_file_submission_rejections(
                            lea_code,
                            get_job_status["FileTypeCode"] + "ERR",
                            submitter_email,
                            get_job_status["JobID"],
                            timeout,
                            poll,
                        )
                    self._get(f"https://www.calpads.org/FileSubmission/Detail/{get_job_status['JobID']}")
                    if self._post_file_post_action().xpath('//*[contains(@class, "alert alert-success")]'):
                        self.log.info("Successfully posted the file.")
                        return True, errors
                    self.log.info("Attempted and failed to post the file.")
                    return False, errors

                if get_errors:
                    errors = self._get_file_submission_rejections(
                        lea_code,
                        get_job_status["FileTypeCode"] + "ERR",
                        submitter_email,
                        get_job_status["JobID"],
                        timeout,
                        poll,
                    )
                self.log.info("Unable to post the latest job because some records were rejected")
                return False, errors

            time.sleep(poll)

        self.log.info("Unable to post the latest job, timed out.")
        return False, errors

    def _get_file_submission_rejections(self, lea_code, record_type, submitter_email, job_id, timeout, poll):
        self.log.info("Attempting to fetch the latest submission's rejected records.")
        submitter_id = self._get_submitter_id(lea_code, submitter_email) if submitter_email else None
        submitted_fields = [
            ("LEA", lea_code),
            ("RecordType", record_type),
            ("JobID", job_id),
            ("Submitter", submitter_id),
            ("School", "All"),
        ]
        success = self.request_extract(lea_code, "REJECTEDRECORDS", submitted_fields)
        if success:
            self.log.info("Successfully requested the rejected records. Attempting download.")
            return (
                self.download_extract(
                    lea_code,
                    timeout=timeout,
                    poll=poll,
                    return_bytes=True,
                    extract_name="REJECTEDRECORDS",
                )
                or b"Failed downloading extract errors"
            )
        self.log.info("Failed to request the rejected records.")
        return b"Failed requesting extract errors"

    def _get_submitter_id(self, lea_code, submitter_email):
        submitter_names = self.get_submitter_names(lea_code)
        try:
            return [
                submitter["Value"]
                for submitter in submitter_names
                if submitter["Text"] == submitter_email
            ][0]
        except IndexError:
            self.log.debug(
                "Could not find the id for the submitter email; will use the email as is."
            )
            return submitter_email

    def _post_file_post_action(self):
        root = etree.fromstring(self.visit_history[-1].text, etree.HTMLParser(encoding="utf8"))
        form_root = root.xpath('//form[@action="/FileSubmission/Post"]')[0]
        inputs = FilesUploadForm(form_root).prefilled_fields + [("command", "Post All")]
        input_dict = dict(inputs)
        self._post(urljoin(self.host, "/FileSubmission/Post"), data=input_dict)
        self.log.info("Attempted to post all for this submission job.")
        return etree.fromstring(self.visit_history[-1].text, etree.HTMLParser(encoding="utf8"))

    def _get_extract_bytes(self, extract_request_id):
        self._get(urljoin(self.host, f"/Extract/DownloadLink?ExtractRequestID={extract_request_id}"))
        return self.visit_history[-1].content

    def _select_lea(self, lea_code):
        with self.session as session:
            session.get(self.host)
            page_root = etree.fromstring(self.visit_history[-1].text, parser=etree.HTMLParser(encoding='utf8'))
            orgchange_form = page_root.xpath("//form[contains(@action, 'UserOrgChange')]")[0]
            try:
                org_form_val = (orgchange_form
                                .xpath("//select/option[contains(text(), '{}')]".format(lea_code))[0]
                                .attrib.get('value'))
            except IndexError:
                self.log.info("The provided lea_code, {}, does not appear to exist for you."
                              .format(lea_code))
                raise Exception("Unable to switch to the provided LEA Code")

            request_token = orgchange_form.xpath("//input[@name='__RequestVerificationToken']")[0].get('value')

            session.post(urljoin(self.host, orgchange_form.attrib['action']),
                         data={'selectedItem': org_form_val,
                               '__RequestVerificationToken': request_token})

    def _get_report_link(self, report_code, is_snapshot=False):
        candidate_paths = (
            ["/Report/Certification", "/Report/Snapshot"]
            if is_snapshot
            else ["/Report/Realtime", "/Report/ODS"]
        )

        for candidate_path in candidate_paths:
            self._get(urljoin(self.host, candidate_path))
            response = self.visit_history[-1]
            if response.status_code != 200:
                continue

            if report_code == "8.1eoy3" and is_snapshot:
                return "https://www.calpads.org/Report/Snapshot/8_1_StudentProfileList_EOY3_"

            root = etree.fromstring(response.text, parser=etree.HTMLParser(encoding="utf8"))
            elements = root.xpath("//*[@class='num-wrap-in']")
            for element in elements:
                if element.text and report_code == element.text.lower():
                    return urljoin(self.host, element.xpath("./../../a")[0].attrib["href"])

        self.log.info("Failed to find the provided report code.")
        return None

    def _get_extract_request_url(self, extract_name):
        special_urls = {
            "SSID": "https://www.calpads.org/Extract/SSIDExtract",
            "DIRECTCERTIFICATION": "https://www.calpads.org/Extract/DirectCertificationExtract",
            "REJECTEDRECORDS": "https://www.calpads.org/Extract/RejectedRecords",
            "CANDIDATELIST": "https://www.calpads.org/Extract/CandidateList",
            "REPLACEMENTSSID": "https://www.calpads.org/Extract/ReplacementSSID",
            "SPEDDISCREPANCYEXTRACT": "https://www.calpads.org/Extract/SPEDDiscrepancyExtract",
            "DSEAEXTRACT": "https://www.calpads.org/Extract/DSEAExtract",
        }
        return special_urls.get(
            extract_name,
            f"https://www.calpads.org/Extract/ODSExtract?RecordType={extract_name}",
        )

    def _find_completed_extract_request_id(self, extracts, extract_name):
        target = extract_name.upper() if extract_name else None

        for extract in reversed(extracts):
            print(f"Checking extract: {extract}")

            status = str(extract.get("ExtractStatus", "")).strip().upper()
            
            if status != "COMPLETE":
                continue

            if target is not None:
                extract_text = " ".join(
                    str(value).upper()
                    for value in extract.values()
                    if value is not None
                )

                if target not in extract_text:
                    print(f"Complete extract found, but did not match target={target}")
                    continue

            return extract.get("ExtractRequestID")
        return None

    def _get_input_value(self, root, input_id):
        nodes = root.xpath(f"//input[@id='{input_id}']")
        return nodes[0].get("value") if nodes else None

    def _get_radio_value(self, root, radio_name):
        nodes = root.xpath(
            f"//input[@type='radio' and @name='{radio_name}' and @checked]"
        )
        return nodes[0].get("value") if nodes else None

    def _handle_event_hooks(self, response, *args, **kwargs):
        self.log.debug(
            "Response STATUS CODE: %s\nChecking hooks for:\n%s\n",
            response.status_code,
            response.url,
        )
        _, _, path, _, _ = urlsplit(response.url)
        normalized_path = path.lower()

        if normalized_path in {"/account/login", "/login"} and response.status_code == 200:
            self.log.debug("Handling login page")
            self.session.cookies.update(response.cookies.get_dict())
            root = etree.fromstring(response.text, parser=etree.HTMLParser(encoding="utf8"))
            forms = root.xpath("//form")
            for form in forms:
                form_inputs = {
                    input_.attrib.get("name"): input_.attrib.get("value", "")
                    for input_ in form.xpath(".//input[@name]")
                    if input_.attrib.get("name")
                }
                action_url = form.attrib.get("action", "")
                lower_action = action_url.lower()

                has_username = any(key.lower() == "username" for key in form_inputs)
                has_password = any(key.lower() == "password" for key in form_inputs)

                if has_username and has_password:
                    username_key = next(
                        key for key in form_inputs if key and key.lower() == "username"
                    )
                    password_key = next(
                        key for key in form_inputs if key and key.lower() == "password"
                    )
                    form_inputs[username_key] = self.username
                    form_inputs[password_key] = self.password
                    if any(key.lower() == "agreementconfirmed" for key in form_inputs):
                        agreement_key = next(
                            key
                            for key in form_inputs
                            if key and key.lower() == "agreementconfirmed"
                        )
                        form_inputs[agreement_key] = "True"

                    self._post(urljoin(response.url, action_url or response.url), data=form_inputs)
                    return response

                if "/login/openidconnect" in lower_action or "/login/azureopenid" in lower_action:
                    self._post(urljoin(response.url, action_url), data=form_inputs)
                    return response

            openid_targets = []
            for anchor in root.xpath("//a[@href]"):
                href = anchor.attrib.get("href", "")
                lower_href = href.lower()
                anchor_text = " ".join(text.strip() for text in anchor.xpath(".//text()") if text.strip()).lower()
                if (
                    "/login/openidconnect" in lower_href
                    or "/login/azureopenid" in lower_href
                    or "cde" in anchor_text
                    or "single sign-on" in anchor_text
                    or "sign in" in anchor_text
                ):
                    openid_targets.append(href)

            if not openid_targets:
                script_matches = re.findall(
                    r'(?i)(/login/(?:openidconnect|azureopenid)[^"\']*)',
                    response.text,
                )
                openid_targets.extend(script_matches)

            if openid_targets:
                self._get(urljoin(response.url, openid_targets[0]))
                return response

            self.log.warning("Login page detected, but no recognizable login action was found.")

        if normalized_path in ["/connect/authorize/callback", "/connect/authorize"] and response.status_code == 200:
            self.log.debug("Handling /connect/authorize/callback")
            self.session.cookies.update(response.cookies.get_dict())
            login_root = etree.fromstring(response.text, parser=etree.HTMLParser(encoding="utf8"))
            openid_form_data = {
                input_.attrib.get("name"): input_.attrib.get("value")
                for input_ in login_root.xpath("//input")
            }
            action_url = login_root.xpath("//form")[0].attrib.get("action")
            scheme, netloc, _, _, _ = urlsplit(action_url)
            if not scheme and not netloc:
                self._post(urljoin(self.host, action_url), data=openid_form_data)
            else:
                self._post(action_url, data=openid_form_data)
            return response

        self.visit_history.append(response)
        return response


def safe_json_load(response):
    try:
        return json.loads(response.content)
    except JSONDecodeError:
        return {}