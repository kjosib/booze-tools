""" No frills. Plenty useful. """

import inspect
import sys

from . import automata, shift_reduce
from .interface import ParseErrorListener, SemanticError
from .context_free import Rule, SemanticAction, ContextFreeGrammar, LEFT, RIGHT, NONASSOC
from .all_methods import PARSE_TABLE_METHODS

class MiniParse(ParseErrorListener):
	""" Connects BNF production rules directly to Python functions. No frills. Very useful as-is. """
	def __init__(self, *start, method='LALR', strict=False):
		self.__grammar = ContextFreeGrammar()
		self.__grammar.start.extend(start)
		self.__attrribute = []
		self.__hfa: automata.DragonBookTable = None
		self.__combine = None
		self.__awaiting_action = False
		self.__method = method
		self.__strict = strict
		self.void_symbols = set() # These won't get picked up as arguments.
	
	def left(self, symbols:list): self.__grammar.assoc(LEFT, symbols)
	def right(self, symbols:list): self.__grammar.assoc(RIGHT, symbols)
	def nonassoc(self, symbols:list): self.__grammar.assoc(NONASSOC, symbols)
	
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
	
	def rule(self, lhs:str, rhs_str:str, prec_sym=None):
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
		assert not self.__awaiting_action, "You forgot to provide the action for the prior production rule."
		self.__awaiting_action = True
		rhs, offsets = self.__analyze(rhs_str)
		def decorate(fn=None):
			hash(fn) # Because later it will need to be hashable; push failures to the fore.
			assert self.__awaiting_action
			self.__awaiting_action = False
			if fn is None:
				if len(rhs) == 1: action = 0 # Unit/renaming rule
				elif len(offsets) == 1: action = offsets[0]  # Bracketing rule
				else: action = SemanticAction(_collect_tuple, offsets)
			else: action = SemanticAction(fn, offsets)
			previous_frame = inspect.currentframe().f_back
			rule = Rule(lhs, rhs, prec_sym, action, inspect.getframeinfo(previous_frame)[:2])
			self.__grammar.add_rule(rule)
			return fn
		return decorate
	
	def renaming(self, lhs:str, *alternatives):
		"""
		Facilitates those "X => A | B | C | D" type rules you often find in real grammars.
		"""
		assert not self.__awaiting_action, "You forgot to provide the action for the prior production rule."
		for branch in alternatives:
			rhs, offsets = self.__analyze(branch)
			if len(rhs) == 1: action = 0  # Unit/renaming rule
			elif len(offsets) == 1: action = offsets[0]  # Bracketing rule
			else: raise AssertionError('%r is not a single-member branch -- although you could prepend the significant member with a dot ( like .this ) to fix it.' % branch)
			previous_frame = inspect.currentframe().f_back
			rule = Rule(lhs, rhs, None, action, inspect.getframeinfo(previous_frame)[:2])
			self.__grammar.add_rule(rule)
	
	def display(self): self.__grammar.display()

	def get_hfa_and_combine(self):
		if self.__hfa is None:
			if self.__awaiting_action: raise AssertionError('You forgot to provide the action for the final production rule.')
			self.__grammar.validate()
			self.__hfa = automata.tabulate(PARSE_TABLE_METHODS[self.__method](self.__grammar), self.__grammar,
										   style=automata.DeterministicStyle(self.__strict))
			constructors = self.__hfa.constructors
			def combine(constructor_id, args):
				try: return constructors[constructor_id](*args)
				except SemanticError as ex: raise ex from None
				except Exception as ex:
					message = self.__hfa.get_constructor(constructor_id)
					file_path = inspect.getfile(message)
					line_number = 1+inspect.findsource(message)[1]
					return self.exception_parsing(ex, file_path, line_number, args)
			self.__combine = combine
		return self.__hfa, self.__combine

	def parse(self, each_token, *, language=None):
		hfa, combine = self.get_hfa_and_combine()
		return shift_reduce.parse(hfa, combine, each_token, language=language, on_error=self)
	
	@staticmethod
	def exception_parsing(ex:Exception, file_path, line_number, args):
		print("\n---\nWhile trying to call %s:%d"%(file_path, line_number), file=sys.stderr)
		raise ex
	
def _collect_tuple(*items): return items
