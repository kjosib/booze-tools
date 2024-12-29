"""
Of particular importance to my cause is a proper bootstrap.
For example, I could hand-roll a recursive-descent parser for regular expressions,
but that would be at odds with the presumed benefits of parser-generation machinery.
The approach taken here is to extract a full-strength system nearly for free.
"""

from typing import NamedTuple, Optional, Any
from ..support import foundation
from ..support.failureprone import SourceText, Issue, Evidence, Severity, illustration
from ..support.treelang import RankedAlphabet, StrictPass, SparseRewrite
from ..support.symtab import NameSpace, NoSuchSymbol
from .interface import Bindings, RuleId
from . import charset
from .finite import NFA
from .engine import IterableScanner
from ..parsing.context_free import ContextFreeGrammar, Rule, SemanticAction
from ..parsing.interface import ParseError
from ..parsing import shift_reduce
from ..parsing.lalr import lalr_construction
from ..parsing.automata import tabulate, DeterministicStyle

class PatternError(Exception):
	gripe = "Malformed pattern."
class VariableTrailingContextError(PatternError):
	gripe = "Variable size for both stem and trailing context in the same pattern is not currently supported."
class NameTooShort(Exception): pass


VOCAB = RankedAlphabet("Rule", "Char", "Cls", "Regex", "LeftContext", "Number", "Codepoint")

VOCAB.symbol("pattern_regular", "Rule", left_context="LeftContext", stem="Regex")
VOCAB.symbol("pattern_with_right_context", "Rule", left_context="LeftContext", stem="Regex", right_context="Regex")
VOCAB.symbol("pattern_only_right_context", "Rule", left_context="LeftContext", right_context="Regex")

VOCAB.symbol("sequence", "Regex", a="Regex", b="Regex")
VOCAB.symbol("alternation", "Regex", a="Regex", b="Regex")

VOCAB.symbol("star", "Regex", sub="Regex")
VOCAB.symbol("hook", "Regex", sub="Regex")
VOCAB.symbol("plus", "Regex", sub="Regex")

VOCAB.symbol("n_times", "Regex", sub="Regex", count="Number")
VOCAB.symbol("n_or_more", "Regex", sub="Regex", min="Number")
VOCAB.symbol("n_or_fewer", "Regex", sub="Regex", max="Number")
VOCAB.symbol("n_to_m", "Regex", sub="Regex", min="Number", max="Number")

VOCAB.symbol("cls", "Regex", members="Cls")
VOCAB.symbol("initial_minus", "Cls")

VOCAB.symbol("singleton", "Cls", item="Codepoint")
VOCAB.symbol("range", "Cls", first="Codepoint", last="Codepoint")
VOCAB.symbol("union", "Cls", a="Cls", b="Cls")
VOCAB.symbol("intersection", "Cls", a="Cls", b="Cls")
VOCAB.symbol("subtraction", "Cls", a="Cls", b="Cls")
VOCAB.symbol("complement", "Cls", inverse="Cls")

# Terminals from here down:
VOCAB.symbol("epsilon", "Regex")
VOCAB.symbol("name", "Regex", "Cls")
VOCAB.symbol("shorthand", "Regex", "Cls")
VOCAB.symbol("literal", "Regex", "Codepoint")
VOCAB.symbol("end", "Regex", "Codepoint")
VOCAB.symbol("escape", "Regex", "Codepoint")
VOCAB.symbol("control", "Regex", "Codepoint")
VOCAB.symbol("hex_point", "Regex", "Codepoint")
VOCAB.symbol("number", "Number")
VOCAB.symbol("dot", "Regex")

VOCAB.symbol("anywhere", "LeftContext")
VOCAB.symbol("begin_line", "LeftContext")
VOCAB.symbol("mid_line", "LeftContext")

# Internal-Use-Only Symbols:
VOCAB.symbol("codepoint_", "Regex", "Codepoint", trace="Codepoint")

