""" No frills. Plenty useful. """

from ..support import interfaces, foundation
from . import automata, context_free, shift_reduce


class MiniParse(interfaces.ParseErrorListener):
	""" Connects BNF production rules directly to Python functions. No frills. Very useful as-is. """
	def __init__(self, *start, method='LALR', strict=False):
		self.__grammar = context_free.ContextFreeGrammar()
		self.__grammar.start.extend(start)
		self.__hfa: automata.DragonBookTable = None
		self.__combine = None
		self.__awaiting_action = False
		self.__method = method
		self.__strict = strict
		self.void_symbols = set() # These won't get picked up as arguments.
	
	def left(self, symbols:list): self.__grammar.assoc(context_free.LEFT, symbols)
	def right(self, symbols:list): self.__grammar.assoc(context_free.RIGHT, symbols)
	def nonassoc(self, symbols:list): self.__grammar.assoc(context_free.NONASSOC, symbols)
	
	def __analyze(self, rhs):
		rhs = rhs.split()
		args = []
		for i,symbol in enumerate(rhs):
			if symbol.startswith('.'):
				rhs[i] = symbol[1:]
				args.append(i)
		if not args: # Pick up non-void symbols if no dotted symbols appear in the right-hand side.
			args = tuple(i for i, symbol in enumerate(rhs) if symbol not in self.void_symbols)
		return tuple(rhs), args
	
	def rule(self, lhs:str, rhs:str, prec_sym=None):
		"""
		Decorates a callable as applying when the given rule is recognized.
		Prefix significant arguments with ., or get the whole right-hand side passed as arguments.
		For renaming and bracketing rules, call as
			foo.rule('expr', '( .expr )')(None)
		For normal rules, call as
			@foo.rule('expr', '.expr + .expr')
			def add(a,b): return a+b
		"""
		assert self.__hfa is None
		if self.__awaiting_action: raise AssertionError('You forgot to provide the action for the prior production rule.')
		self.__awaiting_action = True
		rhs, offsets = self.__analyze(rhs)
		def decorate(fn=None):
			assert self.__awaiting_action
			self.__awaiting_action = False
			if fn is None:
				if len(rhs) == 1: con,plc = None,0 # Unit/renaming rule
				elif len(offsets) == 1: con,plc = None, offsets[0]  # Bracketing rule
				else: con,plc = _collect_tuple, offsets
			else: con,plc = fn, offsets
			self.__grammar.rule(lhs, rhs, prec_sym, con,plc, None)
			return fn
		return decorate
	
	def renaming(self, lhs:str, *alternatives):
		"""
		Facilitates those "X => A | B | C | D" type rules you often find in real grammars.
		"""
		if self.__awaiting_action: raise AssertionError('You forgot to provide the action for the prior production rule.')
		for branch in alternatives:
			rhs, offsets = self.__analyze(branch)
			if len(rhs) == 1: con, plc = None, 0  # Unit/renaming rule
			elif len(offsets) == 1: con, plc = None, offsets[0]  # Bracketing rule
			else: raise AssertionError('%r is not a single-member branch -- although you could prepend the significant member with a dot ( like .this ) to fix it.' % branch)
			self.__grammar.rule(lhs, rhs, None, con, plc, None)
	
	def display(self): self.__grammar.display()

	def get_hfa_and_combine(self):
		if self.__hfa is None:
			if self.__awaiting_action: raise AssertionError('You forgot to provide the action for the final production rule.')
			self.__grammar.validate()
			self.__hfa = automata.tabulate(
				automata.PARSE_TABLE_METHODS[self.__method](self.__grammar),
				style=automata.DeterministicStyle(self.__strict),
			)
			constructors = self.__hfa.constructors
			self.__combine = lambda cid,args:constructors[cid](*args)
		return self.__hfa, self.__combine

	def parse(self, each_token, *, language=None):
		hfa, combine = self.get_hfa_and_combine()
		return shift_reduce.parse(hfa, combine, each_token, language=language, on_error=self)
	
def _collect_tuple(*items): return items
