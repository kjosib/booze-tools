"""
This module contains the example drivers for applications of the sample MacroParse grammars also found
herein. They are exercised in the testing framework.

The ideal design is still being discovered. One way or another, it's necessary to bind the messages of
a definition to a set of functions and their shared context per-parse. The way that seems most natural
in Python is to let a class definition provide the implementations.

For a parser, the job is a little easier: Messages correspond to reduction functions, so the interface
is rather unsurprising.

The hinkey bit is the interface between scanner and parser. The full generality of scanning features,
including all the usual forms of context-dependent scanning, require the individual scanner actions
to call into the parser with zero or more tokens, potentially sharing state with the parse actions.

It's anticipated that relatively few fundamentally distinct scanner actions would be required for
most applications that also involve a parser, so therefore requiring the explicit call into a
parser object is not any major inconvenience.

"""

from boozetools import interfaces

# JSON -- Scanner:

class ScanJSON:
	RESERVED = {'true': True, 'false':False, 'null':None}
	ESCAPES = {'b': 8, 't': 9, 'n': 10, 'f': 12, 'r': 13, }
	
	def on_ignore_whitespace(self, scanner:interfaces.ScanState, parameter): pass
	def on_punctuation(self, scanner:interfaces.ScanState, parameter): return scanner.matched_text(), None
	def on_integer(self, scanner:interfaces.ScanState, parameter): return 'number', int(scanner.matched_text())
	def on_float(self, scanner:interfaces.ScanState, parameter): return 'number', float(scanner.matched_text())
	def on_reserved_word(self, scanner:interfaces.ScanState, parameter): return scanner.matched_text(), self.RESERVED[scanner.matched_text()]
	def on_enter_string(self, scanner:interfaces.ScanState, parameter):
		scanner.enter('in_string')
		return scanner.matched_text(), None
	def on_stringy_bit(self, scanner:interfaces.ScanState, parameter): return 'character', scanner.matched_text()
	def on_escaped_literal(self, scanner:interfaces.ScanState, parameter): return 'character', scanner.matched_text()[1]
	def on_shorthand_escape(self, scanner:interfaces.ScanState, parameter): return 'character', chr(self.ESCAPES[scanner.matched_text()[1]])
	def on_unicode_escape(self, scanner:interfaces.ScanState, parameter): return 'character', chr(int(scanner.matched_text()[2:],16))
	def on_leave_string(self, scanner:interfaces.ScanState, parameter):
		scanner.enter('INITIAL')
		return scanner.matched_text(), None
	

# JSON -- Parser:

