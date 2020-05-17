import unittest
import os
from calpads.client import CALPADSClient

class CALPADSTest(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.cp_client = CALPADSClient(os.getenv('CALPADS_USERNAME'),
                                       os.getenv('CALPADS_PASSWORD'))

    def setUp(self):
        self.assertIsInstance(self.cp_client, CALPADSClient)

    def tearDown(self):
        self.cp_client.session.close()


class ClientTest(CALPADSClient):

    def test_successful_login(self):
        self.assertTrue(self.cp_client.login())
