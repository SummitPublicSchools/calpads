import unittest
import os
import logging
from tempfile import TemporaryDirectory
from calpads.client import CALPADSClient

#Might explore adding colors to the output for tests
#https://stackoverflow.com/questions/384076/how-can-i-color-python-logging-output
#Currently this might only work for Linux/Unix?
# logging.addLevelName(logging.WARNING, "\033[1;31m%s\033[1;0m" % logging.getLevelName(logging.WARNING))
# logging.addLevelName(logging.DEBUG, "\033[1;41m{level_name}\033[1;0m".format(level_name=logging.getLevelName(logging.DEBUG)))


class CALPADSTest(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.cp_client = CALPADSClient(os.getenv('CALPADS_USERNAME'),
                                       os.getenv('CALPADS_PASSWORD'))

    def setUp(self):
        self.assertIsInstance(self.cp_client, CALPADSClient)
        rootlog = logging.getLogger()
        rootlog.setLevel(logging.DEBUG)
        # To focus on the calpads issues, filter for just the client log outputs
        # If you comment this out, you can see requests' and other libraries'
        # debug outputs too which will be super handy!
        rootlog.addFilter(logging.Filter('calpads.client'))

    def tearDown(self):
        self.cp_client.session.close()


class ClientTest(CALPADSTest):

    def test_successful_login(self):
        self.assertTrue(self.cp_client._login())

    def test_successful_connection(self):
        self.cp_client._login()
        self.assertTrue(self.cp_client.is_connected)

    @unittest.skip("This isn't quite ready for a unittest. Might need to remove the self.login call at instantiation")
    def test_invalid_login(self):
        self.cp_client.username = 'BAD USER'
        with self.assertRaises(RecursionError):
            self.cp_client._login()

    def test_get_leas(self):
        #Wouldn't be shocked if this fails if the specification changes on CALPADS' end
        self.assertIsInstance(self.cp_client.get_leas(), list)

    def test_get_elas_history(self):
        self.assertIsInstance(self.cp_client.get_elas_history(1), dict)

    def test_get_enrollment_history(self):
        self.assertIsInstance(self.cp_client.get_enrollment_history(1), dict)

    def test_get_demographics_history(self):
        self.assertIsInstance(self.cp_client.get_elas_history(1), dict)

    def test_get_address_history(self):
        self.assertIsInstance(self.cp_client.get_address_history(1), dict)

    def test_get_program_history(self):
        self.assertIsInstance(self.cp_client.get_program_history(1), dict)

    def test_get_student_course_section_history(self):
        self.assertIsInstance(self.cp_client.get_student_course_section_history(1), dict)

    def test_get_cte_history(self):
        self.assertIsInstance(self.cp_client.get_cte_history(1), dict)

    def test_get_stas_history(self):
        self.assertIsInstance(self.cp_client.get_stas_history(1), dict)

    def test_get_sirs_history(self):
        self.assertIsInstance(self.cp_client.get_sirs_history(1), dict)

    def test_get_soff_history(self):
        self.assertIsInstance(self.cp_client.get_soff_history(1), dict)

    def test_get_sped_history(self):
        self.assertIsInstance(self.cp_client.get_sped_history(1), dict)

    def test_get_ssrv_history(self):
        self.assertIsInstance(self.cp_client.get_ssrv_history(1), dict)

    def test_get_psts_history(self):
        self.assertIsInstance(self.cp_client.get_psts_history(1), dict)

    def test_download_report_dry_run(self):
        self.assertIsInstance(self.cp_client.download_report(lea_code=os.getenv('CALPADS_TEST_LEA_CODE'),
                                                            report_code='8.1',
                                                             file_name='testing.csv',
                                                             is_snapshot=True,
                                                             dry_run=True),
                              dict)

    def test_download_snapshot_report(self):
        payload = {'AcademicYear': '2019-2020',
                   'LEA': os.getenv('CALPADS_TEST_LEA'),
                   'Status': 'Revised Uncertified',
                   }
        #TODO: Add subtests for all ODS and all Snapshot reports
        with TemporaryDirectory() as td:
            #Test that function returns True if it is successful
            self.assertTrue(self.cp_client.download_report(lea_code=os.getenv('CALPADS_TEST_LEA_CODE'),
                                                           report_code='8.1',
                                                           file_name=os.path.join(td, 'testing.csv'),
                                                           form_data=payload,
                                                           is_snapshot=True,
                                                           dry_run=False
                                                           )
                            )
            #Test that all of the bytes were written to file
            #Cautionary Tale here if the content is compressed:
            #https://stackoverflow.com/a/50825553
            self.assertTrue(len(self.cp_client.visit_history[-1].content)
                            ==
                            os.stat(os.path.join(td, 'testing.csv')).st_size
                            )

    def test_download_ods_report(self):
        payload = {'AcademicYear': '2019-2020',
                   'LEA': os.getenv('CALPADS_TEST_LEA'),
                   'Status': 'Revised Uncertified',
                   'AsOfMonth': 'May',
                   'AsOfDay': '24',
                   }
        #TODO: Add subtests for all ODS and all Snapshot reports
        with TemporaryDirectory() as td:
            #Test that function returns True if it is successful
            self.assertTrue(self.cp_client.download_report(lea_code=os.getenv('CALPADS_TEST_LEA_CODE'),
                                                           report_code='8.1',
                                                           file_name=os.path.join(td, 'testing.csv'),
                                                           form_data=payload,
                                                           is_snapshot=False,
                                                           dry_run=False
                                                           )
                            )
            #Test that all of the bytes were written to file
            #Cautionary Tale here if the content is compressed:
            #https://stackoverflow.com/a/50825553
            self.assertTrue(len(self.cp_client.visit_history[-1].content)
                            ==
                            os.stat(os.path.join(td, 'testing.csv')).st_size
                            )

    def test_request_extract_dry_run(self):
        self.assertIsInstance(self.cp_client.request_extract(lea_code=os.getenv('CALPADS_TEST_LEA_CODE'),
                                                             extract_name='SENR',
                                                             dry_run=True),
                              dict)

    def test_request_extract(self):
        payload = [('School', '0000001'), ('School', '0000002'),
                   ('EnrollmentStartDate', '02/02/2020'),
                   ('EnrollmentEndDate', '02/03/2020'),
                   ]
        self.assertTrue(self.cp_client.request_extract(lea_code=os.getenv('CALPADS_TEST_LEA_CODE'),
                                                       extract_name='SENR',
                                                       form_data=payload,
                                                       by_date_range=True
                                                       ))
    def test_download_extract(self):
        with TemporaryDirectory() as td:
            self.assertTrue(self.cp_client.download_extract(lea_code=os.getenv('CALPADS_TEST_LEA_CODE'),
                                                            file_name=os.path.join(td, 'testing.txt')))

            self.assertTrue(len(self.cp_client.visit_history[-1].content)
                            ==
                            os.stat(os.path.join(td, 'testing.txt')).st_size
                            )