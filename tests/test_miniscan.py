import unittest
import miniscan, algorithms, charclass, regular

M = miniscan.META
P = miniscan.PRELOAD['ASCII']

class TestBootstrap(unittest.TestCase):
	def test_00_smoke_test(self):
		self.assertEqual([], list(M.scan('')))
		self.assertEqual(1, len(list(M.scan("a"))))
		M.get_dfa().stats()
	
	def test_10_charclass_beginning_with_minus(self):
		result = list(M.scan(r'[-x]'))
		print(result)
		k = miniscan.rex.parse(result, language='Regular')
		assert isinstance(k, regular.CharClass)
		assert charclass.in_class(k.cls, ord('-'))
		assert charclass.in_class(k.cls, ord('x'))
		assert not charclass.in_class(k.cls, ord('a'))
		

class TestMiniScan(unittest.TestCase):
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
	
	def test_03_begin_anchor(self):
		s = miniscan.Definition()
		s.on('^\w+')(lambda scanner:scanner.matched_text()) # Yield only those words found at the beginning of lines.
		s.on('[\s\S]')(None) # Skip all other characters, one character at a time.
		expect = ['apple', 'animal']
		self.assertEqual(expect, list(s.scan('apple banana orange\nanimal vegetable mineral'))) # Unix-style
		self.assertEqual(expect, list(s.scan('apple banana orange\ranimal vegetable mineral'))) # Apple-Classic Style
		self.assertEqual(expect, list(s.scan('apple banana orange\r\nanimal vegetable mineral'))) # Dos-style
	
	def test_04_non_begin_anchor(self):
		s = miniscan.Definition()
		s.on('^^\w+')(lambda scanner:scanner.matched_text()) # Yield only those words found NOT at the beginning of lines.
		s.on('\s+')(None) # Skip spaces
		s.on('\S+')(None) # Skip other sequences of non-spaces.
		result = list(s.scan('apple banana orange\nanimal vegetable mineral'))
		self.assertEqual(['banana', 'orange', 'vegetable', 'mineral'], result)
	
	def test_05_eol_anchor(self):
		s = miniscan.Definition()
		s.on('\w+$')(lambda scanner:scanner.matched_text()) # Yield only those words found at the ends of lines.
		# Note that the end-of-text also counts as an end-of-line zone; this is NOT strictly looking for \n.
		s.on('\s+')(None) # Skip spaces
		s.on('\S+')(None) # Skip other sequences of non-spaces.
		expect = ['orange', 'mineral']
		self.assertEqual(expect, list(s.scan('apple banana orange\nanimal vegetable mineral'))) # Unix-style
		self.assertEqual(expect, list(s.scan('apple banana orange\ranimal vegetable mineral'))) # Apple-Classic Style
		self.assertEqual(expect, list(s.scan('apple banana orange\r\nanimal vegetable mineral'))) # Dos-style
		
	def test_06_simple_trailing_context(self):
		s = miniscan.Definition()
		s.on('\w+/ing')(lambda scanner:scanner.matched_text()) # Yield the stems of gerunds. Sort of. Ping!
		s.on('\w+')(None) # Skip words not matched above
		s.on('\s+')(None) # Skip spaces
		s.on('\S')(None) # Skip non-spaces, one at a time.
		result = list(s.scan('There was eating, drinking, and merriment all around.'))
		self.assertEqual(['eat', 'drink'], result)
	
	def test_07_variable_trail_on_fixed_stem(self):
		s = miniscan.Definition()
		s.on('eat/ing|en|s')(lambda scanner:scanner.matched_text()) # Yield the stems of eat-forms
		s.on('\s+')(None) # Skip spaces
		s.on('\S')(None) # Skip non-spaces, one at a time.
		result = list(s.scan('There was eating, drinking, and merriment all around, but the man did not eat.'))
		self.assertEqual(['eat', ], result)
	
	def test_08_trailing_context_gets_put_back(self):
		s = miniscan.Definition()
		s.on(r'\d/\d')(lambda scanner:scanner.matched_text())
		s.on(r'.')(None)
		result = list(s.scan('123'))
		expect = list('12')
		self.assertEqual(expect, result)
	
	def test_09_forgotten_action(self):
		s = miniscan.Definition()
		s.on('ernie$')('ernie') # match ernie, but only at the end.
		s.on(r'bert/\s+and') # match bert, but only if " and" follows. However, forget to provide an action,
		with self.assertRaises(algorithms.MetaError):
			s.on('.')(None) # triggering an exception at the next attempt to define a pattern.

	def test_10_charclass_intersection(self):
		""" Exercise the canonical "consonants" example. """
		s = miniscan.Definition()
		s.let('vowel', r'[AEIOUaeiou]')
		s.let('consonant', r'[{alpha}&&^{vowel}]')
		s.on('{consonant}+')(lambda scanner:scanner.matched_text())
		s.on('{ANY}')(None)
		original_text = 'To sit in solemn silence on a dull dark dock,'
		result = '-'.join(s.scan(original_text))
		expect = 'T-s-t-n-s-l-mn-s-l-nc-n-d-ll-d-rk-d-ck'
		self.assertEqual(expect, result)