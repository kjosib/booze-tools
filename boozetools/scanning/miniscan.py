""" Hook regular expression patterns up to method calls on a scanner object. """
from ..support import interfaces
from ..parsing import miniparse
from . import regular, charset, recognition

PRELOAD = {'ASCII': {k: regular.CharClass(cls) for k, cls in charset.POSIX.items()}}

class PatternError(Exception): pass
class BadReferenceError(PatternError):
	"""
	Raised if a pattern refers to a subexpression name not defined in the context of the analysis.
	args are the offending reference and the span within the pattern (offset/length pair) where it appears.
	"""
class TrailingContextError(PatternError):
	"""
	Raised if pattern has both variable-sized stem and variable-sized trailing context.
	This is not supported at this time.
	"""


class Definition(interfaces.ScanRules):
	def __init__(self, *, minimize=True, mode='ASCII'):
		self.__actions = []
		self.__trails = []
		self.__subexpressions = PRELOAD[mode].copy()
		self.__dfa: regular.DFA = None
		self.__nfa = regular.NFA()
		self.__minimize = minimize
		self.__awaiting_action = False
	
	def default_initial_condition(self) -> str: pass
	def get_trailing_context(self, rule_id: int): return self.__trails[rule_id]
	
	def get_dfa(self) -> interfaces.FiniteAutomaton:
		if self.__dfa is None:
			if self.__awaiting_action: raise interfaces.MetaError('You forgot to provide the action for the final pattern!')
			self.__dfa = self.__nfa.subset_construction()
			if self.__minimize: self.__dfa = self.__dfa.minimize_states().minimize_alphabet()
		return self.__dfa
	
	def scan(self, text, *, start=None, env=None):
		scanner = recognition.Scanner(text=text, automaton=self.get_dfa(), rules=self, start=start)
		scanner.env = env
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
		expression.encode(src, dst, self.__nfa, rank)
		return rule_id
	
	def let(self, name:str, pattern:str): self.install_subexpression(name, rex.parse(META.scan(pattern, env=self.__subexpressions), language='Regular'))
	def on(self, pattern:str, *, condition=None, rank=0):
		"""
		For instance:
		scanner_definition.on('r#[^\n]+')(None) # Ignore comments
		@scanner_definition.on(r'[A-Za-z_]+')
		def word(scanner): return ('word', scanner.matched_text()) # Return a token.
		"""
		if self.__awaiting_action: raise interfaces.MetaError('You forgot to provide the action for the previous pattern!')
		self.__awaiting_action = True
		bol, expression, trail = analyze_pattern(pattern, self.__subexpressions)
		def decorator(fn):
			assert self.__awaiting_action
			self.__awaiting_action = False
			assert callable(fn) or isinstance(fn, str) or fn is None
			self.install_rule(action=fn, expression=expression, bol=bol, condition=condition, trail=trail, rank=rank)
			return fn
		return decorator
	def condition(self, *condition): return ConditionContext(self, *condition)
	def invoke(self, scan_state: interfaces.ScanState, rule_id:int):
		action = self.__actions[rule_id]
		if callable(action): return action(scan_state)
		if isinstance(action, str): return action, scan_state.matched_text()
		assert action is None

def analyze_pattern(pattern:str, env):
	scanner = META.scan(pattern, env=env)
	try: bol, expression, trailing_context = rex.parse(scanner)
	except BadReferenceError as e:
		pos,size = scanner.current_span()
		raise BadReferenceError("column %d: %r %s"%(pos+1, pattern[pos:pos+size], e.args[0]))
	assert isinstance(expression, regular.Regular)
	if not trailing_context: trail = None
	else:
		assert isinstance(trailing_context, regular.Regular), trailing_context
		stem, trail = expression.length(), trailing_context.length()
		expression = regular.Sequence(expression, trailing_context)
		if trail: trail = -trail
		elif stem: trail = stem
		else: raise TrailingContextError('Variable stem and variable trailing context in the same pattern are not presently supported.')
	return bol, expression, trail

class ConditionContext:
	""" I'd like to be able to use Python's context manager protocol to simplify writing definitions of scan conditions. """
	def __init__(self, definition:Definition, *condition):
		self.__definition = definition
		self.__condition = condition
	def __enter__(self): return self
	def __exit__(self, exc_type, exc_val, exc_tb): pass
	def on(self, pattern, *, rank=0): return self.__definition.on(pattern, condition=self.__condition, rank=rank)
	def install_rule(self, **kwargs): return self.__definition.install_rule(condition=self.__condition, **kwargs)


#########################
# A pattern parser is easy to build using the miniparse module:

