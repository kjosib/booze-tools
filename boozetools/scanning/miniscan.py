""" Hook regular expression patterns up to method calls on a scanner object. """
from boozetools.support.interfaces import Scanner

from ..support import interfaces
from ..parsing import miniparse
from . import finite, regular, charset, recognition

PRELOAD = {'ASCII': {k: regular.CharSpecial(cls) for k, cls in charset.mode_ascii.items()}}


class Definition(interfaces.ScanRules):
	def __init__(self, *, minimize=True, mode='ASCII'):
		self.__actions = []
		self.__trails = []
		self.__subexpressions = PRELOAD[mode].copy()
		self.__dfa: finite.DFA = None
		self.__nfa = finite.NFA()
		self.__minimize = minimize
		self.__awaiting_action = False
	
	def get_trailing_context(self, rule_id: int): return self.__trails[rule_id]
	
	def get_dfa(self) -> interfaces.FiniteAutomaton:
		if self.__dfa is None:
			if self.__awaiting_action: raise AssertionError('You forgot to provide the action for the final pattern!')
			self.__dfa = self.__nfa.subset_construction()
			if self.__minimize: self.__dfa = self.__dfa.minimize_states().minimize_alphabet()
		return self.__dfa
	
	def scan(self, text, *, start=None, on_error:interfaces.ScanErrorListener = None):
		if on_error is None: on_error = interfaces.ScanErrorListener()
		scanner = recognition.IterableScanner(text=text, automaton=self.get_dfa(), rules=self, start=start, on_error=on_error)
		return scanner
		
	def install_subexpression(self, name:str, expression: regular.Regular):
		assert isinstance(name, str) and name not in self.__subexpressions and len(name) > 1
		assert isinstance(expression, regular.Regular)
		self.__subexpressions[name] = expression
	
	def install_rule(self, *, action:callable, expression: regular.Regular, bol=(True, True), condition: (str, list, tuple)=None, trail:int=None, rank:int=0) -> int:
		rule_id = len(self.__actions)
		self.__actions.append(action)
		self.__trails.append(trail)
		src = self.__nfa.new_node(rank)
		dst = self.__nfa.new_node(rank)
		if condition is None or isinstance(condition, str): condition = [condition]
		else: assert isinstance(condition, (tuple, list)), type(condition)
		for C in condition:
			for q, b in zip(self.__nfa.condition(C), bol):
				if b: self.__nfa.link_epsilon(q,src)
		self.__nfa.final[dst] = rule_id
		regular.Encoder(self.__nfa, rank, self.__subexpressions).visit(expression, src, dst)
		return rule_id
	
	def let(self, name:str, pattern:str):
		self.install_subexpression(name, rex.parse(META.scan(pattern), language='Regular'))
	
	def token(self, kind:str, pattern:str, *, rank=0, condition=None):
		""" This says every member of the pattern has token kind=kind and semantic=matched text. """
		@self.on(pattern, rank=rank, condition=condition)
		def action(yy:Scanner): yy.token(kind, yy.matched_text())
	
	def token_map(self, kind:str, pattern:str, fn:callable, *, rank=0, condition=None):
		""" Every member of the pattern has token kind=kind and semantic=fn(matched text). """
		@self.on(pattern, rank=rank, condition=condition)
		def action(yy:Scanner): yy.token(kind, fn(yy.matched_text()))

	def ignore(self, pattern:str, *, rank=0, condition=None):
		""" Tell Scanner to ignore what matches the pattern. """
		@self.on(pattern, rank=rank, condition=condition)
		def action(yy:Scanner): pass

	def on(self, pattern:str, *, condition=None, rank=0):
		"""
		For instance:
		scanner_definition.on('r#[^\n]+')(None) # Ignore comments
		@scanner_definition.on(r'[A-Za-z_]+')
		def word(yy): yy.token('word', scanner.matched_text())
		"""
		if self.__awaiting_action: raise AssertionError('You forgot to provide the action for the previous pattern!')
		self.__awaiting_action = True
		bol, expression, trail = analyze_pattern(pattern, self.__subexpressions)
		def decorator(fn):
			assert self.__awaiting_action
			self.__awaiting_action = False
			assert callable(fn)
			self.install_rule(action=fn, expression=expression, bol=bol, condition=condition, trail=trail, rank=rank)
			return fn
		return decorator
	def condition(self, *condition): return ConditionContext(self, *condition)
	
	def invoke(self, yy: interfaces.Scanner, rule_id:int):
		action = self.__actions[rule_id]
		if callable(action): action(yy)
		else: assert action is None
	


