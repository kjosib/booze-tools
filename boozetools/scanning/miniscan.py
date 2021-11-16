""" Hook regular expression patterns up to method calls on a scanner object. """
from ..support.interfaces import Scanner
from ..arborist import trees
from ..support import interfaces
from ..parsing import miniparse
from . import finite, regular, charset, recognition

char_prebuilt = regular.VOCAB['CharPrebuilt']
PRELOAD = {'ASCII': {k: char_prebuilt.leaf(cls) for k, cls in charset.mode_ascii.items()}}


class Definition:
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
		scanner = recognition.IterableScanner(text=text, automaton=self.get_dfa(), act=self.invoke, start=start, on_error=on_error)
		return scanner
		
	def install_subexpression(self, name:str, expression: trees.Node):
		assert isinstance(name, str) and name not in self.__subexpressions and len(name) > 1
		assert isinstance(expression, trees.Node), type(expression)
		self.__subexpressions[name] = expression
	
	def install_rule(self, *, action:callable, expression: trees.Node, bol=(True, True), condition: (str, list, tuple)=None, trail:int=None, rank:int=0) -> int:
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
		expression.tour(regular.Encoder(self.__nfa, rank, self.__subexpressions), src, dst)
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
		trail = self.get_trailing_context(rule_id)
		if trail is not None: yy.less(trail)

		action = self.__actions[rule_id]
		if callable(action): action(yy)
		else: assert action is None
	
def analyze_pattern(pattern_text, env):
	pattern = rex.parse(META.scan(pattern_text), language='Pattern')
	if pattern.symbol.label == 'pattern_regular': expression, trail = pattern['stem'], None
	elif pattern.symbol.label == 'pattern_only_trail': expression, trail = pattern['trail'], 0
	elif pattern.symbol.label == 'pattern_with_trail':
		sizer = regular.Sizer(env)
		stem, trail = pattern['stem'].tour(sizer), pattern['trail'].tour(sizer)
		expression = regular.VOCAB['Sequence'].from_args(pattern['stem'], pattern['trail'])
		if trail: trail = -trail
		elif stem: trail = stem
		else: raise regular.TrailingContextError('Variable stem and variable trailing context in the same pattern are not presently supported.')
	else: assert False, pattern.symbol.label
	return regular.LEFT_CONTEXT[pattern['left_context'].symbol.label], expression, trail

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
class RegexParser(miniparse.MiniParse):
	def did_not_recover(self):
		raise regular.PatternSyntaxError

	def __init__(self):
		super(RegexParser, self).__init__('Pattern', 'Regular')
		self.void_symbols.update('^ ^^ / | ? * + { } , ( ) [ - ] && ; whitespace'.split())
		for line in """
			Pattern: left_context Regular               :pattern_regular
			Pattern: left_context Regular right_context :pattern_with_trail
			Pattern: left_context right_context         :pattern_only_trail
			left_context:    :anywhere
			left_context: ^  :begin_line
			left_context: ^^ :mid_line
			right_context: end
			right_context: / Regular
			right_context: / Regular end :Sequence
			Regular: sequence
			Regular: Regular | sequence :Alternation
			sequence: term
			sequence: sequence term :Sequence
			term: atom
			term: atom ? :Hook
			term: atom * :Star
			term: atom + :Plus
			term: atom { number }          :n_times
			term: atom { number , }        :n_or_more
			term: atom { , number }        :n_or_fewer
			term: atom { number , number } :n_to_m
			atom: codepoint
			atom: reference
			atom: ( Regular )
			atom: [ class ]
			class: conjunct
			class: class && conjunct :CharIntersection
			conjunct: members
			conjunct: ^ members :CharComplement
			members: item
			members: members item :CharUnion
			item: codepoint
			item: codepoint - codepoint :CharRange
			item: reference
		""".splitlines():
			bits = [x.strip() for x in line.split(':')]
			if len(bits)==2: self.rule(*bits)()
			elif len(bits)==3:
				symbol = regular.VOCAB[bits.pop()]
				self.rule(*bits)(symbol.from_args)

