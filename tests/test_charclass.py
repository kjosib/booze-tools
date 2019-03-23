import unittest
from boozetools import charset


class TestCharClass(unittest.TestCase):
	def setUp(self):
		self.a = charset.singleton(ord('a'))
		self.digit = charset.range_class(ord('0'), ord('9'))
		self.upper = charset.range_class(ord('A'), ord('Z'))
		self.lower = charset.range_class(ord('a'), ord('z'))
	
	def check(self, cls, members, nonmembers):
		for c in members:
			with self.subTest(c=c): self.assertTrue(charset.in_class(cls, ord(c)))
		for c in nonmembers:
			with self.subTest(c=c): self.assertFalse(charset.in_class(cls, ord(c)))
	
	def test_00_singleton(self): self.check(self.a, 'a', 'Ab')
	
	def test_01_range_class(self): self.check(self.digit, '059', 'A b\0')
	
	def test_02_universal_and_eof(self):
		assert charset.in_class(charset.UNIVERSAL, 0)
		assert charset.in_class(charset.UNIVERSAL, 99)
		assert charset.in_class(charset.UNIVERSAL, 9999)
		assert charset.in_class(charset.UNIVERSAL, 999999)
		assert not charset.in_class(charset.UNIVERSAL, -1)
		
		assert not charset.in_class(charset.EOF, -2)
		assert charset.in_class(charset.EOF, -1)
		assert not charset.in_class(charset.EOF, 0)
		assert not charset.in_class(charset.EOF, 99)
		assert not charset.in_class(charset.EOF, 9999)
		assert not charset.in_class(charset.EOF, 999999)
		
	def test_03_complement(self):
		self.check(charset.complement(self.digit), 'A b\0', '059')
		
		assert charset.complement(charset.UNIVERSAL) == charset.EMPTY # Match nothing
		assert charset.complement(charset.EMPTY) == charset.UNIVERSAL # Match nothing
		assert charset.complement(charset.EOF) == charset.UNIVERSAL # Yes, this is asymmetrical.
	
	def test_04_expand(self):
		it = list(charset.expand(self.upper, [48, 64, 65, 66, 89, 90, 91, 92]))
		self.assertEqual([0, 0, 1, 1, 1, 1, 0, 0], it)
	
	def test_05_union(self):
		alpha = charset.union(self.upper, self.lower)
		self.check(alpha, 'ABCXYZabcxyz', '059@_\0')
		