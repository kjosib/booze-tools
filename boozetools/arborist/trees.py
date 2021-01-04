"""
After playing with parsers and languages, it soon it becomes clear
that a few things are pretty standard about the next steps. Notwithstanding
the occasional single-pass application or lexical context-sensitivity, most
of the job of a parse driver is usually to build a tree structure which later
code will then walk top-down.

Many nice prospects fall out of a standard "normal form" for such a tree:
	1: Smarter parse rules to construct trees directly, eliminating most "parse_foo" actions.
	2: Denotational tree-semantics rather than implied consequences of host-language features.
	3: Consistent and modular debug-information tracking with well-defined tree transducers.
	4: Standard infrastructure for (potentially very sophisticated) tree processing.
	5: Other benefits it's hard to articulate past midnight.

My temptation to start down this path came from reading:
	"Tree Automata Techniques and Applications" (http://tata.gforge.inria.fr/)


"""

__all__ = ['make_symbol', 'Node']

from typing import NamedTuple, Optional
from dataclasses import dataclass


class _Symbol(NamedTuple):
	""" A tree node's "symbol" gives
	has various characteristics.... """
	label: str
	arity: tuple[str, ...]
	index: dict[str, int]
	category: Optional[str]
	origin: object

	def node(self, *, semantic:object, children:tuple["Node", ...], debug_info) -> "Node":
		"""
		This is your general-case API to make nodes with this symbol.
		"""
		assert isinstance(children, tuple)
		assert len(children) == len(self.arity), "%r: %d expected, %d given"%(self.label, len(self.arity), len(children))
		assert not isinstance(semantic, Node)
		return Node(self, semantic, children, debug_info)

	def leaf(self, semantic:object, debug_info=None) -> "Node":
		return self.node(semantic=semantic, children=(), debug_info=debug_info)

	def from_args(self, *children, debug_info=None):
		""" Convenience function for mini-parse grammars. """
		return self.node(semantic=None, children=children, debug_info=debug_info)

def make_symbol(label:str, kids:dict[str,str], category:str=None, origin=None):
	return _Symbol(label, tuple(kids.values()), dict((k,i) for i,k in enumerate(kids.keys())), category, origin)


@dataclass(eq=False)
class Node:
	"""
	See TATA chapter "Preliminaries".
	This structure will be the backbone of the "arborist" framework.
	"""
	__slots__ = ('symbol', 'semantic', 'children', 'debug_info')
	symbol: _Symbol     # Refers into a dictionary of symbol definitions.
	semantic: object   # Mutable in general, but a bottom-up pass may provide a basis object.
	children: tuple    # Must have correct arity for the symbol.
	debug_info: object # Although this remains application-defined, often a file position might work.

	def __getitem__(self, item) -> 'Node':
		""" Make this work sort of like a record, where the Symbol gives the structure. """
		return self.children[self.symbol.index[item]]

	def tour(self, host, /, *args, **kwargs):
		""" Might as well implement classical visitor-pattern double-dispatch. """
		method = getattr(host, "tour_"+self.symbol.label)
		return method(self, *args, **kwargs)

