"""
Things Prone to Failure:

1. People.
2. Machines.

This module is all about easing over the process to display where things go wrong.
A tool-developer should have easy access to sophisticated error-displays.
Such should be made both likely and comfortable independent of other tools.

Error reporting is actually a topic of some complexity. Fortunately, the common cases
are reasonably straightforward and for the uncommon ones there is YAGNI (yet).

If you can localize where an error came from, you'd generally like to include some
context in the report. The usual strategy is to show the offending line, ideally
with a specific portion highlighted somehow. If you're dealing with a text console
(as many tools do) then the `illustration` function helps: Given a single line of
text and a few parameters, it makes a suitable picture.

I prefer to keep line-breaking separate from scanning and parsing, so in those areas
a simple integer position is as much location data as you get. What's a decent means
to convert that to a line and column number? Or to slice the corresponding line
from a larger text string? The SourceText handles that. It also provides a nice
`complain(...)` method, which formats a decent-looking error message to STDOUT.

There is just one complication:

Line breaks are a funny thing. Unix calls for \n. Apple prior to OSx called for \r.
CP/M and its derivatives like Windows call for \r\n, really a printer control sequence.
OS/390 (an IBM mainframe thing) tends toward character 0x85 (a high-ascii control code)
whenever it isn't thinking in EBCDIC, but who in their right mind uses EBCDIC anymore?
The Unicode line-breaking algorithm calls for no less than ELEVEN ways to break a line!

The applications I've tested treat the Unix, Apple, and DOS conventions as line-breaks
and mostly ignore the other options defined in the Unicode standard, so that's the
default behavior of the SourceText. But you can supply a mode parameter to specify
different line-ending conventions. The options are given symbolically as keys in the
LINEBREAK_MODE dictionary.

So how exactly SHOULD you delimit lines? The answer, my friend, is blowin' in the wind....
"""

import bisect, re, sys

LINEBREAK_MODE = {
	'normal': re.compile(r'\r\n?|\n'),
	'unicode': re.compile(r'\r\n|[\x0a-\x0d\x1c-\x1e\u0085\u2028\u2029]]'),
	'unix': re.compile(r'\n'),
	'apple': re.compile(r'\r'),
	'dos': re.compile(r'\r\n'),
}

def illustration(single_line:str, start:int, width:int=0, *, prefix='') -> str:
	""" Builds up a picture of where something appears in a line of text. Useful for polite error messages. """
	blanks = ''.join(c if c == '\t' else ' ' for c in prefix + single_line[:start])
	underline = '^'*(width or 1)+'-- right there'
	return prefix + single_line.rstrip() + '\n' + blanks + underline

class SourceText:
	""" A wrapper for e.g. a program source text which can print a half-respectable error message with context. """
	def __init__(self, content:str, line_breaks='normal', filename:str=None):
		self.content = content
		self.filename = filename
		self.line_breaks = line_breaks
	
	def __make_bounds(self):
		""" Lazily only find line breaks if it turns out to be necessary for a particular text. """
		if not hasattr(self, '__bound'):
			inside = [m.end() for m in LINEBREAK_MODE[self.line_breaks].finditer(self.content)]
			self.__bounds = [0] + inside + [len(self.content)]

	def find_row_col(self, index:int):
		""" Zero-Based! This right here is the main point of the class... """
		self.__make_bounds()
		row = bisect.bisect_right(self.__bounds, index, hi=len(self.__bounds) - 1) - 1
		col = index - self.__bounds[row]
		return row, col
	
	def complain(self, index:int, width=1, *, message:str=None):
		"""  """
		row, col = self.find_row_col(index)
		line = self.content[self.__bounds[row]:self.__bounds[row + 1]]
		if self.filename is None: print("At line %d, column %d,"%(row+1, col+1), file=sys.stderr)
		else: print("At line %d, column %d, in file %s"%(row+1, col+1, self.filename), file=sys.stderr)
		print(illustration(line, col, width, prefix=' >>> '), file=sys.stderr)
		if message is not None: print(message, file=sys.stderr)
