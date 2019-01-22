import unittest

from example import json

class TestJson(unittest.TestCase):
	
	def test_00_smoke_test(self):
		self.assertEqual(25.2, json.parse('25.2'))
		