#################################################
#
#  Now I can describe a translation strategy.
#
# 1. Convert all literals, escapes, controls, and hex-points to their respective codepoint ordinals.
#    This may imply adding a generic symbol "codepoint" and subtracting other members of the category.
# 2. Evaluate numbers. Check that n_to_m items make sense, in the sense of min <= max.
# 3. Look up names and shorthands from the environment and check for acceptability within character classes.
#    - Everything from here up involves taking extracts from the text. Henceforth, we don't need it.
# 4. Adjust for right-context in rule-pattern, which may involve checking the sizes of stem and right_context.
# --- At this point, you can drop positional information: Conversion can no longer fail. ---
# 5. Do something about the alphabet. For example, turn singletons into trivial character classes.
# 6. Optionally, bottom-up, convert alternations-of-classes into single classes. This may save time later.
# 7. The actual NFA encoding process should follow the advice at https://swtch.com/~rsc/regexp/regexp1.htm
#    To wit: Treat the destination-state as an inherited attribute, and the source-state as a synthesized one.
# 8. The usual procedure to make a minimal DFA with a minimal alphabet.
#
# There is some freedom to shift and merge portions of this stuff. For example, to add case-folding
# as a flag on the parentheses, I'd use an inherited attribute to control converting literal letters.

class Annotation(NamedTuple):
	codepoints: dict[object:int]
	names: dict[object:]

class RulePattern(NamedTuple):
	bol: tuple[bool, bool]
	tree: Any
	trail_code: Optional[int]
	annotation: Annotation

class DefinitionEntry(NamedTuple):
	tree: Any
	size: Optional[int]
	annotation: Annotation

class ConvertLiterals(SparseRewrite):
	def __init__(self, *, text:str, slices:dict, env:NameSpace):
		self.__text = text
		self.__slices = slices
		self.__env = env
		assert isinstance(env, NameSpace)
		
		# Public attributes will be the results of analysis:
		self.codepoints = {}
		self.names = {}
		self.numbers = {}
		self.warnings = {}
		self.errors = {}
	
	def _mk(self, node, ordinal):
		literal = VOCAB['codepoint_'](node)
		self.codepoints[literal] = ordinal
		return literal
	
	def literal(self, node, in_class=False):
		return self._mk(node, ord(self.__text[self.__slices[node]]))

	def escape(self, node, in_class=False):
		return self._mk(node, ord(self.__text[self.__slices[node].stop-1]))

	def control(self, node, in_class=False):
		return self._mk(node, ord(self.__text[self.__slices[node].stop-1]) % 32)
	
	def hex_point(self, node, in_class=False):
		the_slice = self.__slices[node]
		the_text = self.__text[the_slice.start+2:the_slice.stop]
		return self._mk(node, int(the_text, 16))

	def number(self, node):
		the_text = self.__text[self.__slices[node]]
		self.numbers[node] = int(the_text)
		return node
	
	def n_to_m(self, node):
		sub = self(node.sub)
		least = self(node.min)
		most = self(node.max)
		if self.numbers[least] > self.numbers[most]:
			self.warnings[node] = "Backwards Boundaries; swapping..."
			S = self.__slices
			S[node] = slice(S[node.min].start, S[node.max].stop)
			least, most = most, least
		node = VOCAB['n_to_m'](sub, most, least)
		return node
	
	def cls(self, node):
		""" Inherited attribute useful to make sure defined char-classes get used the right way. """
		return self._unhandled_(node, True)
	
	def __lookup(self, node, in_class, text):
		try: entry = self.names[node] = self.__env[text]
		except NoSuchSymbol: self.errors[node] = "No such symbol as %r in this environment."%text
		else:
			if in_class and type(entry) is not list and type(entry.tree) is not VOCAB['cls']:
				self.errors[node] = "Defined name %r does not refer to a character class here."%text
			return node
	
	def name(self, node, in_class=False):
		s = self.__slices[node]
		return self.__lookup(node, in_class, self.__text[s.start + 1:s.stop - 1])
	
	def shorthand(self, node, in_class=False):
		proxy = VOCAB['name']()
		text = self.__text[self.__slices[node].start+1]
		return self.__lookup(proxy, in_class, text)
	
	def end(self, node):
		# Convert to being a name-reference. Can't happen inside a char-class.
		proxy = VOCAB['name']()
		self.names[proxy] = charset.EOL
		return proxy

	def dot(self, node):
		# Convert to being a name-reference. Can't happen inside a char-class.
		proxy = VOCAB['name']()
		self.names[proxy] = charset.DOT
		return proxy

