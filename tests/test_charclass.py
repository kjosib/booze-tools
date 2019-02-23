import unittest
from boozetools import charclass


class TestCharClass(unittest.TestCase):
	def setUp(self):
		self.a = charclass.singleton(ord('a'))
		self.digit = charclass.range_class(ord('0'), ord('9'))
		self.upper = charclass.range_class(ord('A'), ord('Z'))
		self.lower = charclass.range_class(ord('a'), ord('z'))
	
	def check(self, cls, members, nonmembers):
		for c in members:
			with self.subTest(c=c): self.assertTrue(charclass.in_class(cls, ord(c)))
		for c in nonmembers:
			with self.subTest(c=c): self.assertFalse(charclass.in_class(cls, ord(c)))
	
	def test_00_singleton(self): self.check(self.a, 'a', 'Ab')
	
	def test_01_range_class(self): self.check(self.digit, '059', 'A b\0')
	
	def test_02_universal_and_eof(self):
		assert charclass.in_class(charclass.UNIVERSAL, 0)
		assert charclass.in_class(charclass.UNIVERSAL, 99)
		assert charclass.in_class(charclass.UNIVERSAL, 9999)
		assert charclass.in_class(charclass.UNIVERSAL, 999999)
		assert not charclass.in_class(charclass.UNIVERSAL, -1)
		
		assert not charclass.in_class(charclass.EOF, -2)
		assert charclass.in_class(charclass.EOF, -1)
		assert not charclass.in_class(charclass.EOF, 0)
		assert not charclass.in_class(charclass.EOF, 99)
		assert not charclass.in_class(charclass.EOF, 9999)
		assert not charclass.in_class(charclass.EOF, 999999)
		
	def test_03_complement(self):
		self.check(charclass.complement(self.digit), 'A b\0', '059')
		
		assert charclass.complement(charclass.UNIVERSAL) == charclass.EMPTY # Match nothing
		assert charclass.complement(charclass.EMPTY) == charclass.UNIVERSAL # Match nothing
		assert charclass.complement(charclass.EOF) == charclass.UNIVERSAL # Yes, this is asymmetrical.
	
	def test_04_expand(self):
		it = list(charclass.expand(self.upper, [48, 64, 65, 66, 89, 90, 91, 92]))
		self.assertEqual([0, 0, 1, 1, 1, 1, 0, 0], it)
	
	def test_05_union(self):
		alpha = charclass.union(self.upper, self.lower)
		self.check(alpha, 'ABCXYZabcxyz', '059@_\0')
		