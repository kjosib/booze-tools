""" An AST class-hierarchy for regular expressions and mechanisms for translating them. """

from ..arborist.trees import make_symbol, Node
from . import finite, charset

class PatternError(Exception):
	"""
	Raised if something wrong is found with a regular expression.
	"""
	errmsg = "Generic Pattern Semantic Error."
class BadReferenceError(PatternError):
	"""
	Raised if a pattern refers to a subexpression name not defined in the context of the analysis.
	args are the offending reference and the span within the pattern (offset/length pair) where it appears.
	"""
	errmsg = "This reference-name has no definition (yet)."
class CircularDefinitionError(PatternError):
	"""
	Raised if a named pattern somehow refers back to itself.
	args are the offending reference and the span within the pattern (offset/length pair) where it appears.
	"""
	errmsg = "This expression definition refers back to itself, which is not allowed."
class NonClassError(PatternError):
	"""
	Raised if a character class definition refers to a named expression which is not itself a character class.
	args are the offending reference and the span within the pattern (offset/length pair) where it appears.
	"""
	errmsg = "This reference-name appears in a character class, but is defined other than as a character class."
class TrailingContextError(PatternError):
	"""
	Raised if pattern has both variable-sized stem and variable-sized trailing context.
	This is not supported at this time.
	"""
	errmsg = "Pattern has variable-sized both stem and trailing context; currently unsupported."
class PatternSyntaxError(PatternError):
	"""
	Raised if the pattern is unsyntactic.
	"""
	errmsg = "Pattern syntax does not compute."

codepoint = make_symbol('Codepoint', {}, 'char_class') # Semantic is codepoint.

# A bit of theory: A character class is an intersection of one or more (possibly-inverted) set/unions;
# each set consists of one or more of codepoints, ranges, and named-classes. Therefore, we get this alphabet:
VOCAB = {s:make_symbol(s,k,c) for (s,k,c) in [
	('CharRange', {'first':'Codepoint', 'last':'Codepoint'}, 'char_class'),
    ('Sequence', {'a':'regular', 'b':'regular'}, 'regex'),
    ('Alternation', {'a':'regular', 'b':'regular'}, 'regex'),
	('Star', {'sub':'regular'}, 'regex'),
	('Hook', {'sub':'regular'}, 'regex'),
	('Plus', {'sub':'regular'}, 'regex'),
	('n_times', {'sub':'regular', 'num':'Bound'}, 'regex'),
	('n_or_more', {'sub':'regular', 'min':'Bound'}, 'regex'),
	('n_or_fewer', {'sub':'regular', 'max':'Bound'}, 'regex'),
	('n_to_m', {'sub':'regular', 'min':'Bound', 'max':'Bound'}, 'regex'),
	('CharUnion', {'a': 'char_class', 'b': 'char_class', }, 'char_class'),
	('CharIntersection', {'a': 'char_class', 'b': 'char_class', }, 'char_class'),
	('CharComplement', {'inverse': 'char_class'}, 'char_class'),
	('pattern_regular', {'left_context':'left_context', 'stem':'regular'}, 'pattern'),
	('pattern_with_trail', {'left_context':'left_context', 'stem':'regular', 'trail':'regular'}, 'pattern'),
	('pattern_only_trail', {'left_context':'left_context', 'trail':'regular'}, 'pattern'),
]}
char_prebuilt = make_symbol('CharPrebuilt', {}, 'char_class')
bound = make_symbol('Bound', {}) # Semantic is number (or None).
named_subexpression = make_symbol('NamedSubexpression', {}, 'regex') # Semantic is subexpression name.

LEFT_CONTEXT = {
	'anywhere': (True, True),
	'begin_line': (False, True),
	'mid_line': (True, False),
}
for x in LEFT_CONTEXT:
	VOCAB[x] = make_symbol(x, {}, 'left_context')