class RuleAnalyzer(StrictPass):
	""" Just enough to extract a pattern's left and right context information. """
	
	def __init__(self, names):
		# By now I'm assuming names have been resolved,
		# so I don't need the environment.
		self.__names = names

	def pattern_regular(self, node):
		# No trailing context, so trail is None
		return self(node.left_context), node.stem, None
	
	def pattern_with_right_context(self, node):
		stemSize, trailSize = self(node.stem), self(node.right_context)
		expression = VOCAB['sequence'](node.stem, node.right_context)
		if trailSize:
			trailCode = - trailSize
		elif stemSize:
			trailCode = stemSize
		else:
			raise VariableTrailingContextError()
		return self(node.left_context), expression, trailCode
	
	def pattern_only_right_context(self, node):
		return self(node.left_context), node.right_context, 0
	
	def anywhere(self, n):
		return (True, True)
	
	def begin_line(self, n):
		return (False, True)
	
	def mid_line(self, n):
		return (True, False)
	
	def cls(self, node):
		return 1
	
	def codepoint_(self, node):
		return 1
	
	def sequence(self, node):
		a = self(node.a)
		if a is not None:
			b = self(node.b)
			if b is not None:
				return a+b
			
	def alternation(self, node):
		a = self(node.a)
		if a is not None:
			b = self(node.b)
			if b == a:
				return b

	def star(self, _): return None
	def hook(self, _): return None
	def plus(self, _): return None
	def epsilon(self, _): return 0
	
	def name(self, node):
		entry = self.__names[node]
		return 1 if type(entry) is list else entry.size

class RemoveCounts(SparseRewrite):
	"""
	Counted notation is convenient shortcut.
	To implement it, I'll also take a shortcut:
	Specific forms of count-expressions get rewritten in terms of sequence, star, hook, and epsilon.
	There's an interesting consequence:
	The resulting "tree" is no longer a tree, but a DAG.
	The algorithms won't care.
	"""
	def __init__(self, numbers):
		self.__numbers = numbers
	def n_times(self, n):
		count = self.__numbers[n.count]
		return self.__convert(n.sub, count, count)
	def n_to_m(self, n):
		least = self.__numbers[n.min]
		most = self.__numbers[n.max]
		return self.__convert(n.sub, least, most)
	def n_or_more(self, n):
		least = self.__numbers[n.min]
		return self.__convert(n.sub, least, None)
	def n_or_fewer(self, n):
		most = self.__numbers[n.max]
		return self.__convert(n.sub, 0, most)
	
	@staticmethod
	def __convert(sub, least:int, most):
		"""
		This will return a sequence (or an epsilon node, as the case may be).
		The first ``least`` elements will be references to sub.
		Then, ``most - least`` elements will be optional references.
		Or, if ``most`` is unbounded, the last element us made a plus-reference.
		However, I wrote it in reverse.
		"""
		if most is None:
			it = VOCAB['star'](sub)
		else:
			it = VOCAB['epsilon']()
			option = VOCAB['hook'](sub)
			for _ in range(least, most):
				it = VOCAB['sequence'](option, it)
		for _ in range(least):
			it = VOCAB['sequence'](sub, it)
		return it

