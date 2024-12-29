"""
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
default behavior of the SourceText. But you can supply a mode argument to specify
different line-ending conventions. The options are given symbolically as keys in the
LINEBREAK_MODE dictionary.

So how exactly SHOULD you delimit lines? The answer, my friend, is blowin' in the wind....
"""

import bisect, re, sys
from typing import NamedTuple, Any
from enum import Enum

LINEBREAK_MODE = {
	'normal': re.compile(r'\r\n?|\n'),
	'unicode': re.compile(r'\r\n|[\x0a-\x0d\x1c-\x1e\u0085\u2028\u2029]]'),
	'unix': re.compile(r'\n'),
	'apple': re.compile(r'\r'),
	'dos': re.compile(r'\r\n'),
}

class Severity(Enum):
	NOTICE = "Notice"
	WARNING = "Warning"
	ERROR = "Error"

class Evidence(NamedTuple):
	slice:slice
	caption: str = "here"
	
	def width(self): return self.slice.stop - self.slice.start

class Issue(NamedTuple):
	"""
	Contain all the information necessary to present elements of an error, warning, notice, or whatever.
	In theory, it should be possible to organize these for sensible presentation.
	
	The notion is that any given issue could result from an interaction of causes
	in multiple different places. (For example, a mismatched function signature
	might have declaration and reference in different files.) Thus:
	
	phase: tells what portion of the interpretation process found the issue.
	severity: tells how bad the issue is.
	description: explains the issue in plain language.
	evidence: a dictionary:
		from "key" (as known to an assumed "fetch" function),
		to lists of ``Evidence`` objects relevant to that corresponding text.
	"""
	phase: str
	severity: Severity
	description: str
	evidence: dict[Any, list[Evidence]]
	
	def as_text(self, fetch):
		"""
		This will generate a not-completely-terrible error report in text-only format.
		The precise format is subject to change, but basically you should be able to
		print this on stderr and not cry yourself to sleep.
		
		:param: "fetch" must be a function which takes a key (from the evidence dictionary)
		and returns a corresponding SourceText object.
		"""
		lines = ["%s while %s: %s"%(self.severity.value, self.phase, self.description)]
		for key, evidence in self.evidence.items():
			source = fetch(key)
			if source.filename:
				lines.append("Excerpt from "+source.filename+" :")
			for e in evidence:
				row, col = source.find_row_col(e.slice.start)
				single_line = source.line_of_text(row)
				lines.append(illustration(single_line, col, e.width(), prefix='% 6d :'%row, caption=e.caption))
		return "\n".join(lines)
		
	def emit(self, fetch):
		""" Print to standard error the generated error text. """
		print(self.as_text(fetch), file=sys.stderr)

def illustration(single_line:str, start:int, width:int=0, *, prefix='', caption="near here") -> str:
	""" Builds up a picture of where something appears in a line of text. Useful for polite error messages. """
	blanks = ''.join(c if c == '\t' else ' ' for c in prefix + single_line[:start])
	underline_width = max(1, min(width, len(single_line)-start))
	underline = '^'*underline_width
	return prefix + single_line.rstrip() + '\n' + blanks + underline +" "+caption

class SourceText:
	""" Wrapper for (a section of) source text: participates in half-respectable error-display with context. """
	def __init__(self, content:str, line_breaks='normal', filename:str=None, first_line=1):
		self.content = content
		self.filename = filename
		self.line_breaks = line_breaks
		self.first_line = first_line
	
	def __make_bounds(self):
		""" Lazily only find line breaks if it turns out to be necessary for a particular text. """
		if not hasattr(self, '__bound'):
			inside = [m.end() for m in LINEBREAK_MODE[self.line_breaks].finditer(self.content)]
			self.__bounds = [0] + inside + [len(self.content)]

	def find_row_col(self, index:int):
		""" Based on a character index offset from the start of text. Respects self.first_line. """
		self.__make_bounds()
		row = bisect.bisect_right(self.__bounds, index, hi=len(self.__bounds) - 1) - 1
		col = index - self.__bounds[row]
		return row+self.first_line, col
	
	def line_of_text(self, row):
		""" Argument respects self.first_line. """
		r = max(0, row - self.first_line)
		return self.content[self.__bounds[r]:self.__bounds[r + 1]]
	
	def _format_message(self, row, col, message):
		prefix = "At" if self.filename is None else str(self.filename)+":"
		return "%s line %d, column %d: %s" % (prefix, row, col + 1, message)
	
	def complaint(self, a_slice:slice, message:str):
		left, right = a_slice.start, a_slice.stop
		row, col = self.find_row_col(left)
		reference = self._format_message(row, col, message)
		line = self.line_of_text(row)
		illustrated = illustration(line, col, right - left, prefix=' >>> ')
		return "%s\n%s"%(reference, illustrated)

	def complain(self, a_slice:slice, message:str):
		print(self.complaint(a_slice, message), file=sys.stderr)