class Encoder:
	"""
	This visitor represents the strategy to encode a regular expression as
	a non-deterministic finite state automaton.
	"""
	def __init__(self, nfa:finite.NFA, rank:int, names:dict):
		self.__nfa = nfa
		self.__rank = rank
		self.__names = names
		self.__ce = ClassEncoder(names)
		self.__inside = set()  # For detecting circular definitions.
	def __new_node(self): return self.__nfa.new_node(self.__rank)
	def __eps(self, src:int, dst:int, ): self.__nfa.link_epsilon(src, dst)
	def __chars(self, n:Node, src:int, dst:int, ):
		cc = n.tour(self.__ce)
		assert isinstance(cc, list), n
		self.__nfa.link(src, dst, cc)
	tour_CharPrebuilt = tour_Codepoint = tour_CharRange = tour_CharUnion = tour_CharIntersection = tour_CharComplement = __chars

	def tour_Alternation(self, alt:Node, src:int, dst:int, ):
		alt['a'].tour(self, src, dst)
		alt['b'].tour(self, src, dst)
	def tour_Sequence(self, seq:Node, src:int, dst:int, ):
		midpoint = self.__new_node()
		seq['a'].tour(self, src, midpoint)
		seq['b'].tour(self, midpoint, dst)
	def tour_Star(self, s:Node, src:int, dst:int, ):
		loop = self.__new_node()
		s['sub'].tour(self, loop, loop)
		self.__eps(src, loop)
		self.__eps(loop, dst)
	def tour_Hook(self, h:Node, src:int, dst:int, ):
		h['sub'].tour(self, src, dst)
		self.__eps(src, dst)
	def tour_Plus(self, p:Node, src:int, dst:int, ):
		before, after = self.__new_node(), self.__new_node()
		p['sub'].tour(self, before, after)
		self.__eps(src, before)
		self.__eps(after, before)
		self.__eps(after, dst)
	def tour_n_times(self, n:Node, src:int, dst:int, ):
		self._counted(n['sub'], n['num'].semantic, n['num'].semantic, src, dst)
	def tour_n_to_m(self, n:Node, src:int, dst:int, ):
		self._counted(n['sub'], n['min'].semantic, n['max'].semantic, src, dst)
	def tour_n_or_more(self, n:Node, src:int, dst:int, ):
		self._counted(n['sub'], n['min'].semantic, None, src, dst)
	def tour_n_or_fewer(self, n:Node, src:int, dst:int, ):
		self._counted(n['sub'], 0, n['max'].semantic, src, dst)
	def _counted(self, sub:Node, least:int, most, src:int, dst:int, ):
		p1 = self.__new_node()
		self.__eps(src, p1)
		for _ in range(least):
			p2 = self.__new_node()
			sub.tour(self, p1, p2)
			p1 = p2
		self.__eps(p1, dst)
		if most is None:
			sub.tour(self, p1, p1)
		else:
			for _ in range(most - least):
				p2 = self.__new_node()
				sub.tour(self, p1, p2)
				self.__eps(p2, dst)
				p1 = p2
	def tour_NamedSubexpression(self, ns:Node, src:int, dst:int, ):
		try: item = self.__names[ns.semantic]
		except KeyError: raise BadReferenceError(ns)
		if ns.semantic in self.__inside: raise CircularDefinitionError(ns)
		self.__inside.add(ns.semantic)
		result = item.tour(self, src, dst)
		self.__inside.remove(ns.semantic)
		return result


class Sizer:
	"""
	Finds the fixed length of a Regular, if it is defined.
	"""
	
	def __init__(self, names: dict[object, Node]):
		self.__names = names
	
	def __chars(self, _:Node): return 1
	tour_CharPrebuilt = tour_Codepoint = tour_CharRange = tour_CharUnion = tour_CharIntersection = tour_CharComplement = __chars

	def tour_Alternation(self, n:Node):
		a,b = n['a'].tour(self), n['b'].tour(self)
		return a if a == b else None
	def tour_Sequence(self, n:Node):
		a,b = n['a'].tour(self), n['b'].tour(self)
		if None not in (a,b): return a + b
	def tour_Star(self, _:Node): return None
	def tour_Hook(self, _:Node): return None
	def tour_Plus(self, _:Node): return None
	def tour_n_or_more(self, _:Node): return None
	def tour_n_or_fewer(self, _:Node): return None
	def tour_n_times(self, n:Node):
		sub = n['sub'].tour(self)
		if sub is not None: return sub * n['num'].semantic
	def tour_n_to_m(self, ct:Node):
		if ct['min'].semantic == ct['max'].semantic:
			x = ct['sub'].tour(self)
			if x is not None: return x * ct['min'].semantic
	def tour_NamedSubexpression(self, ns:Node):
		try: item = self.__names[ns.semantic]
		except KeyError: raise BadReferenceError(ns)
		return item.tour(self)


class ClassEncoder:
	"""
	Builds a character class in the format used by the finite.NFA class.
	
	One might think this could all be done inside class Encoder, but the
	treatment of name references differs.
	"""
	def __init__(self, names:dict):
		self.__names = names
	
	def tour_CharPrebuilt(self, n:Node): return n.semantic
	def tour_Codepoint(self, n:Node): return charset.singleton(n.semantic)
	def tour_CharRange(self, n:Node): return charset.range_class(n['first'].semantic, n['last'].semantic)
	def tour_CharUnion(self, n:Node): return charset.union(n['a'].tour(self), n['b'].tour(self))
	def tour_CharIntersection(self, n:Node): return charset.intersect(n['a'].tour(self), n['b'].tour(self))
	def tour_CharComplement(self, n:Node): return charset.complement(n['inverse'].tour(self))
	def tour_NamedSubexpression(self, n:Node):
		try: expr = self.__names[n.semantic]
		except KeyError: raise BadReferenceError(n)
		if expr.symbol.category == 'char_class': return expr.tour(self)
		else: raise NonClassError(n)
	