rex = miniparse.MiniParse('Pattern', 'Regular')
rex.rule('Pattern', 'BOL Regular Trail')()
rex.rule('Pattern', 'BOL $')(lambda bol, eof:(bol, eof, None)) # To specify end-of-file rules without introducing yet another metacharacter
rex.rule('BOL', '')(lambda : (True, True))
rex.rule('BOL', '^')(lambda x: (False, True))
rex.rule('BOL', '^^')(lambda x: (True, False))
rex.rule('Trail', '')()
rex.rule('Trail', '$')()
rex.rule('Trail', '/ .Regular')()
rex.rule('Trail', '/ .Regular .$')(regular.Sequence)
rex.rule('Regular', 'Sequence')()
rex.rule('Regular', '.Regular | .Sequence')(regular.Alternation)
rex.rule('Sequence', 'Term')()
rex.rule('Sequence', 'Sequence Term')(regular.Sequence)
rex.rule('Term', 'Atom')()
rex.rule('Term', '.Atom ?')(regular.Hook)
rex.rule('Term', '.Atom *')(regular.Star)
rex.rule('Term', '.Atom +')(regular.Plus)
rex.rule('Term', '.Atom { .number }')(lambda a, n: regular.Counted(a, n, n))
rex.rule('Term', '.Atom { .number , }')(lambda a, n: regular.Counted(a, n, None))
rex.rule('Term', '.Atom { , .number }')(lambda a, n: regular.Counted(a, 0, n))
rex.rule('Term', '.Atom { .number , .number }')(lambda a, m, n: regular.Counted(a, m, n))
rex.rule('Atom', '( .Regular )')()
rex.rule('Atom', 'c')(lambda c: regular.CharClass([c, c + 1]))
rex.rule('Atom', 'reference')(None)
rex.rule('Atom', '[ .Class ]')(regular.CharClass)
rex.rule('Class', 'Conjunct')()
rex.rule('Class', '.Class && .Conjunct')(charset.intersect)
rex.rule('Conjunct', 'Members')()
rex.rule('Conjunct', '^ .Members')(charset.complement)
rex.rule('Members', 'Item')()
rex.rule('Members', 'Members Item')(charset.union)
rex.rule('Item', 'c')(charset.singleton)
rex.rule('Item', '.c - .c')(charset.range_class)
rex.rule('Item', 'short')(lambda c:c.cls)
@rex.rule('Item', 'reference')
def classref(subex: regular.Regular):
	if isinstance(subex, regular.CharClass): return subex.cls
	else: raise BadReferenceError('Reference is not to a character class, and so cannot be used within one.')

