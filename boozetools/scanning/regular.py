""" An AST class-hierarchy for regular expressions and mechanisms for translating them. """

from typing import List
from ..support import foundation
from . import finite, charset

class PatternError(Exception):
	"""
	Raised if something wrong is found with the semantics of a regular expression.
	"""
class BadReferenceError(PatternError):
	"""
	Raised if a pattern refers to a subexpression name not defined in the context of the analysis.
	args are the offending reference and the span within the pattern (offset/length pair) where it appears.
	"""
class CircularDefinitionError(PatternError):
	"""
	Raised if a named pattern somehow refers back to itself.
	args are the offending reference and the span within the pattern (offset/length pair) where it appears.
	"""
class NonClassError(PatternError):
	"""
	Raised if a character class definition refers to a named expression which is not itself a character class.
	args are the offending reference and the span within the pattern (offset/length pair) where it appears.
	"""
class TrailingContextError(PatternError):
	"""
	Raised if pattern has both variable-sized stem and variable-sized trailing context.
	This is not supported at this time.
	"""


class Regular: pass


class CharClass(Regular): pass

class CharSpecial(CharClass):
	""" Useful for pre-built classes, I suppose... """
	def __init__(self, cls:List[int]):
		self.cls = cls

class Letter(CharClass):
	def __init__(self, codepoint:int):
		self.codepoint = codepoint

class CharRange(CharClass):
	def __init__(self, first:int, last:int):
		self.first, self.last = first, last

class CharUnion(CharClass):
	def __init__(self, a:CharClass, b:CharClass): self.a, self.b = a,b

class CharIntersection(CharClass):
	def __init__(self, a:CharClass, b:CharClass): self.a, self.b = a,b

class CharComplement(CharClass):
	def __init__(self, inverse:CharClass): self.inverse = inverse

class Binary(Regular):
	def __init__(self, a:Regular, b:Regular): self.a, self.b = a,b

class Alternation(Binary): pass
class Sequence(Binary): pass
class Inflection(Regular):
	def __init__(self, sub:Regular): self.sub = sub

class Star(Inflection): pass
class Hook(Inflection): pass
class Plus(Inflection): pass
class Counted(Regular):
	""" Just too handy not to provide. """
	def __init__(self, sub: Regular, m:int, n):
		assert isinstance(sub, Regular)
		assert isinstance(m, int)
		assert isinstance(n, int) or n is None
		self.sub, self.m, self.n = sub, m, n

class NamedSubexpression(Regular):
	def __init__(self, name, trace):
		self.name, self.trace = name, trace


class Encoder(foundation.Visitor):
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
	def visit_CharClass(self, cc:CharClass, src:int, dst:int, ):
		self.__nfa.link(src, dst, self.__ce.visit(cc))
	def visit_Alternation(self, alt:Alternation, src:int, dst:int, ):
		self.visit(alt.a, src, dst)
		self.visit(alt.b, src, dst)
	def visit_Sequence(self, seq:Sequence, src:int, dst:int, ):
		midpoint = self.__new_node()
		self.visit(seq.a, src, midpoint)
		self.visit(seq.b, midpoint, dst)
	def visit_Star(self, star:Star, src:int, dst:int, ):
		loop = self.__new_node()
		self.visit(star.sub, loop, loop)
		self.__eps(src, loop)
		self.__eps(loop, dst)
	def visit_Hook(self, hook:Hook, src:int, dst:int, ):
		self.visit(hook.sub, src, dst)
		self.__eps(src, dst)
	def visit_Plus(self, plus:Plus, src:int, dst:int, ):
		before, after = self.__new_node(), self.__new_node()
		self.visit(plus.sub, before, after)
		self.__eps(src, before)
		self.__eps(after, before)
		self.__eps(after, dst)
	def visit_Counted(self, ct:Counted, src:int, dst:int, ):
		p1 = self.__new_node()
		self.__eps(src, p1)
		for _ in range(ct.m):
			p2 = self.__new_node()
			self.visit(ct.sub, p1, p2)
			p1 = p2
		self.__eps(p1, dst)
		if ct.n is None:
			self.visit(ct.sub, p1, p1)
		else:
			for _ in range(ct.n - ct.m):
				p2 = self.__new_node()
				self.visit(ct.sub, p1, p2)
				self.__eps(p2, dst)
				p1 = p2
	def visit_NamedSubexpression(self, ns:NamedSubexpression, src:int, dst:int, ):
		try: item = self.__names[ns.name]
		except KeyError: raise BadReferenceError(ns.name, ns.trace)
		if ns.name in self.__inside: raise CircularDefinitionError(ns.name, ns.trace)
		self.__inside.add(ns.name)
		result = self.visit(item, src, dst)
		self.__inside.remove(ns.name)
		return result


class Sizer(foundation.Visitor):
	"""
	Finds the fixed length of a Regular, if it is defined.
	"""
	
	def __init__(self, names: dict):
		self.__names = names
	
	def visit_CharClass(self, _): return 1
	def visit_Alternation(self, alt:Alternation):
		a, b = self.visit(alt.a), self.visit(alt.b)
		return a if a == b else None
	def visit_Sequence(self, seq:Sequence):
		a, b = self.visit(seq.a), self.visit(seq.b)
		if None not in (a,b): return a + b
	def visit_Star(self, star: Star): return None
	def visit_Hook(self, hook: Hook): return None
	def visit_Plus(self, plus: Plus): return None
	def visit_Counted(self, ct: Counted):
		if ct.m == ct.n:
			x = self.visit(ct.sub)
			if x is not None: return x * ct.m
	def visit_NamedSubexpression(self, ns:NamedSubexpression):
		try: item = self.__names[ns.name]
		except KeyError: raise BadReferenceError(ns.name, ns.trace)
		return self.visit(item)


class ClassEncoder(foundation.Visitor):
	"""
	Builds a character class in the format used by the finite.NFA class.
	
	One might think this could all be done inside class Encoder, but the
	treatment of name references differs.
	"""
	def __init__(self, names:dict):
		self.__names = names
	
	def visit_Letter(self, ltr:Letter): return charset.singleton(ltr.codepoint)
	def visit_CharSpecial(self, cs:CharSpecial): return cs.cls
	def visit_CharRange(self, cr:CharRange): return charset.range_class(cr.first, cr.last)
	def visit_CharUnion(self, cu:CharUnion): return charset.union(self.visit(cu.a), self.visit(cu.b))
	def visit_CharIntersection(self, ci:CharIntersection): return charset.intersect(self.visit(ci.a), self.visit(ci.b))
	def visit_CharComplement(self, cc:CharComplement): return charset.complement(self.visit(cc.inverse))
	def visit_NamedSubexpression(self, ns:NamedSubexpression):
		try: expr = self.__names[ns.name]
		except KeyError: raise BadReferenceError(ns.name, ns.trace)
		if isinstance(expr, (CharClass, NamedSubexpression)): return self.visit(expr)
		else: raise NonClassError(ns.name, ns.trace)
	