import unittest
import os
import logging
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
        self.assertTrue(self.cp_client.login())


    def test_successful_connection(self):
        self.cp_client.login()
        self.assertTrue(self.cp_client.is_connected)

    @unittest.skip("This isn't quite ready for a unittest. Might need to remove the self.login call at instantiation")
    def test_invalid_login(self):
        self.cp_client.username = 'BAD USER'
        with self.assertRaises(RecursionError):
            self.cp_client.login()