class Encoder(StrictPass):
	"""
	This represents the strategy to encode a regular expression as
	a non-deterministic finite state automaton.
	Cribbing from https://swtch.com/~rsc/regexp/regexp1.htm
	"""
	def __init__(self, nfa:NFA, *, annotation:Annotation, rank:int):
		self.__nfa = nfa
		self.__rank = rank
		self.__ann = annotation
		self.__ce = ClassEncoder(names=annotation.names, codepoints=annotation.codepoints)
	def __new_node(self) -> int: return self.__nfa.new_node(self.__rank)
	def __eps(self, src:int, dst:int, ): self.__nfa.link_epsilon(src, dst)
	def codepoint_(self, n, dst:int, ) -> int:
		src = self.__new_node()
		self.__nfa.link(src, dst, charset.singleton(self.__ann.codepoints[n]))
		return src
	
	def cls(self, n, dst:int) -> int:
		compiled_class = self.__ce(n.members)
		src = self.__new_node()
		self.__nfa.link(src, dst, compiled_class)
		return src
	
	@staticmethod
	def epsilon(_, dst:int, ) -> int:
		return dst
	
	def alternation(self, alt, dst:int, ) -> int:
		src = self.__new_node()
		self.__eps(src, self(alt.a, dst))
		self.__eps(src, self(alt.b, dst))
		return src
	
	def sequence(self, seq, dst:int, ) -> int:
		return self(seq.a, self(seq.b, dst))
	
	def hook(self, h, dst:int, ) -> int:
		src = self.__new_node()
		self.__eps(src, self(h.sub, dst))
		self.__eps(src, dst)
		return src
		
	def star(self, s, dst:int, ) -> int:
		src = self.__new_node()
		self.__eps(src, self(s.sub, src))
		self.__eps(src, dst)
		return src
		
	def plus(self, p, dst:int, ) -> int:
		mid = self.__new_node()
		src = self(p.sub, mid)
		self.__eps(mid, src)
		self.__eps(mid, dst)
		return src
		

	def __name(self, ns, dst:int, ) -> int:
		dfn = self.__ann.names[ns]
		if type(dfn) is list:
			src = self.__new_node()
			self.__nfa.link(src, dst, dfn)
			return src
		else:
			enc = Encoder(self.__nfa, rank=self.__rank, annotation=dfn.annotation)
			return enc(dfn.tree, dst)

	name = shorthand = __name


class ClassEncoder(StrictPass):
	"""
	Builds a character class in the format used by the finite.NFA class.
	
	One might think this could all be done inside class Encoder, but the
	treatment of name references differs.
	"""
	def __init__(self, *, names:dict, codepoints:dict):
		self.__names = names
		self.__codepoints = codepoints
	
	def initial_minus(self, node):
		return charset.singleton(ord("-"))
	def __name(self, n):
		# By this point, the name is proven safe to use in a class.
		# That check happens before a definition goes into the symbol table.
		dfn : DefinitionEntry = self.__names[n]
		if type(dfn) is list:
			return dfn
		else:
			ann = dfn.annotation
			ce = ClassEncoder(names=ann.names, codepoints=ann.codepoints)
			return ce(dfn.tree.members)
	name = shorthand = __name
	def singleton(self, n): return charset.singleton(self.__codepoints[n.item])
	def range(self, n): return charset.range_class(self.__codepoints[n.first], self.__codepoints[n.last])
	def union(self, n): return charset.union(self(n.a), self(n.b))
	def intersection(self, n): return charset.intersect(self(n.a), self(n.b))
	def complement(self, n): return charset.complement(self(n.inverse))
	def subtraction(self, n): return charset.intersect(self(n.a), charset.complement(self(n.b)))
	def empty_set(self, n): return charset.EMPTY


def annotate(text, env, language) -> tuple[Any, [Annotation]]:
	slices = {}
	tree_1 = parse_regex(text, slices, language=language)
	pass_1 = ConvertLiterals(text=text, slices=slices, env=env)
	tree_2 = pass_1(tree_1)
	
	if pass_1.warnings or pass_1.errors:
		st = SourceText(text)
		for node, error in pass_1.warnings.items():
			Issue("Pass-1", Severity.WARNING, error, {None: [Evidence(slices[node])]}).emit(lambda _: st)
		for node, error in pass_1.errors.items():
			Issue("Pass-1", Severity.ERROR, error, {None: [Evidence(slices[node])]}).emit(lambda _: st)
		if pass_1.errors:
			raise PatternError(text)
	
	tree_3 = RemoveCounts(pass_1.numbers)(tree_2)
	return tree_3, Annotation(pass_1.codepoints, pass_1.names)


