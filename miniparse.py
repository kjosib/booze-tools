""" No frills. Plenty useful. """

import context_free, algorithms

class MiniParse:
	""" Connects BNF production rules directly to Python functions. No frills. Very useful as-is. """
	def __init__(self, *start):
		self.__start = start
		self.__grammar = context_free.ContextFreeGrammar()
		self.__hfa:context_free.DragonBookTable = None
	
	def left(self, symbols:list): self.__grammar.assoc(context_free.LEFT, symbols)
	def right(self, symbols:list): self.__grammar.assoc(context_free.RIGHT, symbols)
	def nonassoc(self, symbols:list): self.__grammar.assoc(context_free.NONASSOC, symbols)
	
	@staticmethod
	def __analyze(rhs):
		rhs = rhs.split()
		args = []
		for i,symbol in enumerate(rhs):
			if symbol.startswith('.'):
				rhs[i] = symbol[1:]
				args.append(i)
		if not args: args = range(len(rhs)) # Pick up everything if nothing is special.
		return tuple(rhs), tuple(x-len(rhs) for x in args)
	
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
		rhs, offsets = MiniParse.__analyze(rhs)
		def decorate(fn=None):
			if fn is None:
				if len(rhs) == 1: message = None # Unit/renaming rule
				elif len(offsets) == 1: message = ((lambda x:x), offsets) # Bracketing rule
				else: message = (lambda *x:x, offsets) # Tuple collection rule
			else: message = (fn, offsets)
			self.__grammar.rule(lhs, rhs, message, prec_sym)
		return decorate
	def display(self): self.__grammar.display()
	def get_hfa(self):
		if self.__hfa is None:
			self.__grammar.validate(self.__start)
			self.__hfa = self.__grammar.lalr_construction(self.__start)
		return self.__hfa
	def parse(self, each_token, *, language=None):
		return algorithms.parse(self.get_hfa(), MiniParse.combine, each_token, language=language)
	
	@staticmethod
	def combine(message, attribute_stack:list):
		fn, offsets = message
		return fn(*(attribute_stack[x] for x in offsets))