def analyze_pattern(pattern:str, env):
	scanner = META.scan(pattern)
	bol, expression, trailing_context = rex.parse(scanner)
	assert isinstance(expression, regular.Regular)
	if not trailing_context: trail = None
	else:
		assert isinstance(trailing_context, regular.Regular), trailing_context
		sizer = regular.Sizer(env)
		stem, trail = sizer.visit(expression), sizer.visit(trailing_context)
		expression = regular.Sequence(expression, trailing_context)
		if trail: trail = -trail
		elif stem: trail = stem
		else: raise regular.TrailingContextError('Variable stem and variable trailing context in the same pattern are not presently supported.')
	return bol, expression, trail

class ConditionContext:
	""" I'd like to be able to use Python's context manager protocol to simplify writing definitions of scan conditions. """
	def __init__(self, definition:Definition, *condition):
		self.__definition = definition
		self.__condition = condition
	def __enter__(self): return self
	def __exit__(self, exc_type, exc_val, exc_tb): pass
	def on(self, pattern, *, rank=0): return self.__definition.on(pattern, rank=rank, condition=self.__condition)
	def install_rule(self, **kwargs): return self.__definition.install_rule(condition=self.__condition, **kwargs)
	def token(self, kind:str, pattern:str, *, rank=0): self.__definition.token(kind, pattern, rank=rank, condition=self.__condition)
	def token_map(self, kind:str, pattern:str, fn:callable, *, rank=0): self.__definition.token_map(kind, pattern, fn, rank=rank, condition=self.__condition)
	def ignore(self, pattern:str, *, rank=0): self.__definition.ignore(pattern, rank=rank, condition=self.__condition)

#########################
# A pattern parser is easy to build using the miniparse module:

rex = miniparse.MiniParse('Pattern', 'Regular')
rex.void_symbols.update('^ ^^ / | ? * + { } , ( ) [ - ] &&'.split())
rex.rule('Pattern', 'BOL Regular Trail')()
rex.rule('Pattern', 'BOL $')(lambda bol, eof:(bol, eof, None)) # To specify end-of-file rules without introducing yet another metacharacter
rex.rule('BOL', '')(lambda : (True, True))
rex.rule('BOL', '^')(lambda : (False, True))
rex.rule('BOL', '^^')(lambda : (True, False))
rex.rule('Trail', '')()
rex.rule('Trail', '$')()
rex.rule('Trail', '/ Regular')()
rex.rule('Trail', '/ Regular $')(regular.Sequence)
rex.rule('Regular', 'Sequence')()
rex.rule('Regular', 'Regular | Sequence')(regular.Alternation)
rex.rule('Sequence', 'Term')()
rex.rule('Sequence', 'Sequence Term')(regular.Sequence)
rex.rule('Term', 'Atom')()
rex.rule('Term', 'Atom ?')(regular.Hook)
rex.rule('Term', 'Atom *')(regular.Star)
rex.rule('Term', 'Atom +')(regular.Plus)
rex.rule('Term', 'Atom { number }')(lambda a, n: regular.Counted(a, n, n))
rex.rule('Term', 'Atom { number , }')(lambda a, n: regular.Counted(a, n, None))
rex.rule('Term', 'Atom { , number }')(lambda a, n: regular.Counted(a, 0, n))
rex.rule('Term', 'Atom { number , number }')(lambda a, m, n: regular.Counted(a, m, n))
rex.rule('Atom', '( Regular )')()
rex.rule('Atom', 'c')(regular.Letter)
rex.rule('Atom', 'reference')()
rex.rule('Atom', '[ Class ]')()
rex.rule('Class', 'Conjunct')()
rex.rule('Class', 'Class && Conjunct')(regular.CharIntersection)
rex.rule('Conjunct', 'Members')()
rex.rule('Conjunct', '^ Members')(regular.CharComplement)
rex.rule('Members', 'Item')()
rex.rule('Members', 'Members Item')(regular.CharUnion)
rex.rule('Item', 'c')(regular.Letter)
rex.rule('Item', 'c - c')(regular.CharRange)
rex.rule('Item', 'short')()
rex.rule('Item', 'reference')()