def analyze_pattern(pattern_text, env) -> Optional[RulePattern]:
	tree, ann = annotate(pattern_text, env, 'Pattern')
	pass_2 = RuleAnalyzer(ann.names)
	bol, expression, trail_code = pass_2(tree)
	return RulePattern(bol, expression, trail_code, ann)


def let_subexpression(env, name, pattern):
	assert isinstance(name, str)
	if len(name) <= 1: raise NameTooShort
	tree, ann = annotate(pattern, env, 'Regular')
	size = RuleAnalyzer(ann.names)(tree)
	env[name] = DefinitionEntry(tree, size, ann)

############

REGEX_SUGAR = set(r"^ / \ | ? * + { } , ( ) [ [^ - ] && &&^ ; whitespace".split())

def install_regex_grammar(grammar:ContextFreeGrammar, message_mapper=lambda x:x):
	"""
	Problem one: Context-free grammar for regular expressions.
	The object is to add rules to a CFG representing how to
	parse a regular expression from its constituent tokens.
	
	This gets extracted in hopes of reusing it in a smarter meta-compiler later.
	"""
	for line in """
		Pattern: left_context Regular               :pattern_regular
		Pattern: left_context Regular right_context :pattern_with_right_context
		Pattern: left_context right_context         :pattern_only_right_context
		left_context:    :anywhere
		left_context: ^  :begin_line
		left_context: ^ ^ :mid_line
		right_context: end
		right_context: / Regular
		right_context: / Regular end :sequence
		Regular: sequence
		Regular: Regular | sequence :alternation
		sequence: term
		sequence: sequence term :sequence
		term: atom
		term: atom ? :hook
		term: atom * :star
		term: atom + :plus
		term: atom { number }          :n_times
		term: atom { number , }        :n_or_more
		term: atom { , number }        :n_or_fewer
		term: atom { number , number } :n_to_m
		atom: codepoint
		atom: name
		atom: shorthand
		atom: dot
		atom: ( Regular )
		atom: class ] :cls
		class: [ conjunct
		class: [^ conjunct :complement
		class: class && conjunct :intersection
		class: class &&^ conjunct :subtraction
		conjunct: item
		conjunct: - :initial_minus
		conjunct: conjunct item :union
		item: codepoint :singleton
		item: codepoint - codepoint :range
		item: name
		item: shorthand
		codepoint : literal
		codepoint : escape
		codepoint : control
		codepoint : hex_point
	""".splitlines():
		bits = [x.strip() for x in line.split(':')]
		if len(bits) < 2: continue
		lhs, rhs = bits[0], tuple(bits[1].split())
		indices = [i for i, s in enumerate(rhs) if s not in REGEX_SUGAR]
		if len(bits) == 2:
			assert len(indices) == 1, line
			action = indices[0]
		elif len(bits) == 3:
			action = SemanticAction(message_mapper(bits[2]), indices)
		else: assert False
		grammar.add_rule(Rule(lhs, rhs, None, action, line))


