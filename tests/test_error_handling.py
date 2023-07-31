import unittest
from boozetools.macroparse.compiler import compile_string
from boozetools.macroparse import runtime
from boozetools.parsing.interface import END_OF_TOKENS
from boozetools.scanning.engine import IterableScanner

SAMPLE_GRAMMAR = """
## Productions start
```
start -> exp exp
	| $error$ :error
exp -> word

```
## Patterns
```
{alpha}+  :word
\s+  :ignore
.  :other
```
"""
TEXTBOOK_FORM = compile_string(SAMPLE_GRAMMAR, True).determinize()
# TEXTBOOK_FORM.pretty_print()  # Uncomment when confused...
COMPACT_FORM = TEXTBOOK_FORM.as_compact_form(filename=None)

class Parser(runtime.TypicalApplication):
	def __init__(self):
		super().__init__(COMPACT_FORM)
		self.unexpected = None
	
	def scan_word(self, yy:IterableScanner):
		yy.token('word', yy.match())
		
	def scan_ignore(self, yy:IterableScanner):
		pass
	
	def scan_other(self, yy:IterableScanner):
		yy.token('other', yy.match())
		
	def parse_error(self, *args):
		return "ERROR"
	
	def unexpected_token(self, kind, semantic, pds):
		self.unexpected = kind

class Test_MacroParse_Errors(unittest.TestCase):
	
	def setUp(self) -> None:
		self.parser = Parser()
	
	def test_empty(self):
		self.assertEqual("ERROR", self.parser.parse(""))
		self.assertEqual(END_OF_TOKENS, self.parser.unexpected)

	def test_unexpected(self):
		self.assertEqual("ERROR", self.parser.parse("+"))
		self.assertEqual('other', self.parser.unexpected)
		
	def test_excess(self):
		self.assertEqual("ERROR", self.parser.parse("foo bar baz"))
		self.assertEqual('word', self.parser.unexpected)

	def test_non_error(self):
		tree = self.parser.parse("foo bar")
		self.assertIsNone(self.parser.unexpected)
		self.assertEqual(("foo", "bar"), tree)


if __name__ == '__main__':
	unittest.main()
