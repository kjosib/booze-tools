import unittest
from boozetools.support import interfaces
from boozetools.scanning import regular, miniscan, charset

M = miniscan.META
P = miniscan.PRELOAD['ASCII']

class TestBootstrap(unittest.TestCase):
	def test_00_smoke_test(self):
		self.assertEqual([], list(M.scan('')))
		self.assertEqual(1, len(list(M.scan("a"))))
		M.get_dfa().stats()
	
	def test_01_confusing_charclass(self):
		ce = regular.ClassEncoder(P)
		for spec, inside, outside in [
			(r'[-x]', '-x', 'Aa'), # contains minus
			(r'[^]^abc]', 'xX\n', '^]abc'), # negates; contains close-bracket
			(r'[^-]^abc]', 'xX\n', '-]^abc'), # contains both tricky characters
		]:
			with self.subTest(spec=spec):
				tokens = list(M.scan(spec))
				k = ce.visit(miniscan.rex.parse(tokens, language='Regular'))
				for c in inside: assert charset.in_class(k, ord(c))
				for c in outside: assert not charset.in_class(k, ord(c))

class TestMiniScan(unittest.TestCase):
	def test_01_simple_tokens_with_rank_feature(self):
		s = miniscan.Definition()
		s.ignore('\s+') # Ignore spaces except inasmuch as they separate tokens.
		s.token('word', '\w+') # The digits are included in the \w shorthand,
		s.token_map('number', '\d+', int, rank=1) # but the higher rank (than default zero) makes numbers stand out.
		
		self.assertEqual(
			[
				('word', 'abc'),
				('number', 123),
				('word', 'def456'),
				('number', 789),
				('word', 'XYZ'),
			],
			list(s.scan(' abc   123  def456  789XYZ ')),
		)
	
	def semantics(self, expect, s, text):
		found = [token[1] for token in s.scan(text)]
		self.assertEqual(expect, found)
	
	def test_03_begin_anchor(self):
		s = miniscan.Definition()
		s.token('word', '^\w+') # Yield only those words found at the beginning of lines.
		s.ignore('[\s\S]') # Skip all other characters, one character at a time.
		expect = ['apple', 'animal']
		self.semantics(expect, s, 'apple banana orange\nanimal vegetable mineral') # Unix-style
		self.semantics(expect, s, 'apple banana orange\ranimal vegetable mineral') # Apple-Classic Style
		self.semantics(expect, s, 'apple banana orange\r\nanimal vegetable mineral') # Dos-style
	
	def test_04_non_begin_anchor(self):
		s = miniscan.Definition()
		s.token('word', '^^\w+') # Yield only those words found NOT at the beginning of lines.
		s.ignore('\s+') # Skip spaces
		s.ignore('\S+') # Skip other sequences of non-spaces.
		self.semantics(['banana', 'orange', 'vegetable', 'mineral'], s, 'apple banana orange\nanimal vegetable mineral')
	
	def test_05_eol_anchor(self):
		s = miniscan.Definition()
		s.token('work', '\w+$') # Yield only those words found at the ends of lines.
		# Note that the end-of-text also counts as an end-of-line zone; this is NOT strictly looking for \n.
		s.ignore('\s+') # Skip spaces
		s.ignore('\S+') # Skip other sequences of non-spaces.
		expect = ['orange', 'mineral']
		self.semantics(expect, s, 'apple banana orange\nanimal vegetable mineral') # Unix-style
		self.semantics(expect, s, 'apple banana orange\ranimal vegetable mineral') # Apple-Classic Style
		self.semantics(expect, s, 'apple banana orange\r\nanimal vegetable mineral') # Dos-style
		
	def test_06_simple_trailing_context(self):
		s = miniscan.Definition()
		s.token('stem', '\w+/ing') # Yield the stems of gerunds. Sort of. "Thing" is not a gerund.
		s.ignore('\w+') # Skip words not matched above
		s.ignore('\s+') # Skip spaces
		s.ignore('\S') # Skip non-spaces, one at a time.
		self.semantics(['eat', 'drink'], s, 'There was eating, drinking, and merriment all around.')
	
	def test_07_variable_trail_on_fixed_stem(self):
		s = miniscan.Definition()
		s.token('stem', 'eat/ing|en|s') # Yield the stems of eat-forms
		s.ignore('\s+') # Skip spaces
		s.ignore('\S') # Skip non-spaces, one at a time.
		self.semantics(['eat', ], s, 'There was eating, drinking, and merriment all around, but the man did not eat.')
	
	def test_08_trailing_context_gets_put_back(self):
		s = miniscan.Definition()
		s.token('stem', r'\d/\d')
		s.ignore(r'.')
		expect = list('12')
		self.semantics(expect, s, '123')
	
	def test_09_forgotten_action(self):
		s = miniscan.Definition()
		s.token('ernie', 'ernie$') # match ernie, but only at the end.
		s.on(r'bert/\s+and') # match bert, but only if " and" follows. However, forget to provide an action,
		with self.assertRaises(AssertionError):
			s.on('.') # triggering an exception at the next attempt to define a pattern.

	def test_10_charclass_intersection(self):
		""" Exercise the canonical "consonants" example. """
		s = miniscan.Definition()
		s.let('vowel', r'[AEIOUaeiou]')
		s.let('consonant', r'[{alpha}&&^{vowel}]')
		s.token('consonant', '{consonant}+')
		s.ignore('{ANY}')
		original_text = 'To sit in solemn silence on a dull dark dock,'
		result = '-'.join(t[1] for t in s.scan(original_text))
		expect = 'T-s-t-n-s-l-mn-s-l-nc-n-d-ll-d-rk-d-ck'
		self.assertEqual(expect, result)
	
	def test_11_escape_in_charclass(self):
		""" char-class should allow hex escapes. """
		s = miniscan.Definition()
		s.token('upper', r'[\x41-\x5a]')
		s.ignore(r'.')
		original_text = 'The Quick Brown Fox'
		result = '-'.join(t[1] for t in s.scan(original_text))
		expect = 'T-Q-B-F'
		self.assertEqual(expect, result)
	
