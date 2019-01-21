import unittest
import miniscan

M = miniscan.META
P = miniscan.PRELOAD['ASCII']

class TestBootstrap(unittest.TestCase):
	def test_00_smoke_test(self):
		self.assertEqual([], list(M.scan('')))
		self.assertEqual(1, len(list(M.scan("a"))))
		M.get_dfa().stats()
		
	def test_01_simple_tokens_with_rank_feature(self):
		s = miniscan.Definition()
		s.on('\s+')(None) # Ignore spaces except inasmuch as they separate tokens.
		s.on('\w+')('word') # The digits are included in the \w shorthand,
		@s.on('\d+', rank=1) # but the higher rank (than default zero) makes numbers stand out.
		def number(scanner): return 'number', int(scanner.matched_text())
		
		self.assertEqual(
			[('word', 'abc'), ('number', 123), ('word', 'def456'), ('number', 789), ('word', 'XYZ')],
			list(s.scan(' abc   123  def456  789XYZ ')),
		)
		
