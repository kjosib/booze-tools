"""
This module contains an example driver for the sample MacroParse JSON grammar found
[herein](json.md). It is exercised in the [testing framework](../tests/test_examples.py).

One way or another, it's necessary to bind the messages of a definition to a set of functions and their
shared context per-scan/parse. The way that seems most natural in Python is to let a class definition
provide the implementation for the messages named in the scanner and parser specifications.

If the Python method names are kept distinct (as by using a different prefix for scan and parse actions)
then the same object can provide a sensible context and driver for both scanning and parsing. This
greatly facilitates any sort of context-dependent ad-hockery that your subject language might demand.
"""

from boozetools.scanning.engine import IterableScanner


class ExampleJSON:
	"""
	This is the application driver for the JSON sample.
	As you can see, it contains methods named for the messages in the scanner and parser definitions.
	No rule says you have to use the same context object for both, but it's often convenient.
	
	Just as with MiniScan, call yy.token(...) from your scan_*(...) methods to emit tokens.
	(The same engine is used for both.) In most applications, the set of necessarily-distinct scanner
	recognition rules is likely to be relatively small, especially considering that the parse algorithm
	takes terminal identities symbolically. That is why the scanner messages come with room for a parameter.
	It just happens not to be particularly relevant for JSON, so the parameter is never actually
	used in this example.
	
	A generic parser function consumes a stream of <symbolic-token, semantic-value> pairs and
	invokes parse_*(...) as appropriate to compose semantic values for production rules.
	
	This simple approach to scanner/parser integration is usually just fine. Still,
	it's nice to be able to invert that relation and explicitly send tokens into the parser
	when and where you desire. To that end, a parser-as-object is in the pipeline.
	"""
	
	RESERVED = {'true': True, 'false':False, 'null':None}
	ESCAPES = {'b': 8, 't': 9, 'n': 10, 'f': 12, 'r': 13, }
	
	def scan_ignore_whitespace(self, yy: IterableScanner): pass
	def scan_punctuation(self, yy: IterableScanner): yy.token(yy.match())
	def scan_integer(self, yy: IterableScanner): yy.token('number', int(yy.match()))
	def scan_float(self, yy: IterableScanner): yy.token('number', float(yy.match()))
	def scan_reserved_word(self, yy: IterableScanner): yy.token(yy.match(), self.RESERVED[yy.match()])
	def scan_enter_string(self, yy: IterableScanner):
		yy.enter('in_string')
		yy.token(yy.match())
	def scan_stringy_bit(self, yy: IterableScanner): yy.token('character', yy.match())
	def scan_escaped_literal(self, yy: IterableScanner): yy.token('character', yy.match()[1])
	def scan_shorthand_escape(self, yy: IterableScanner): yy.token('character', chr(self.ESCAPES[yy.match()[1]]))
	def scan_unicode_escape(self, yy: IterableScanner): yy.token('character', chr(int(yy.match()[2:],16)))
	def scan_leave_string(self, yy: IterableScanner):
		yy.enter('INITIAL')
		yy.token(yy.match())
	
	def parse_empty(self): return []
	def parse_first(self, item): return [item]
	def parse_append(self, aList, anItem):
		aList.append(anItem)
		return aList
	def parse_object(self, kv_pairs): return dict(kv_pairs)
	def parse_string(self, parts): return ''.join(parts)