def declare_regex_token_rules(nfa, make_rule):
	"""
	A recognizer for regex tokens.

	One approach is to build an NFA directly from state transition rules.
	This implies a simplified (internal) DSL for such rules.
	In this DSL, every character will stand for itself except:
		normal shorthand-escape letters serve their purpose without an escape symbol.
		the underscore shall stand in for the plus symbol (because we need to recognize plus, unescaped).
		C for the char range from @ to ~ in the ASCII space. (i.e. 64 - 126)
	"""
	def connect(cond, pattern, rule_id):
		src = prior = nfa.new_node(0)
		for q in nfa.condition(cond): nfa.link_epsilon(q, src)
		for c in pattern:
			if c == '_':
				nfa.link_epsilon(src, prior)
			else:
				if c in bootclass: label = bootclass[c]
				else: label = charset.singleton(ord(c))
				dst = nfa.new_node(0)
				nfa.link(src, dst, label)
				prior, src = src, dst
		nfa.final[src] = rule_id
	def declare(cond, pattern, kind, then=None):
		rule_id = make_rule(kind, then)
		connect(cond, pattern, rule_id)
	def meta(cond, token, then=None):
		return declare(cond, token, token, then)
	
	bootclass = charset.mode_normal.new_child("Bootstrap Extras")
	bootclass['C'] = charset.range_class(64, 127)
	bootclass['%'] = charset.POSIX['xdigit']
	
	ignore =  make_rule(None, None)
	for cond in 'group', 'brace', 'class':
		connect(cond, 's_', ignore)
	meta("group", ")", "POP")
	meta("init", "(", "group")
	meta("init", "[", "class")
	meta("init", '[^', "class")
	meta("init", '{', "brace")
	declare("init", '.', 'dot')
	for c in "^$/": declare("group", c, 'literal')
	for c in r'|}])/^\?*+': meta("init", c)
	declare("init", '$', 'end')

	declare("brace", 'd_', "number")
	meta("brace", ',')
	meta("brace", '}', "POP")
	
	meta('class', '-')
	meta('class', '&&')
	meta('class', '&&^')
	meta('class', ']', "POP")

	declare("esc", r'\L', "escape")
	declare("esc", '{lw_}', "name")
	declare("esc", r"\cC", 'control')
	declare("esc", r"\l", 'shorthand')
	hex_point = make_rule("hex_point", None)
	for pattern in (r"\x%%",  r"\u%%%%", r"\U%%%%%%%%", ):
		connect("esc", pattern, hex_point)
	declare("esc", 'S', 'literal')
	
	nfa.link_condition("group", "init")
	nfa.link_condition("init", "esc")
	nfa.link_condition("class", "esc")

def _regex_scanner():
	nfa = NFA()
	actions = []
	def rule(msg, *args):
		return foundation.allocate(actions, ("scan_"+msg, args))
	def makeRule(kind:str, then):
		if kind is None: return rule("ignore")
		elif then is None:
			if kind in REGEX_SUGAR: return rule("sugar", kind)
			else: return rule("token", kind)
		elif then == "POP": return rule("popping", kind)
		else: return rule("pushing", kind, then)
	
	declare_regex_token_rules(nfa, makeRule)
	dfa = nfa.subset_construction().minimize_states().minimize_alphabet()
	return dfa, actions
_DFA, _ACTIONS = _regex_scanner()

class RXBindings(Bindings):
	
	def __init__(self, slices):
		self.__slices = slices
	
	def on_match(self, yy, rule_id:RuleId):
		message, args = _ACTIONS[rule_id]
		method = getattr(self, message)
		method(yy, *args)
	
	def scan_ignore(self, yy):
		pass
	def scan_sugar(self, yy, kind):
		yy.token(kind, None)
	def scan_token(self, yy, kind):
		semantic = VOCAB[kind]()
		self.__slices[semantic] = yy.slice()
		yy.token(kind, semantic)
	def scan_pushing(self, yy, kind, then):
		yy.token(kind, None)
		yy.push(then)
	def scan_popping(self, yy, kind):
		yy.token(kind, None)
		yy.pop()

def _regex_parser():
	rex = ContextFreeGrammar()
	rex.start.extend(['Pattern', 'Regular'])
	install_regex_grammar(rex, message_mapper=VOCAB.__getitem__)
	rex.validate()
	table = tabulate(lalr_construction(rex), rex, style=DeterministicStyle(strict=True))
	constructors = table.constructors
	combine = lambda cid,args:constructors[cid](*args)
	return table, combine
_PARSE, _COMBINE = _regex_parser()


def scan_regex(text, slices):
	return IterableScanner(text, _DFA, RXBindings(slices), "init")

def parse_regex(text, slices, *, language="Pattern", on_error=None):
	each_token = scan_regex(text, slices)
	try:
		return shift_reduce.parse(_PARSE, _COMBINE, each_token, language=language, on_error=on_error)
	except ParseError:
		print("Cannot understand regex:")
		print(illustration(text, each_token.left))
		raise
