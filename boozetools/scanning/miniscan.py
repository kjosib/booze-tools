""" Hook regular expression patterns up to method calls on a scanner object. """

from . import finite, charset
from .interface import Bindings
from .engine import Scanner, IterableScanner
from .regular import Encoder, RulePattern, analyze_pattern, let_subexpression


class Definition(Bindings):
	def __init__(self, name="MiniScan Definition", *, minimize=True):
		self.__actions = []
		self.__trails = []
		self.__subex = charset.mode_normal.new_child(name)
		self.__leaves = {}
		self.__dfa = None
		self.__nfa = finite.NFA()
		self.__minimize = minimize
		self.__awaiting_action = False
	
	def get_trailing_context(self, rule_id: int): return self.__trails[rule_id]
	
	def get_dfa(self):
		if self.__dfa is None:
			if self.__awaiting_action: raise AssertionError('You forgot to provide the action for the final pattern!')
			self.__dfa = self.__nfa.subset_construction()
			if self.__minimize: self.__dfa = self.__dfa.minimize_states().minimize_alphabet()
		return self.__dfa
	
	def scan(self, text, *, start=None):
		return IterableScanner(text, self.get_dfa(), self, start=start)
		
	def __install_rule(self, *, action:callable, program: RulePattern, condition: (str, list, tuple)=None, rank:int=0) -> int:
		rule_id = len(self.__actions)
		self.__actions.append(action)
		self.__trails.append(program.trail_code)
		dst = self.__nfa.new_node(rank)
		self.__nfa.final[dst] = rule_id
		if condition is None or isinstance(condition, str): condition = [condition]
		else: assert isinstance(condition, (tuple, list)), type(condition)
		
		src = Encoder(self.__nfa, rank=rank, annotation=program.annotation)(program.tree, dst)
		for C in condition:
			for q, b in zip(self.__nfa.condition(C), program.bol):
				if b: self.__nfa.link_epsilon(q,src)
		return rule_id
	
	def let(self, name:str, pattern:str):
		
		let_subexpression(self.__subex, name, pattern)

	def token(self, kind:str, pattern:str, *, rank=0, condition=None):
		""" This says every member of the pattern has token kind=kind and semantic=matched text. """
		@self.on(pattern, rank=rank, condition=condition)
		def action(yy:IterableScanner): yy.token(kind, yy.match())
	
	def token_map(self, kind:str, pattern:str, fn:callable, *, rank=0, condition=None):
		""" Every member of the pattern has token kind=kind and semantic=fn(matched text). """
		@self.on(pattern, rank=rank, condition=condition)
		def action(yy:IterableScanner): yy.token(kind, fn(yy.match()))

	def ignore(self, pattern:str, *, rank=0, condition=None):
		""" Tell Scanner to ignore what matches the pattern. """
		@self.on(pattern, rank=rank, condition=condition)
		def action(yy:IterableScanner): pass

	def on(self, pattern:str, *, condition=None, rank=0):
		"""
		For instance:
		scanner_definition.on('r#[^\n]+')(None) # Ignore comments
		@scanner_definition.on(r'[A-Za-z_]+')
		def word(yy): yy.token('word', scanner.match())
		"""
		if self.__awaiting_action: raise AssertionError('You forgot to provide the action for the previous pattern!')
		self.__awaiting_action = True
		program = analyze_pattern(pattern, self.__subex)
		def decorator(fn):
			assert self.__awaiting_action
			self.__awaiting_action = False
			assert callable(fn)
			self.__install_rule(action=fn, program=program, condition=condition, rank=rank)
			return fn
		return decorator
	def condition(self, *condition): return ConditionContext(self, *condition)
	
	def on_match(self, yy: Scanner, rule_id:int):
		yy.less(self.get_trailing_context(rule_id))
		action = self.__actions[rule_id]
		if callable(action): action(yy)
		else: assert action is None
	
class ConditionContext:
	""" I'd like to be able to use Python's context manager protocol to simplify writing definitions of scan conditions. """
	def __init__(self, definition:Definition, *condition):
		self.__definition = definition
		self.__condition = condition
	def __enter__(self): return self
	def __exit__(self, exc_type, exc_val, exc_tb): pass
	def on(self, pattern, *, rank=0): return self.__definition.on(pattern, rank=rank, condition=self.__condition)
	def token(self, kind:str, pattern:str, *, rank=0): self.__definition.token(kind, pattern, rank=rank, condition=self.__condition)
	def token_map(self, kind:str, pattern:str, fn:callable, *, rank=0): self.__definition.token_map(kind, pattern, fn, rank=rank, condition=self.__condition)
	def ignore(self, pattern:str, *, rank=0): self.__definition.ignore(pattern, rank=rank, condition=self.__condition)

