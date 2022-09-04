import sys

from boozetools.scanning.regular import VOCAB, ConvertLiterals, PatternError, ClassEncoder
from boozetools.scanning.charset import mode_normal, in_class
from boozetools.scanning.regular import scan_regex, REGEX_SUGAR, parse_regex, _DFA
from boozetools.scanning.interface import ScannerBlocked
from boozetools.parsing.interface import ParseError

import unittest

def scan(text):
	where = {}
	tokens = list(scan_regex(text, where))
	return tokens, where

def parse(text, language="Pattern"):
	where = {}
	try:
		tree = parse_regex(text, where, language=language)
		return tree, where
	except PatternError:
		tokens = list(scan_regex(text, where))
		print(tokens, file=sys.stderr)
		raise

class TokenizerTests(unittest.TestCase):
	"""
	This group aims to show that the rules,
	which `declare_regex_token_rules` injects into an NFA,
	have the effect of scanning sequences of regex tokens.
	A further requirement is that associated scan-actions
	perform whatever scan-condition management is necessary.
	"""
	
	def test_00_smoke_test(self):
		_DFA.stats()
	
	def test_01_happy_path(self):
		""" Things which ought to scan, do in fact scan. """
		for case, size, leaves in [
			("", 0, 0),  # Blank should be empty.
			("a", 1, 1),  # A letter should scan as one thing.
			("abc", 3, 3),  # Some letters
			("a(bc)+d", 7, 4),  # Adding punctuation
			("|(|[", 4, 0), # This is not a valid regex...
			("^f", 2, 1), # Carets are metacharacters, so we handle them specially
			("^^f", 3, 1), # There's no special recognition of double-carets.
			("f^", 2, 1), # Carets are still metacharacters here; we must parse them.
			("a[^b", 3, 2), # but [^ is a token in itself...
			(r"\d\l{dli}", 3, 3), # shorthands and names should behave properly
			("f(o o)b", 6, 4), # whitespace within parens should be ignored
			("[ z]", 3, 1),# same for char classes
			(r"( $ )$", 4, 2), # Dollar signs need to work properly
		]:
			with self.subTest(case):
				tokens, where = scan(case)
				self.assertEqual(len(tokens), size)
				self.assertSetEqual(set(s for k,s in tokens)-{None}, set(where))
				sems = {k:v for k,v in where.items() if type(k) is not object}
				self.assertEqual(len(sems), leaves, tokens)
				assert None not in where
				for kind, node in tokens:
					if node is None:
						self.assertIn(kind, REGEX_SUGAR)
					else:
						assert isinstance(node, VOCAB[kind]), node
						assert node in where
	
	def test_02_space_not_allowed_outside_parens(self):
		with self.assertRaises(ScannerBlocked):
			tokens, where = scan("foo bar")

	def test_03_dollar_is_literal_in_parens_meta_outside(self):
		tokens, where = scan("($)$")
		assert tokens[1][0] == "literal", tokens
		assert type(tokens[1][1]) is VOCAB['literal'], tokens
		assert tokens[3][0] == 'end', tokens
		assert type(tokens[3][1]) is VOCAB['end'], tokens


class ParserTests(unittest.TestCase):
	def test_00_smoke_test(self):
		spec = r"te\st"
		tree, where = parse(spec, "Regular")
		assert len(where) == 4
		assert type(tree).__name__ == "sequence"
	
	def test_01_grouping_whitespace_and_classes(self):
		for spec in (
			r'this( is a )test',
			r'[Hh]ello,\ [Ww]orld[!.]',
			r'When\s([iI][Nn]\s)?the\ course',
			r"(dollar $ signs)$",
		):
			with self.subTest(spec=spec):
				tree, where = parse(spec, "Pattern")
	
	def test_02_confusing_charclass(self):
		for spec, inside, outside in [
			(r'[-x]', '-x', 'Aa'),  # contains minus
			(r'[x\-]', '-x', 'A\\a'),  # also contains minus
			(r'[^\]^abc]', 'xX\n', '^]abc'),  # negates; contains close-bracket
			(r'[^-\]^abc]', 'xX\n', '-]^abc'),  # contains both tricky characters
			(r"[\s\S]", "a\n ^", ""), # Should mean the universal character class
			(r"[-]", "-", "abc"), # Just minus
			(r"[^-]", "abc", "-"), # Not minus
		]:
			with self.subTest(spec=spec):
				t1, where = parse(spec, "Regular")
				# This should change to rely on the new treelang model.
				cl = ConvertLiterals(text=spec, slices=where, env=mode_normal)
				t2 = cl(t1)
				assert type(t2) is VOCAB["cls"]
				ce = ClassEncoder(names=cl.names, codepoints=cl.codepoints)
				cls = ce(t2.members)
				for c in inside: assert in_class(cls, ord(c))
				for c in outside: assert not in_class(cls, ord(c))

	def test_03_names_and_numbers(self):
		text = r"{foo}{1,2}"
		tree, where = parse(text, "Regular")
		assert type(tree) is VOCAB["n_to_m"]
		assert type(tree.sub) is VOCAB["name"]
		assert type(tree.min is VOCAB["number"])
		assert type(tree.max is VOCAB["number"])
		assert text[where[tree.sub]] == "{foo}"
		assert text[where[tree.min]] == "1"
		assert text[where[tree.max]] == "2"
	
	def test_04_common_errors(self):
		for text in ("]", "[]]", "}", "[]", "{}", "[^]"):
			with self.subTest(text=text):
				with self.assertRaises(ParseError):
					parse(text, "Regular")
	pass

if __name__ == '__main__':
	unittest.main()
