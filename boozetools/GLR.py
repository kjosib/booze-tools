"""
GLR is basically the non-deterministic version of LR parsing.

As a parsing strategy, it's amenable to the use of parse tables produced by any viable LR algorithm.
The more powerful table-construction algorithms result in comparatively fewer blind alleys for
a GLR runtime to explore.

Building a deterministic parse table can be seen as first building a non-deterministic one and
then taking a further step to resolve any conflicts. That is why I'm going down this alley.

"""
import typing, collections

from . import context_free

class GLR_State():
	"""
	This generic structure for a GLR(k) parse state is convenient while constructing
	parse tables. Later on, another structure may be better for actually using them.
	"""
	def __init__(self, core):
		self.core = frozenset(core)
		self.extension = set() # all active parse items; initially empty; facilitates the subset constructions.
		self.shifts = {} # Keys are symbols, values are state IDs.
		self.reductions = {} # Keys refer to productions, values are about look-ahead, defined by the table generator.

class HandleFindingAutomaton(typing.NamedTuple):
	grammar: context_free.ContextFreeGrammar # Because what good is a parse table without most of the grammar also?
	states: list #


def glr0_construction(grammar:context_free.ContextFreeGrammar, start: (str, list, tuple)) -> HandleFindingAutomaton:
	"""
	
	:param grammar: as advertised
	:param start: either a single start symbol or a group of acceptable ones.
	:return: The
	"""
