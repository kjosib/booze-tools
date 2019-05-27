"""
Things Prone to Failure:

1. People.
2. Machines.

This module is all about easing over the process to display where things go wrong.
A tool-developer should have easy access to sophisticated error-displays.
Such should be made both likely and comfortable independent of other tools.

Error reporting is actually a topic of some complexity. Fortunately, the common cases
are reasonably straightforward and for the uncommon ones there is YAGNI (yet).
"""

import itertools, bisect

def illustration(text:str, start:int, width:int=0, *, prefix='') -> str:
	""" Builds up a picture of where something appears in a line of text. Useful for polite error messages. """
	text = text
	blanks = ''.join(c if c == '\t' else ' ' for c in prefix+text[:start])
	underline = '^'*(width or 1)+'-- right there'
	return prefix+text.rstrip()+'\n'+blanks+underline

class Text:
	"""
	Line breaks are a funny thing. Unix calls for \n. Apple prior to OSx called for \r.
	CP/M and its derivatives like Windows call for \r\n, really a printer control sequence.
	The Unicode line-breaking algorithm calls for no less than ELEVEN ways to break a line!
	So how exactly SHOULD you delimit lines? The answer, my friend, is blowin' in the wind....
	"""
	def __init__(self, content:str, filename:str=None):
		self.content = content
		self.bounds = [0, *itertools.accumulate(map(len, content.splitlines(keepends=True))), len(content)]
		self.nr_lines = len(self.bounds) - 2
		self.filename = filename
	def each_line(self):
		for i in range(self.nr_lines): yield self.get_line(i)
	def get_line(self, row:int) -> str:
		""" Zero-Based! (Like everything else in modern computing...) and includes line end. """
		return self.content[self.bounds[row]:self.bounds[row+1]]
	def find_row_col(self, index:int):
		""" Zero-Based! This right here is the main point of the class... """
		row = bisect.bisect_right(self.bounds, index, hi=len(self.bounds)-1)-1
		col = index - self.bounds[row]
		return row, col
