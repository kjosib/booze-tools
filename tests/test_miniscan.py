import unittest
import miniscan

M = miniscan.META
P = miniscan.PRELOAD['ASCII']

class TestBootstrap(unittest.TestCase):
	def test_00_foo(self):
		self.assertEqual([], list(M.scan('')))
		self.assertEqual(1, len(list(M.scan("a"))))
		M.get_dfa().stats()