META = Definition()
def _BEGIN_():
	""" This is the bootstrapping routine: it builds the preload and the meta-scanner. """
	def seq(head, *tail):
		for t in tail: head = regular.Sequence(head, t)
		return head
	def txt(s):return seq(*(regular.CharSpecial(charset.singleton(ord(_))) for _ in s))
	
	def _metatoken(yy): yy.token(yy.matched_text(), None)
	def _and_then(condition):
		def fn(yy):
			_metatoken(yy)
			yy.enter(condition)
		return fn
	def _instead(condition):
		def fn(yy):
			yy.less(0)
			yy.enter(condition)
		return fn
	def _bracket_reference(yy:interfaces.Scanner):
		name = yy.matched_text()[1:-1]
		node = regular.NamedSubexpression(name, yy.current_span())
		yy.token('reference', node)
	def _shorthand_reference(yy:interfaces.Scanner):
		yy.token('reference', regular.NamedSubexpression(yy.matched_text()[1], yy.current_span()))
	def _dot_reference(yy:interfaces.Scanner):
		yy.token('reference', regular.NamedSubexpression('DOT', yy.current_span()))
	def _hex_escape(yy): yy.token('c', int(yy.matched_text()[2:], 16))
	def _control(yy): yy.token('c', 31 & ord(yy.matched_text()[2:]))
	def _arbitrary_character(yy): yy.token('c', ord(yy.matched_text()))
	def _class_initial_close_bracket(yy):
		yy.enter('in_class')
		_arbitrary_character(yy)
	def _class_final_dash(yy):
		yy.token('c', ord('-'))
		yy.token(']', None)
		yy.enter(None)
	def _arbitrary_escape(yy): yy.token('c', ord(yy.matched_text()[1:]))
	def _number(yy): yy.token('number', int(yy.matched_text()))
	def _dollar(charclass):
		def fn(yy:Scanner): yy.token('$', charclass)
		return fn
	def _meta_caret(yy):
		yy.token(yy.matched_text()[:-1], None)
		yy.token('^')
		yy.enter('start_class')
	
	def common_rules(ctx, *rules):
		for lit, act in rules: ctx.install_rule(expression=txt(lit), action=act)
	
	def ref(x): return PRELOAD['ASCII'][x]
	
	dot = ref('DOT')
	
	eof_charclass = regular.CharSpecial(charset.EOF)
	dollar_charclass = regular.CharSpecial(charset.union(charset.EOF, PRELOAD['ASCII']['vertical'].cls))
	
	for t in '^', '^^': META.install_rule(expression=txt(t), action=_metatoken, bol=(False, True))
	for t,cc in ('$', dollar_charclass), ('<<EOF>>', eof_charclass):
		META.install_rule(expression=seq(txt(t), eof_charclass), trail=-1, action=_dollar(cc))
	common_rules(META,
		('.', _dot_reference),
		('{', _and_then('brace')),
		('[', _and_then('start_class')),
		('[^', _meta_caret),
		*((c, _metatoken) for c in '(|)?*+/'),
	)
	common_rules(META.condition('in_class'),
		(']', _and_then(None)),
		('&&', _metatoken),
		('&&^', _meta_caret),
		('-', _metatoken),
		('-]', _class_final_dash),
	)
	with META.condition('start_class') as start_class:
		common_rules(start_class, (']', _class_initial_close_bracket), ('-', _arbitrary_character),)
		start_class.install_rule(expression=ref('ANY'), action = _instead('in_class'))
	with META.condition(None, 'in_class') as anywhere:
		anywhere.install_rule(expression=seq(txt('{'), ref('alpha'), regular.Plus(ref('word')), txt('}'), ), action=_bracket_reference)
		whack = txt('\\')
		for c, n in [('x', 2), ('u', 4), ('U', 8)]:
			META.install_rule(expression=seq(whack, txt(c), regular.Counted(ref('xdigit'), n, n)), action=_hex_escape)
		anywhere.install_rule(expression=seq(whack, txt('c'), regular.CharSpecial(charset.range_class(64, 127))), action=_control)
		anywhere.install_rule(expression=seq(whack, ref('alnum')), action=_shorthand_reference)
		anywhere.install_rule(expression=seq(whack, dot), action=_arbitrary_escape)
		anywhere.install_rule(expression=dot, action=_arbitrary_character)
	with META.condition('brace') as brace:
		brace.install_rule(expression=regular.Plus(ref('digit')), action=_number)
		common_rules(brace, (',', _metatoken), ('}', _and_then(None)),)
	
	PRELOAD['ASCII']['R'] = rex.parse(META.scan(r'\r?\n|\r'), language='Regular')
_BEGIN_()
