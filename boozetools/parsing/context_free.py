"""
# Context Free Grammars

In pure form, a context free grammar (CFG) consists of:
	* A set of terminal symbols,
	* A set of non-terminal symbols, disjoint from the terminals,
	* A set of production rules, each consisting of:
		* left-hand side (exactly one symbol)
		* right-hand side (ordered sequence of zero or more symbols)
	* and a start symbol.

As a cool and potentially useful hack, I expand the normal definition to allow
potentially several "start symbols" to share the same overall definition. The
practical benefit is that a single set of tables (by choice of initial state)
describes a process to parse different languages (or sub-phrases) while sharing
common specification elements.

Practical language definitions generally make use of a few extra concepts:
* Attribute-synthesis rules show how to construct a semantic value for a sentence in the language.
* Operator-precedence rules enable deterministic parsing decisions in the face of CFG ambiguities.


# Operator Precedence and Associativity (OP&A)

Classically, operator-precedence and associativity was an entire parsing method.
In more recent times, it's normally an adjunct for resolving the parsing conflicts
that come up in ambiguous context-free grammars.

The method considers two broad categories of conflict:
* Shift/Reduce: a priority decision between operators to the left and right.
* Reduce/Reduce: a choice between production rules applicable at the same point.

If explicit declarations are not provided, the grammar is
ambiguous -- at least with respect to the power of the  used.
There are ways to deal with ambiguity, but for parsers the convention
is to shift on a shift-reduce conflict (i.e. assume right-associativity) and, in
the event of a reduce/reduce conflict, to use the earliest-defined rule.


# Attribute Synthesis

The rules are annotated with instructions for how to perform a semantic transduction
of the implied parse tree. In current Booze-Tools philosophy, there are a few broad
categories of transduction steps. These include:

* Renaming: These can usually be optimized out of parse tables.
* Bracketing: Technically a special-case message parameterized only by a single stack offset.
* Message: Carries a message and a list of stack offsets for semantic parameters to the message.
* Accept-Language: Implied in augmentation-rules used for generating parse tables.


# A note on symbology:

People adopt various style-rules for representing the symbols in their grammars. These strictures add
a useful layer of redundancy. At the moment there's no support for it, but eventually it could be as
simple as adding a predicate for whether something *looks* like a non-terminal. A related

"""

import collections, itertools
from typing import List, Optional, NamedTuple, Hashable, Sequence, Union, Protocol
from ..support import foundation, pretty


LEFT, RIGHT, NONASSOC, BOGUS = object(), object(), object(), object()

class Fault(ValueError):
	""" Generic exception thrown by the generic handler. """

class FaultHandler(Protocol):
	"""
	This generic handler just raises exceptions.
	More sophisticated handlers might do something more sophisticated.
	The concept is to report faults as they are noticed.
	
	This may not be the final form of the protocol, but it will do for now.
	"""
	def rule_produces_bogons(self, rule, bogons):
		raise Fault("Rule at %r produces bogus terminal(s) %r."%(rule.provenance, bogons))
	
	def epsilon_right_recursion(self, rule):
		raise Fault("Rule at %r produces epsilon right-recursion."%rule.provenance)
	
	def nonterminal_given_precedence(self, symbol):
		raise Fault("Nonterminal %r included in precedence declaration."%symbol)
	
	def bad_prec_sym(self, rule):
		raise Fault("Rule at %r has an explicit precedence-symbol without a defined precedence level.", rule.provenance)
	
	def ill_founded_symbols(self, symbols):
		raise Fault("Ill-Founded Symbols: %r."%symbols)
	
	def unreachable_symbols(self, symbols):
		raise Fault("Unreachable Symbols: %r."%symbols)
	
	def duplicate_rule(self, rule, extra):
		raise Fault("Rule at %r gets duplicated at %r."%(rule.provenance, extra))
	
	def precedence_declared_twice(self, symbol):
		# FIXME: convey the locations involved in the conflict?
		raise Fault("Precedence declared twice on symbol %r."%symbol)

	def self_recursive_loop(self, symbol):
		# FIXME: convey the location of the problem?
		raise Fault("Symbol %r may be replaced by itself in a recursive loop."%symbol)

	def mutual_recursive_loop(self, symbols):
		# FIXME: convey the locations of the problematic rules?
		raise Fault("Symbols %r may be replaced by one another in a mutually-recursive loop."%symbols)

	def epsilon_mutual_recursion(self, symbols):
		# FIXME: convey the locations of the problematic rules?
		raise Fault("Symbols %r form a mutually-recursive epsilon loop."%symbols)