def _BOOTSTRAP_REGEX_SCANNER_():
	""" This is the bootstrapping routine: it builds the preload and the meta-scanner. """
	def seq(head, *tail):
		for t in tail: head = regular.VOCAB['Sequence'].from_args(head, t)
		return head
	def txt(s):return seq(*(regular.VOCAB['Codepoint'].leaf(ord(_)) for _ in s))
	
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
		node = regular.VOCAB['NamedSubexpression'].leaf(name, yy.current_span())
		yy.token('reference', node)
	def _shorthand_reference(yy:interfaces.Scanner):
		yy.token('reference', regular.VOCAB['NamedSubexpression'].leaf(yy.matched_text()[1], yy.current_span()))
	def _dot_reference(yy:interfaces.Scanner):
		yy.token('reference', regular.VOCAB['NamedSubexpression'].leaf('DOT', yy.current_span()))
	def _hex_escape(yy): yy.token('codepoint', regular.VOCAB['Codepoint'].leaf(int(yy.matched_text()[2:], 16)))
	def _control(yy): yy.token('codepoint', regular.VOCAB['Codepoint'].leaf(31 & ord(yy.matched_text()[2:])))
	def _arbitrary_character(yy): yy.token('codepoint', regular.VOCAB['Codepoint'].leaf(ord(yy.matched_text())))
	def _class_initial_close_bracket(yy):
		yy.enter('in_class')
		_arbitrary_character(yy)
	def _class_final_dash(yy):
		yy.token('codepoint', ord('-'))
		yy.token(']', None)
		yy.enter(None)
	def _arbitrary_escape(yy): yy.token('codepoint', regular.VOCAB['Codepoint'].leaf(ord(yy.matched_text()[1:])))
	def _number(yy): yy.token('number', regular.VOCAB['Bound'].leaf(int(yy.matched_text())))
	def _dollar(charclass):
		def fn(yy:Scanner): yy.token('end', charclass)
		return fn
	def _meta_caret(yy):
		yy.token(yy.matched_text()[:-1], None)
		yy.token('^')
		yy.enter('start_class')
	
	def common_rules(ctx, *rules):
		for lit, act in rules: ctx.install_rule(expression=txt(lit), action=act)
	
	def ref(x): return PRELOAD['ASCII'][x]
	
	dot = ref('DOT')
	
	eof_charclass = regular.VOCAB['CharPrebuilt'].leaf(charset.EOF)
	dollar_charclass = regular.VOCAB['CharPrebuilt'].leaf(charset.union(charset.EOF, PRELOAD['ASCII']['vertical'].semantic))

	meta = Definition()

	for t in '^', '^^': meta.install_rule(expression=txt(t), action=_metatoken, bol=(False, True))
	for t,cc in ('$', dollar_charclass), ('<<EOF>>', eof_charclass):
		meta.install_rule(expression=seq(txt(t), eof_charclass), trail=-1, action=_dollar(cc))
	common_rules(meta,
		('.', _dot_reference),
		('{', _and_then('brace')),
		('[', _and_then('start_class')),
		('[^', _meta_caret),
		*((c, _metatoken) for c in '(|)?*+/'),
	)
	common_rules(meta.condition('in_class'),
		(']', _and_then(None)),
		('&&', _metatoken),
		('&&^', _meta_caret),
		('-', _metatoken),
		('-]', _class_final_dash),
	)
	with meta.condition('start_class') as start_class:
		common_rules(start_class, (']', _class_initial_close_bracket), ('-', _arbitrary_character),)
		start_class.install_rule(expression=ref('ANY'), action = _instead('in_class'))
	with meta.condition(None, 'in_class') as anywhere:
		anywhere.install_rule(expression=seq(txt('{'), ref('alpha'), regular.VOCAB['Plus'].from_args(ref('word')), txt('}'), ), action=_bracket_reference)
		whack = txt('\\') # NB: Python doesn't let you end a raw-string with a backslash.
		for c, n in [('x', 2), ('u', 4), ('U', 8)]:
			hexblock = regular.VOCAB['n_times'].from_args(ref('xdigit'), regular.VOCAB['Bound'].leaf(n))
			anywhere.install_rule(expression=seq(whack, txt(c), hexblock), action=_hex_escape)
		anywhere.install_rule(expression=seq(whack, txt('codepoint'), regular.VOCAB['CharPrebuilt'].leaf(charset.range_class(64, 127))), action=_control)
		anywhere.install_rule(expression=seq(whack, ref('alnum')), action=_shorthand_reference)
		anywhere.install_rule(expression=seq(whack, dot), action=_arbitrary_escape)
		anywhere.install_rule(expression=dot, action=_arbitrary_character)
	with meta.condition('brace') as brace:
		brace.install_rule(expression=regular.VOCAB['Plus'].from_args(ref('digit')), action=_number)
		common_rules(brace, (',', _metatoken), ('}', _and_then(None)),)
	return meta

rex = RegexParser()
META = _BOOTSTRAP_REGEX_SCANNER_()
PRELOAD['ASCII']['R'] = rex.parse(META.scan(r'\r?\n|\r'), language='Regular')

