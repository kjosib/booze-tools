"""
The original input mode for MacroParse treated .md files as a container format.
This reads that format and turns it into a list of parts.
I'm going to go ahead and use the treelang module to represent the parts.


Translation plan:
1. Identify headings and code blocks.
2. Associate code blocks to headings.
3. Characterize headings.
4. Send each code-block to appropriate parser (based on heading).


"""
import os
from functools import partial
from boozetools.scanning.miniscan import Definition
from boozetools.support.treelang import RankedAlphabet

MarkDown = RankedAlphabet("node")
MarkDown.symbol("header", "node")
MarkDown.symbol("code", "node")

tree = []
text = {}
location = {}

def tok(kind, yy):
	it = MarkDown[kind]()
	tree.append(it)
	text[it] = yy.match()
	location[it] = yy.slice()

foo = Definition("Deconstruct Mark-Down")
foo.on(r"```(`?`?[^`])*```")(partial(tok, "code"))
foo.on(r"```(`?`?[^`])*")(partial(tok, "code")) # But this means non-closed section.
foo.on(r"^#.*")(partial(tok, "header"))
@foo.on(r"(`?`?[^`{vertical}])+|(`?`?{vertical})+")
def _other_text(yy):
	pass

# def deconstruct(text:str):
# 	"""
# 	A simple pass that breaks a .md file into component parts:
# 	headings, code-blocks, and other text (which is ignored).
# 	"""
#
#
# 	return tree, annotations

definition_path = os.path.join(os.path.dirname(__file__), 'pascal.md')
with open(definition_path) as fh:
	definition_text = fh.read()
scanner = foo.scan(definition_text)
try:
	list(scanner)
except:
	x = scanner.current_position()
	print(definition_text[x:x+20])
else:
	print(tree)
	print(text[tree[5]])
	