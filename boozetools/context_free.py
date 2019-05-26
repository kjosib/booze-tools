import typing, collections
from .foundation import *
from . import pretty, interfaces

LEFT, RIGHT, NONASSOC, BOGUS = object(), object(), object(), object()

class Fault(ValueError): pass
class DuplicateRule(Fault): pass
class NonTerminalsCannotHavePrecedence(Fault): pass
class FailedToSetPrecedenceOnPrecsym(Fault): pass
class PrecedenceDeclaredTwice(Fault): pass
class RuleProducesBogusToken(Fault): pass # The rule produces a bogus symbol...
class UnreachableSymbols(Fault): pass
class NonproductiveSymbols(Fault): pass
class IllFoundedGrammar(Fault): pass

class Rule(typing.NamedTuple):
	lhs: str
	rhs: tuple
	attribute: object
	prec_sym: typing.Optional[str]

class ContextFreeGrammar:
	"""
	Formally, a context free grammar consists of:
		* A set of terminal symbols,
		* A set of non-terminal symbols, disjoint from the terminals,
		* A set of production rules (as described at class Rule),
		* and a start symbol.
	
	As a cool and potentially useful hack, I expand the normal definition to allow
	potentially several "start symbols" to share the same overall definition. This allows
	a single set of tables to be used (with a different initial state) to parse different
	languages (or sub-phrases) while sharing common specification elements.
	
	Practical languages usually have some ambiguities which are ordinarily resolved with
	precedence declarations. If explicit declarations are not provided, the grammar is
	ambiguous -- at least with respect to the power of the table-generation method used.
	There are ways to deal with ambiguity, but for deterministic parsers the convention
	is to shift on a shift-reduce conflict (i.e. assume right-associativity) and, in
	the event of a reduce/reduce conflict, to use the earliest-defined rule.
	"""
	def __init__(self):
		self.symbols = set()
		self.start = [] # The start symbol(s) may be specified asynchronously to construction or the rules.
		self.rules, self.token_precedence, self.level_assoc = [], {}, []
		self.symbol_rule_ids = {}
	def display(self):
		head = ['', 'Symbol', 'Produces', 'Using']
		body = [[i, rule.lhs, rule.rhs, rule.attribute] for i,rule in enumerate(self.rules)]
		pretty.print_grid([head] + body)

	def rule(self, lhs:str, rhs:(list, tuple), attribute:object, prec_sym=None):
		"""
		This is your basic mechanism to install arbitrary plain-jane BNF rules.
		For the sake of simplicity, at this layer symbols are all strings.
		Duplicate rules are rejected by raising an exception.
		
		:param lhs: The "left-hand-side" non-terminal symbol which is declared to produce...
		
		:param rhs: this "right-hand-side" sequence of symbols.
		
		:param attribute: This is uninterpreted, except in one simple manner:
		if the attribute is `None` and the right-hand-side contains only a single symbol,
		then the production is considered a unit/renaming rule, and the parser tables
		will optimize this rule to a zero-cost abstraction (wherever possible).
		
		:param prec_sym: Set the precedence of this reduction explicitly according to that
		of the given symbol as previously declared. If this is not supplied and the table
		construction algorithm finds it necessary, method infer_prec_sym(...) implements
		default processing on the right-hand-side.
		
		:return: Nothing.
		
		Please note: Certain rare constructions make the unit-rule optimization unsound.
		The tables will be constructed correctly but the general parsing algorithm needs
		to be prepared to find a rule with a null attribute. Correct behavior is generally
		to leave the semantic-stack unchanged.
		"""
		if lhs in self.token_precedence: raise NonTerminalsCannotHavePrecedence(lhs)
		assert attribute is not None or len(rhs) == 1, 'There are no shortcuts at this layer.'
		self.symbols.add(lhs)
		self.symbols.update(rhs)
		if lhs not in self.symbol_rule_ids: self.symbol_rule_ids[lhs] = []
		sri = self.symbol_rule_ids[lhs]
		if any(self.rules[rule_id].rhs == rhs for rule_id in sri): raise DuplicateRule(lhs, rhs)
		sri.append(allocate(self.rules, Rule(lhs, rhs, attribute, prec_sym)))
	
	def apparent_terminals(self) -> set:
		""" Of all symbols mentioned, those without production rules are apparently terminal. """
		return self.symbols - self.symbol_rule_ids.keys()
	
	def find_epsilon(self) -> set:
		""" Which nonterminals can possibly produce epsilon? Enquiring algorithms want to know! """
		opaque = self.apparent_terminals() # These definitely do NOT produce epsilon.
		epsilon = set() # These do, and are the final return object.
		population = {k:len(v) for k,v in self.symbol_rule_ids.items()}
		work = list(self.rules)
		while work:
			maybe = []
			for rule in work:
				if all(map(epsilon.__contains__, rule.rhs)): epsilon.add(rule.lhs)
				elif any(map(opaque.__contains__, rule.rhs)):
					population[rule.lhs] -= 1
					if population[rule.lhs] == 0: opaque.add(rule.lhs)
				else: maybe.append(rule)
			if len(maybe) < len(work): work = maybe
			else:
				# If this happens, all rules that remain are mutually recursive or worse,
				# and I have an idea that this shouldn't happen in a well-founded grammar.
				raise IllFoundedGrammar(maybe)
		return epsilon
	
	def validate(self):
		"""
		This raises an exception (derived from Fault, above) for the first error noticed.
		It might be nice to get a more complete read-out of problems, but that would mean
		inventing some sort of document structure to talk about faults in grammars.
		Then again, maybe that's in the pipeline.
		"""
		bogons = {sym for sym, prec in self.token_precedence.items() if self.level_assoc[prec] is BOGUS}
		produces = collections.defaultdict(set)  # nt -> set[t]
		produced_by = collections.defaultdict(set)
		for rule_id, rule in enumerate(self.rules):
			assert rule.attribute is not None or len(rule.rhs) == 1
			if rule.prec_sym is not None and rule.prec_sym not in self.token_precedence:
				raise FailedToSetPrecedenceOnPrecsym(rule_id)
			produces[rule.lhs].update(rule.rhs)
			for symbol in rule.rhs:
				produced_by[symbol].add(rule.lhs)
				if symbol in bogons: raise RuleProducesBogusToken(rule_id)
		unreachable = self.symbols - transitive_closure(self.start, produces.get)
		# NB: This shows the bogons are not among the true symbols.
		if unreachable: raise UnreachableSymbols(unreachable)
		nonterminals = set(produces.keys())
		nonproductive = self.symbols - transitive_closure(self.symbols-nonterminals, produced_by.get)
		if nonproductive: raise NonproductiveSymbols(nonproductive)
		pass
	
	def assoc(self, direction, symbols):
		assert direction in (LEFT, NONASSOC, RIGHT, BOGUS)
		assert symbols
		level = allocate(self.level_assoc, direction)
		for symbol in symbols:
			if symbol in self.symbol_rule_ids: raise NonTerminalsCannotHavePrecedence(symbol)
			if symbol in self.token_precedence: raise PrecedenceDeclaredTwice(symbol)
			self.token_precedence[symbol] = level
			
	def decide_shift_reduce(self, symbol, rule_id):
		try: sp = self.token_precedence[symbol]
		except KeyError: return None
		rp = self.determine_rule_precedence(rule_id)
		if rp is None: return None
		if rp < sp: return LEFT
		# NB: Bison and Lemon both treat later declarations as higher-precedence,
		# which is unintuitive, in that you perform higher-precedence operations
		# first so it makes sense to list them first. Please excuse my dear aunt Sally!
		if rp == sp: return self.level_assoc[rp]
		return RIGHT
	
	def infer_prec_sym(self, rhs):
		"""
		If a rule without an explicit precedence declaration is involved in a shift/reduce conflict,
		the parse table generation algorithm will call this to decide which symbol represents the
		precedence of this right-hand-side.
		
		As a slight refinement to the BISON approach, this returns the first terminal with an
		assigned precedence, as opposed to the first terminal symbol whatsoever. Often that's
		a distinction without a difference, but when it matters I think this makes more sense.
		"""
		for symbol in rhs:
			if symbol in self.token_precedence:
				return symbol
	
	def determine_rule_precedence(self, rule_id):
		rule = self.rules[rule_id]
		prec_sym = rule.prec_sym or self.infer_prec_sym(rule.rhs)
		if prec_sym: return self.token_precedence[prec_sym]

	def decide_reduce_reduce(self, rule_ids):
		""" This is more art than science. """
		field = []
		for r in rule_ids:
			p = self.determine_rule_precedence(r)
			if p is not None: field.append((p,r))
		if field: return min(field)[1]
