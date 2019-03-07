"""
This module implements the macro-enabled enhanced-BNF context-free grammar semantics.
There is exactly zero concern for where the production rules come from.

Because the production rules support a no-kidding macro language, this module gets a
good bit of hair all by itself. It is both expedient and illustrative to use miniparse
and miniscan definitions to analyze the definitions.

"""

from boozetools import miniparse, miniscan

"""
The MetaParse definition object works with structured rewriting-rule objects. They
are composed of the following set of semantic objects:
"""
### Here's a set of semantic categories for the breakdown of rewrite rules:
class Element:
	""" Base class of RHS elements. """
	def canonical_symbol(self) -> str:
		""" To support the enhancements over plain BNF, each element needs a canonical symbolic expression. """
		raise NotImplementedError(type(self))

class Action(Element):
	def __init__(self, name): self.name = name
	def canonical_symbol(self) -> str: return ':'+self.name

class Symbol(Element):
	def __init__(self, name): self.name = name
	def canonical_symbol(self) -> str: return self.name

class InlineRenaming(Element):
	def __init__(self, alternatives): self.alternatives = alternatives
	def canonical_symbol(self) -> str: return "[%s]"%("|".join(s.canonical_symbol() for s in self.alternatives))

class MacroCall(Element):
	def __init__(self, name, actuals): self.name, self.actuals = name, actuals
	def canonical_symbol(self) -> str: return "%s(%s)"%(self.name, ",".join(s.canonical_symbol() for s in self.actuals))


class Rewrite:
	def __init__(self, elements:list, precsym):
		self.elements = elements
		self.precsym = precsym
		self.message = self.elements.pop(-1).name if isinstance(self.elements[-1], Action) else None
		self.__args = args = []
		self.size = len(self.elements)
		for i,elt in enumerate(self.elements):
			if hasattr(elt, 'capture'): args.append(i)
		if not args: args.extend(range(self.size)) # Pick up everything if nothing is special.
	def prefix_capture(self, size:int):
		return tuple(c - size for c in self.__args if c < size)

"""
The MacroParse metagrammar contains various repetition constructs. The following functions
act as rudimentary macros to relieve some redundancy; they essentially mean something like:

	list_of(what, sep) -> what :first | .list_of(what, sep) sep .what :append
	one_or_more(what) -> what :first | .one_or_more(what) .what :append

Doing macros for real is a little more complicated and will be dealt with further down.
"""
def list_of(what, sep):
	head = 'list_of(%r,%r)'%(what,sep)
	PRODUCTION.rule(head, '.%s'%what)(FIRST)
	PRODUCTION.rule(head, '.%s %s .%s'%(head, sep, what) )(APPEND)
	return head
def one_or_more(what):
	head = 'one_or_more(%r)' % (what)
	PRODUCTION.rule(head, '.%s' % what)(FIRST)
	PRODUCTION.rule(head, '.%s .%s' % (head, what))(APPEND)
	return head
def FIRST(element): return [element]
def APPEND(the_list, element):
	the_list.append(element)
	return the_list



"""
The MacroParse metagrammar for individual production lines is as follows:

production -> .head arrow .list_of(rewrite, '|')

head       -> :use_prior | name | .name '(' .list_of(name, ',' ) ')'

rewrite    -> one_or_more(element) :normal_rewrite
	| .one_or_more(element) pragma_precsym .[name literal] :prec_rewrite
	
element    -> slot | capture slot :capturing

slot       -> symbol | message :action

symbol     -> name | literal
	| '[' .one_or_more(symbol) ']' :gensym_renaming
	| .name '(' .list_of(symbol, ',') ')' :macro_call
"""
PRODUCTION = miniparse.MiniParse('production')

PRODUCTION.rule('production', '.head arrow .'+list_of('rewrite', '|'))

PRODUCTION.rule('head', '', lambda :None) # "use prior" is represented by a null "head".
PRODUCTION.renaming('head', 'name',) # This will come across as a string.
PRODUCTION.rule('head', '.name ( .%s )'%list_of('name', ','))(tuple) # Represent macro heads with (name, args) tuples.

PRODUCTION.rule('rewrite', one_or_more('element'))(lambda elements:Rewrite(elements, None))
PRODUCTION.rule('rewrite', '.'+one_or_more('element')+' pragma_precsym .terminal')(Rewrite)

PRODUCTION.renaming('terminal', 'name', 'literal')

PRODUCTION.renaming('element', 'slot')
@PRODUCTION.rule('element', 'capture .slot')
def capture(slot:Element):
	slot.capture = True
	return slot

PRODUCTION.rule('symbol', 'name')(Symbol)    # Normal symbol
PRODUCTION.rule('symbol', 'literal')(Symbol) # Also a normal symbol with a funny name
PRODUCTION.rule('symbol', '[ .'+one_or_more('symbol')+' ]')(InlineRenaming)
PRODUCTION.rule('symbol', '.name ( .'+list_of('symbol', ',')+' )')(MacroCall)



### The lexeme definitions for production rule lines are as follows:
LEX = miniscan.Definition()
LEX.on(r'\s+')(None) # Ignore whitespace
LEX.on(r'\l\w*')('name') # Identifiers as token type "name".
LEX.on(r':\l\w*')(lambda scanner:('message', scanner.matched_text()[1:])) # Strip out the colon for message names
LEX.on(r'%\l+')(lambda scanner:('pragma_'+scanner.matched_text()[1:], None)) # Build pragma token types from the text.
LEX.on(r'[.]/\S')('capture') # a dot prefixes a captured element, so it needs to be followed by something.
LEX.on(r'[][(),|]')(lambda scanner:(scanner.matched_text(), None)) # Punctuation is represented directly above.
LEX.on(r"'\S+'")(lambda scanner:('literal', scanner.matched_text()[1:-1])) # Literals are allowed two ways, so you can
LEX.on(r'"\S+"')(lambda scanner:('literal', scanner.matched_text()[1:-1])) # easily contain whichever kind of quote.
LEX.on(r'[-=>:<]+')('arrow') # Arrows in grammar definitions tend to look all different ways. This is flexible.