META = Definition()
def _BEGIN_():
	""" This is the bootstrapping routine: it builds the preload and the meta-scanner. """
	def seq(head, *tail):
		for t in tail: head = regular.Sequence(head, t)
		return head
	def txt(s):return seq(*(regular.CharClass(charset.singleton(ord(_))) for _ in s))
	
	def _metatoken(scanner):return scanner.matched_text(), None
	def _and_then(condition):
		def fn(scanner):
			scanner.enter(condition)
			return _metatoken(scanner)
		return fn
	def _instead(condition):
		def fn(scanner):
			scanner.less(0)
			scanner.enter(condition)
		return fn
	def _bracket_reference(scanner):
		name = scanner.matched_text()[1:-1]
		try: return 'reference', scanner.env[name]
		except KeyError: raise BadReferenceError("Undefined sub-pattern reference")
	def _shorthand_reference(scanner): return 'reference', scanner.env[scanner.matched_text()[1]]
	def _dot_reference(scanner): return 'reference', scanner.env['DOT']
	def _hex_escape(scanner): return 'c', int(scanner.matched_text()[2:], 16)
	def _control(scanner): return 'c', 31 & ord(scanner.matched_text()[2:])
	def _arbitrary_character(scanner): return 'c', ord(scanner.matched_text())
	def _class_initial_close_bracket(scanner):
		scanner.enter('[')
		return _arbitrary_character(scanner)
	def _arbitrary_escape(scanner): return 'c', ord(scanner.matched_text()[1:])
	def _number(scanner): return 'number', int(scanner.matched_text())
	
	dot = PRELOAD['ASCII']['DOT'] = regular.CharClass([0, 10, 14])
	for codepoint, char in [(0, '0'), (27, 'e'), *enumerate('abtnvfr', 7)]: PRELOAD['ASCII'][char] = regular.CharClass(
		charset.singleton(codepoint))
	for codepoint, mnemonic in enumerate('NUL SOH STX ETX EOT ENQ ACK BEL BS TAB LF VT FF CR SO SI DLE DC1 DC2 DC3 DC4 NAK SYN ETB CAN EM SUB ESC FS GS RS US SP'.split()):
		PRELOAD['ASCII'][mnemonic] = regular.CharClass(charset.singleton(codepoint))
	PRELOAD['ASCII']['DEL'] = regular.CharClass(charset.singleton(127))
	PRELOAD['ASCII']['ANY'] = regular.CharClass(charset.UNIVERSAL)
	PRELOAD['ASCII']['vertical'] = regular.CharClass([10, 14])
	PRELOAD['ASCII']['horizontal'] = regular.CharClass([8, 10, 32, 33])
	for shorthand, longhand in [
		('d', 'digit'),
		('l', 'alpha'),
		('w', 'word'),
		('s', 'space'),
		('h', 'horizontal'),
	]:
		PRELOAD['ASCII'][shorthand] = PRELOAD['ASCII'][longhand]
		PRELOAD['ASCII'][shorthand.upper()] = regular.CharClass(
			charset.subtract(dot.cls, PRELOAD['ASCII'][longhand].cls))
	def ref(x): return PRELOAD['ASCII'][x]
	
	eof_charclass = regular.CharClass(charset.EOF)
	dollar_charclass = regular.CharClass(charset.union(charset.EOF, PRELOAD['ASCII']['vertical'].cls))
	META.install_rule(expression=txt('^'), action=_metatoken, bol=(False, True))
	META.install_rule(expression=txt('^^'), action=_metatoken, bol=(False, True))
	# This next rule says that a dollar-sign at the end of a pattern supplies a regex matching EITHER end-of-line OR end-of-file
	META.install_rule(expression=seq(txt('$'), eof_charclass), trail=-1, action=lambda scanner:('$', dollar_charclass))
	# So I build another similar one for end-of-file rules: the string '<<EOF>>' appearing at the end of the pattern.
	# And by the way, the rex grammar (above) correctly directs such things to the trailing-context fork of the parse.
	META.install_rule(expression=seq(txt('<<EOF>>'), eof_charclass), trail=-1, action=lambda scanner:('$', eof_charclass))
	for c in '(|)?*+/': META.install_rule(expression=txt(c), action=_metatoken)
	META.install_rule(expression=txt('.'), action=_dot_reference)
	META.install_rule(expression=txt('{'), action=_and_then('{'))
	META.install_rule(expression=txt('['), action=_and_then('[.'))
	META.install_rule(expression=txt('[^'), trail=-1, action=_and_then('^'))
	META.install_rule(expression=txt('^'), condition='^', action=_and_then('[.'))
	with META.condition('[.') as start_class:
		start_class.install_rule(expression=txt(']'), action = _class_initial_close_bracket)
		start_class.install_rule(expression=txt('-'), action = _arbitrary_character)
		start_class.install_rule(expression=ref('ANY'), action = _instead('['))
	with META.condition('[') as in_class:
		in_class.install_rule(expression=txt(']'), action=_and_then(None))
		in_class.install_rule(expression=txt('&&'), action=_metatoken)
		in_class.install_rule(expression=txt('&&^'), trail=-1, action=_and_then('^'))
		in_class.install_rule(expression=txt('-'), action=_metatoken)
		in_class.install_rule(expression=txt('-]'), trail=-1, action=_arbitrary_character)
	with META.condition(None, '[') as anywhere:
		anywhere.install_rule(expression=seq(txt('{'), ref('alpha'), regular.Plus(ref('word')), txt('}'), ), action=_bracket_reference)
		whack = txt('\\')
		for c, n in [('x', 2), ('u', 4), ('U', 8)]: META.install_rule(expression=seq(whack, txt(c), regular.Counted(ref('xdigit'), n, n)), action=_hex_escape)
		anywhere.install_rule(expression=seq(whack, txt('c'), regular.CharClass([64, 128])), action=_control)
		anywhere.install_rule(expression=seq(whack, ref('alnum')), action=_shorthand_reference)
		anywhere.install_rule(expression=seq(whack, dot), action=_arbitrary_escape)
		anywhere.install_rule(expression=dot, action=_arbitrary_character)
	with META.condition('{') as brace:
		brace.install_rule(expression=regular.Plus(ref('digit')), action=_number)
		brace.install_rule(expression=txt(','), action=_metatoken)
		brace.install_rule(expression=txt('}'), action=_and_then(None))
	
	PRELOAD['ASCII']['R'] = rex.parse(META.scan(r'\r?\n|\r', env=PRELOAD['ASCII']), language='Regular')
_BEGIN_()
