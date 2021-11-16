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

In concept, our generic trees re-invent algebraic data types.
Pragmatic benefits of a centralized implementation include:
	1. It decouples the concept (essence) from the implementation language (accident).
	2. Data-driven construction-time sanity-checks on structure.
	3. A consistent source-tracking channel for tracing the origin(s) of bogus input.
	4. The possibility of data-driven transformations on tree structures.

What's here is far from perfect yet, but it's doing some jobs.
"""

__all__ = ['Ontology', 'OntologyError', 'Node']

from typing import NamedTuple, Optional
from dataclasses import dataclass


class _Symbol(NamedTuple):
	""" A tree node's "symbol" corresponds to its "constructor" in an "abstract data types" conception of trees. """
	label: str
	arity: tuple[str, ...] # Why strings? Why can't they be category-objects? Or have the list nature?
	index: dict[str, int]
	category: Optional[str] # Category may be thought of as a "data type" which may have several constructors/symbols.
	ontology: "Ontology"

	def node(self, *, semantic:object, children:tuple["Node", ...], debug_info) -> "Node":
		"""
		This is your general-case API to make nodes with this symbol.
		"""
		assert isinstance(children, tuple)
		assert len(children) == len(self.arity), "%r: %d expected, %d given"%(self.label, len(self.arity), len(children))
		assert not isinstance(semantic, Node)
		for b in children:
			assert isinstance(b, Node), b
			#assert a is None or a == b.symbol.category, (a, b.symbol.category) # This is not ready yet... Need an "extends" relationship.
		return Node(self, semantic, children, debug_info)

	def leaf(self, semantic:object, debug_info=None) -> "Node":
		return self.node(semantic=semantic, children=(), debug_info=debug_info)

	def from_args(self, *children, debug_info=None):
		""" Convenience function for mini-parse grammars. """
		return self.node(semantic=None, children=children, debug_info=debug_info)

class OntologyError(ValueError):
	pass

class Ontology:
	"""
	The symbols in a given ontology are meant to hang together.
	This is fairly simplistic, in that the categories do not form any sort of network.
	But it will do for experimentation.
	
	Two obvious enhancement ideas:
		For error reporting, you might want to know where the ontology came from.
		For language embedding, you might want to import symbols from another ontology.
	"""
	def __init__(self):
		self.symbols = {}
		self.defined_categories = {}
		self.mentioned_categories = set()
		
	def __getitem__(self, item):
		return self.symbols[item]
		
	def define_category(self, category:str, cases:dict[str,dict[str,str]]):
		"""
		category: a string describing the general data type all the cases fulfill.
		cases: dict[label, dict[field, category]]
		Why not accept a term from a meta-ontology? Because -- well -- not yet.
		"""
		if category in self.defined_categories: raise OntologyError(category)
		self.defined_categories[category] = set(cases.keys())
		for label, kids in cases.items():
			if label in self.symbols: raise OntologyError(label)
			self.mentioned_categories.update(kids.values())
			self.symbols[label] = _Symbol(label, tuple(kids.values()), dict((k,i) for i,k in enumerate(kids.keys())), category, self)
	
	def check_sanity(self):
		"""
		The ontology is sane when every field's category is defined.
		This would have to change if and when imports happen.
		"""
		bogons = self.mentioned_categories - self.defined_categories.keys()
		if bogons: raise OntologyError(bogons)
		

@dataclass(eq=False)
class Node:
	"""
	See TATA chapter "Preliminaries".
	This structure will be the backbone of the "arborist" framework.
	"""
	__slots__ = ('symbol', 'semantic', 'children', 'debug_info')
	symbol: _Symbol    # Refers into a dictionary of symbol definitions.
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