class SimpleFaultHandler(FaultHandler):
	""" Raise for everything. """
	pass

class ContextFreeGrammar:
	"""
	Attributed context-free grammar with operator-precedence and associativity declarations.
	
	This object follows a builder pattern: You're expected to construct an empty grammar,
	give it a bunch of declarations, and then start calculating based on the completed grammar.
	"""
	def __init__(self, fault_handler:FaultHandler = None):
		# Context-free bits
		self.symbols = set()
		self.rules = []
		self.start = []  # The start symbol(s) may be specified asynchronously to construction or the rules.
		self.symbol_rule_ids = {}
		
		# Operator-Precedence Support
		self.token_precedence = {}
		self.level_assoc = []
		self.level_provenance = []  # Used for error-reporting.
		
		# Oh yes, let's don't forget about fault handling and detection:
		self.fault_handler = fault_handler or SimpleFaultHandler()
		self.mentions = collections.defaultdict(list)
	
	def display(self):
		head = ['', 'Symbol', 'Produces', 'Using']
		body = [[i, rule.lhs, rule.rhs, rule.action] for i,rule in enumerate(self.rules)]
		pretty.print_grid([head] + body)

	def rule(self, lhs:str, rhs:List[str], prec_sym, action, provenance):
		"""
		This is your basic mechanism to install arbitrary plain-jane BNF rules.
		It provides the consistency checks better than if you were to instantiate Rule directly.
		
		For the sake of simplicity, at this layer symbols are all strings.
		Duplicate rules are rejected by raising an exception.
		
		:param lhs: The "left-hand-side" non-terminal symbol which is declared to produce...
		
		:param rhs: this "right-hand-side" sequence of symbols.
		
		:param prec_sym: Set the precedence of this reduction explicitly according to that
		of the given symbol as previously declared. If this is not supplied and the table
		construction algorithm finds it necessary, method infer_prec_sym(...) implements
		default processing on the right-hand-side.
		
		:param action:
		* If an integer, then the significant-symbol index for a renaming or bracketing rule.
		* If a SemanticAction object, then as explained there.
		
		Unit/renaming productions are recognized and treated specially. The parser tables
		will generally optimize such rules to a zero-cost abstraction, bypassing pointless
		extra stack activity and leaving out needless extra states. Certain very rare
		constructions may defeat the optimization by rendering it unsound. The tables will
		be constructed *correctly* in any event.
		
		:param provenance: Use this to indicate the provenance of the rule. It can be a source
		line number, or whatever else makes sense in your application.
		
		:return: Nothing.
		
		"""
		if lhs in self.token_precedence:
			return self.fault_handler.nonterminal_given_precedence(lhs)
		self.symbols.add(lhs)
		self.symbols.update(rhs)
		if lhs not in self.symbol_rule_ids: self.symbol_rule_ids[lhs] = []
		if isinstance(action, int): assert 0 <= action < len(rhs)
		else: assert isinstance(action, SemanticAction) and all(p<len(rhs) for p in action.places), action
		sri = self.symbol_rule_ids[lhs]
		if any(self.rules[rule_id].rhs == rhs for rule_id in sri):
			# This may technically be quadratic, but it's only looking within the same nonterminal's rules.
			return self.fault_handler.duplicate_rule(lhs, rhs)
		else:
			rule_id = foundation.allocate(self.rules, Rule(lhs, rhs, prec_sym, action, provenance))
			sri.append(rule_id)
			for symbol in rhs:
				self.mentions[symbol].append(rule_id)

	def augmented_rules(self) -> list:
		"""
		The LR family of algorithms are normally explained in terms of an augmented grammar:
		It has a special "accept" rule which just expands to the start symbol for the ordinary
		context-free grammar at issue. There's a good reason for this: It makes the algorithms
		work properly without a lot of special edge cases to worry about. However, the "accept"
		non-terminal ought to be imaginary: it can't appear on the right, one never reduces the
		"accept" symbol, and I object to it consuming space in the GOTO table as it typically
		does in implementations that rely on a first-class rule (with left-hand side symbol).

		This object exists to clarify interaction with the "augmented" rule set.
		NB: Since we support multiple "start" symbols, there are corresponding "accept" rules.
		"""
		assert self.start
		return [rule.rhs for rule in self.rules] + [[language] for language in self.start]
	
	def initial(self) -> range:
		""" The range of augmented-rule indices corresponding to the list of start symbols. """
		first = len(self.rules)
		return range(first, first+len(self.start))
	
	################
	#
	#  Here begin bits associated with the operator-precedence disambiguation feature:
	#
	################
	
	def assoc(self, direction, symbols, provenance=None):
		assert direction in (LEFT, NONASSOC, RIGHT, BOGUS)
		assert symbols
		level = foundation.allocate(self.level_assoc, direction)
		self.level_provenance.append(provenance)
		for symbol in symbols:
			if symbol in self.symbol_rule_ids: self.fault_handler.nonterminal_given_precedence(symbol)
			elif symbol in self.token_precedence: self.fault_handler.precedence_declared_twice(symbol)
			else: self.token_precedence[symbol] = level
	
	def decide_shift_reduce(self, symbol, rule_id):
		try:
			sp = self.token_precedence[symbol]
		except KeyError:
			return None
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
	
	def apparent_terminals(self) -> set:
		""" Of all symbols mentioned, those without production rules are apparently terminal. """
		# FIXME: This could be a pluggable strategy, and MAY be misplaced. Validation and table generation need to know.
		return self.symbols - self.symbol_rule_ids.keys()
	
	def bipartite_closure(self, root_symbols) -> set:
		"""
		The algorithm to find epsilon symbols and well-founded symbols is basically the same,
		with different initial conditions. It's a bipartite propagation, alternating between
		disjuncts (symbols) and conjuncts (rules). By factoring this out and focusing on the
		graph structure of the problem (and also getting some sleep) a decent solution arose.
		"""
		# Structuring the problem in bipartite-graph form, as explained in the docstring.
		# The transitive closure involves some stateful cleverness:
		# Rely on the foundation library for proper abstraction:
		
		def successors(symbol):
			for rule_id in self.mentions[symbol]:
				remain[rule_id] -= 1
				if remain[rule_id] == 0:
					yield self.rules[rule_id].lhs
		
		remain = [len(rule.rhs) for rule in self.rules]
		return foundation.transitive_closure(root_symbols, successors)
	
	def find_epsilon(self) -> set:
		""" Which symbols may produce the empty string? """
		return self.bipartite_closure(rule.lhs for rule in self.rules if not rule.rhs)
	
	def assert_well_founded(self):
		"""
		Here, "well-founded" means "can possibly produce a finite sequence of terminals."
		The opposite is called "ill-founded".
		
		Here are two examples of ill-founded grammars:
			S -> x S   -- This is ill-founded because there's always one more S.
			A -> B y;  B -> A x     -- Similar, but with mutual recursion.

		A terminal symbol is well-founded. So is an epsilon symbol, since zero is finite.
		A rule with only well-founded symbols in the right-hand side is well-founded.
		A non-terminal symbol with at least one well-founded rule is well-founded.
		Induction applies. That induction happens to be called ``bipartite_closure``.
		
		A grammar with only well-founded symbols is well-founded.
		"""
		well_founded = self.bipartite_closure(self.apparent_terminals() | self.find_epsilon())
		ill_founded = self.symbol_rule_ids.keys() - well_founded
		if ill_founded:
			self.fault_handler.ill_founded_symbols(ill_founded)

	def find_first(self):
		"""
		Particularly the LL school of grammar processing uses first-sets.
		These tables answer the question: For each nonterminal symbol,
		what terminal symbols could it possibly start with?
		
		The FIRST set of a nonterminal is the union of the FIRST sets of each right-hand side.
		Without epsilon symbols, the FIRST set of a right-hand side is that of its first symbol.
		With them, you need to include all symbols up to the first non-epsilon symbol.
		
		Anyway, this is a job for a strongly_connected_components,
		in part because it also produces a topological sort which
		allows for a quick determination of the level sets.
		"""
		
		# Structure the problem as a graph, called ``first``
		first = collections.defaultdict(set)
		epsilon = self.find_epsilon()
		for rule in self.rules:
			for symbol in rule.rhs:
				first[rule.lhs].add(symbol)
				if symbol not in epsilon: break
		
		# Gather up the answer in topological order:
		for component in foundation.strongly_connected_components_hashable(first):
			# All the members of a component share a first-set, here called ``f``.
			f = set()
			for symbol in component:  # Not sure about performance with large SCCs.
				f.update(*(first[x] for x in first[symbol]))
				first[symbol] = f
			f.difference_update(self.symbol_rule_ids)
		return first
	
	def assert_valid_prec_sym(self):
		for rule in self.rules:
			if rule.prec_sym and rule.prec_sym not in self.token_precedence:
				self.fault_handler.bad_prec_sym(rule)
	
	def assert_no_bogons(self):
		"""
		"Bogus" tokens only exist to establish precedence levels and must not appear in right-hand sides.
		"""
		bogons = collections.defaultdict(list)
		for sym, prec in self.token_precedence.items():
			if self.level_assoc[prec] is BOGUS:
				if sym in self.mentions:
					for rule_id in self.mentions[sym]:
						bogons[rule_id].append(sym)
		for rule_id, symbols in sorted(bogons.items()):
			self.fault_handler.rule_produces_bogons(self.rules[rule_id], symbols)
	
	def assert_no_orphans(self):
		"""
		Every symbol should be reachable from the start symbol(s).
		This is a simple transitive closure.
		"""
		produces = collections.defaultdict(set)
		for rule in self.rules: produces[rule.lhs].update(rule.rhs)
		unreachable = self.symbols - foundation.transitive_closure(self.start, produces.get)
		if unreachable:  # NB: Bogons are not among self.symbols.
			self.fault_handler.unreachable_symbols(unreachable)
	
	def assert_no_rename_loops(self):
		""" If a symbol may be replaced by itself (possibly indirectly) then it is diseased. """
		renames = collections.defaultdict(set)
		for rule in self.rules:
			if len(rule.rhs) == 1:
				if rule.lhs == rule.rhs[0]:
					self.fault_handler.self_recursive_loop(rule.lhs)
				else:
					renames[rule.lhs].add(rule.rhs[0])
		for component in foundation.strongly_connected_components_hashable(renames):
			if len(component) > 1: self.fault_handler.mutual_recursive_loop(component)
	
	def assert_no_epsilon_loops(self):
		""" Epsilon Left-Self-Recursion is OK. All other recursive-epsilon-loops are pathological. """
		epsilon = self.find_epsilon()
		reaches = collections.defaultdict(set)
		for rule in self.rules:
			epsilon_prefix = list(itertools.takewhile(epsilon.__contains__, rule.rhs))
			if not epsilon_prefix: continue
			if epsilon_prefix[0] == rule.lhs: epsilon_prefix.pop(0)
			if rule.lhs in epsilon_prefix:
				# Somehow this case seems qualitatively different.
				self.fault_handler.epsilon_right_recursion(rule)
			reaches[rule.lhs].update(epsilon_prefix)
		for component in foundation.strongly_connected_components_hashable(reaches):
			if len(component) > 1:
				self.fault_handler.epsilon_mutual_recursion(component)
	
	def validate(self):
		"""
		This raises an exception (derived from Fault, above) for the first error noticed.
		It might be nice to get a more complete read-out of problems, but that would mean
		inventing some sort of document structure to talk about faults in grammars.
		Then again, maybe that's in the pipeline.
		"""
		self.assert_valid_prec_sym()
		self.assert_no_bogons()
		self.assert_well_founded()
		self.assert_no_orphans()
		self.assert_no_rename_loops()
		self.assert_no_epsilon_loops()


class Rule(NamedTuple):
	lhs: str  # What non-terminal symbol...
	rhs: List[str]  # ...produces what string of other symbols?
	prec_sym: Optional[str]  # If this rule has explicit precedence, what symbol represents its precedence level?
	action: object  # What to do for attribute synthesis when recognizing this rule?
	provenance: object  # Where did this rule come from? We need to know for reporting and debugging.
	
	def is_rename(self):
		return len(self.rhs) == 1 and self.action == 0

class SemanticAction(NamedTuple):
	"""
	designate the semantics for the attribute synthesis portion of the rule specification
		:param message: and
		:param places: . If `message` is `None`, then places is expected to be the
		. Otherwise,
		`places` should be a list/tuple of indices into the RHS relevant to the given message.
		Note: At this level we don't interpret messages further.
	"""
	message: Hashable
	places: Sequence[int]


