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
from typing import Optional, NamedTuple, Hashable, Sequence, Union, Protocol
from ..support import foundation, pretty


LEFT, RIGHT, NONASSOC, BOGUS = object(), object(), object(), object()

class Fault(ValueError):
	""" Generic exception thrown by the generic handler. """

class FaultHandler(Protocol):
	"""
	This generic handler just raises exceptions.
	More sophisticated handlers might do something more sophisticated.
	This is not the final form of the protocol.

	It might be nice to get a more complete read-out of problems, but that would mean
	inventing some sort of document structure to talk about faults in grammars.
	Then again, maybe that's in the pipeline.
	"""
	def rule_produces_bogon(self, rule, symbol):
		raise Fault("Rule at %r produces bogus terminal(s) %r." % (rule.provenance, symbol))
	
	def nullable_right_recursion(self, rule):
		raise Fault("Rule at %r produces nullable right-recursion."%rule.provenance)
	
	def nonterminal_given_precedence(self, symbol):
		raise Fault("Nonterminal %r included in precedence declaration."%symbol)
	
	def bad_prec_sym(self, rule):
		raise Fault("Rule at %r has an explicit precedence-symbol without a defined precedence level.", rule.provenance)
	
	def ill_founded_symbols(self, symbols):
		raise Fault("Ill-Founded Symbols: %r."%symbols)
	
	def unreachable_symbols(self, symbols):
		raise Fault("Unreachable Symbols: %r."%symbols)
	
	def duplicate_rules(self, rules):
		raise Fault("Duplicated rules at %r."%', '.join(map(str, (r.provenance for r in rules))))
	
	def precedence_redeclared(self, symbol, first, extras):
		raise Fault("Precedence declared twice on symbol %r."%symbol)

	def self_recursive_loop(self, symbol):
		# FIXME: convey the location of the problem?
		raise Fault("Symbol %r may be replaced by itself in a recursive loop."%symbol)

	def mutual_recursive_loop(self, symbols):
		# FIXME: convey the locations of the problematic rules?
		raise Fault("Symbols %r may be replaced by one another in a mutually-recursive loop."%symbols)

	def mutual_nullable_recursion(self, symbols):
		# FIXME: convey the locations of the problematic rules?
		raise Fault("Symbols %r form a mutually-recursive nullable loop."%symbols)

class SimpleFaultHandler(FaultHandler):
	""" Protocols cannot be instantiated, so here's a simple way to get "raise for everything" behavior. """
	pass


class SemanticAction(NamedTuple):
	"""
	Designate semantics for the attribute synthesis portion of the rule specification.
	Consists of an ostensible *message* and a list of indices within the right-hand-side from
	which to gather arguments to that message. The indices are zero-indexed from the left.
	At this level, we don't interpret messages further: That's for the driver to handle.
	"""
	message: Optional[Hashable]
	indices: Sequence[int]

class Rule(NamedTuple):
	"""
	Arbitrary plain-jane BNF rule.

	lhs: The "left-hand-side" non-terminal symbol which is declared to produce...
	rhs: this "right-hand-side" sequence of symbols.
	prec_sym: Optional explicit rule precedence symbol. If missing, may be inferred.
	action:
		* If an integer, then the significant-symbol index for a renaming or bracketing rule.
		* If a SemanticAction object, then as explained there.

	Unit/renaming productions are recognized and treated specially. The parser tables
	will generally optimize such rules to a zero-cost abstraction, bypassing pointless
	extra stack activity and leaving out needless extra states. Certain very rare
	constructions may defeat the optimization by rendering it unsound. The tables will
	be constructed *correctly* in any event.

	provenance: Use this to indicate the provenance of the rule. It can be a source
	line number, or whatever else makes sense in your application.
	"""
	lhs: Hashable  # What non-terminal symbol...
	rhs: tuple[Hashable, ...]  # ...produces what string of other symbols?
	prec_sym: Optional[Hashable]  # If this rule has explicit precedence, what symbol represents its precedence level?
	action: Union[int, SemanticAction]  # What to do for attribute synthesis when recognizing this rule?
	provenance: object  # Where did this rule come from? We need to know for reporting and debugging.
	
	def __str__(self):
		return "%s -> %s"%(self.lhs, ' '.join(map(str, self.rhs)))
	
	def is_rename(self):
		return len(self.rhs) == 1 and self.action == 0
	
	def assert_valid_action(self):
		""" If this check fails, it's held to be a bug in whatever code created the rule object. """
		arity = len(self.rhs)
		if isinstance(self.action, SemanticAction):
			assert all(p<arity for p in self.action.indices), self.action
		else:
			assert isinstance(self.action, int) and 0 <= self.action < arity
	
	def as_dotted(self, position):
		rhs = [str(s) for s in self.rhs]
		rhs.insert(position, pretty.DOT)
		return str(self.lhs)+' -> '+(" ".join(rhs))

class OperatorPrecedenceSupport:
	""" Coherent bits that deal with operator-precedence parsing. This decides most shift-reduce conflicts. """
	
	def __init__(self):
		# The fundamental essentials:
		self.token_precedence = {}
		self.level_assoc = []
		
		# Now for some error-reporting help:
		self.level_provenance = []  # Used for error-reporting.
		self.bogons = set()
		self.extra_declarations = collections.defaultdict(list)

	def assoc(self, direction, symbols, provenance=None):
		assert direction in (LEFT, NONASSOC, RIGHT, BOGUS)
		assert symbols
		level = foundation.allocate(self.level_assoc, direction)
		self.level_provenance.append(provenance)
		for symbol in symbols:
			if symbol in self.token_precedence:
				self.extra_declarations[symbol].append(provenance)
			else:
				self.token_precedence[symbol] = level
	
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

	def validate(self, fault_handler:FaultHandler, rules):
		for symbol, extras in self.extra_declarations.items():
			first = self.level_provenance[self.token_precedence[symbol]]
			fault_handler.precedence_redeclared(symbol, first, extras)
		for rule in rules:
			if rule.lhs in self.token_precedence:
				fault_handler.nonterminal_given_precedence(rule)
			if rule.prec_sym and rule.prec_sym not in self.token_precedence:
				fault_handler.bad_prec_sym(rule)
			for symbol in rule.rhs:
				if self.token_precedence.get(symbol,None) is BOGUS:
					fault_handler.rule_produces_bogon(rule, symbol)
	
	def determine_rule_precedence(self, rule):
		prec_sym = rule.prec_sym or self.infer_prec_sym(rule.rhs)
		if prec_sym: return self.token_precedence[prec_sym]
	
	def decide_shift_reduce(self, symbol, rule):
		try: sp = self.token_precedence[symbol]
		except KeyError: return None
		rp = self.determine_rule_precedence(rule)
		if rp is None: return None
		if rp < sp: return LEFT
		# NB: Bison and Lemon both treat later declarations as higher-precedence,
		# which is unintuitive, in that you perform higher-precedence operations
		# first so it makes sense to list them first. Please excuse my dear aunt Sally!
		if rp == sp: return self.level_assoc[rp]
		return RIGHT


class ContextFreeGrammar:
	"""
	Attributed context-free grammar with operator-precedence and associativity declarations.
	
	This object follows a builder pattern: You're expected to construct an empty grammar,
	give it a bunch of declarations, and then start calculating based on the completed grammar.
	"""
	def __init__(self):
		# Context-free bits
		self.symbols = set()
		self.rules:list[Rule] = []
		self.start = []  # The start symbol(s) may be specified asynchronously to construction or the rules.
		self.symbol_rule_ids = {}
		self.ops = OperatorPrecedenceSupport()
		# A reverse mapping from right-hand side symbols to rule IDs makes various algorithms easier/faster:
		self.mentions = collections.defaultdict(list)
	
	def display(self):
		head = ['', 'Symbol', 'Produces', 'Using']
		body = [[i, rule.lhs, rule.rhs, rule.action] for i,rule in enumerate(self.rules)]
		pretty.print_grid([head] + body)

	def add_rule(self, rule):
		"""
		This is your basic mechanism to add BNF rules.
		It's responsible for various bits of internal accounting.
		:return: Nothing.
		"""
		rule.assert_valid_action()
		self.symbols.add(rule.lhs)
		self.symbols.update(rule.rhs)
		
		if rule.lhs not in self.symbol_rule_ids:
			# Don't use a defaultdict; we can't be adding keys by checking for them.
			self.symbol_rule_ids[rule.lhs] = []
		sri = self.symbol_rule_ids[rule.lhs]
		rule_id = foundation.allocate(self.rules, rule)
		sri.append(rule_id)
		for symbol in rule.rhs:
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
	
	def assoc(self, direction, symbols, provenance=None):
		self.ops.assoc(direction, symbols, provenance)
		
	def decide_shift_reduce(self, symbol, rule_id):
		return self.ops.decide_shift_reduce(symbol, self.rules[rule_id])
	
	def apparent_terminals(self) -> set:
		""" Of all symbols mentioned, those without production rules are apparently terminal. """
		# FIXME: This could be a pluggable strategy, and MAY be misplaced. Validation and table generation need to know.
		return self.symbols - self.symbol_rule_ids.keys()
	
	def _bipartite_closure(self, root_symbols) -> set:
		"""
		The algorithm to find nullable symbols and well-founded symbols is basically the same,
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
	
	def find_nullable(self) -> set:
		""" Which symbols may produce the empty string? """
		return self._bipartite_closure(rule.lhs for rule in self.rules if not rule.rhs)
	
	def find_first(self):
		"""
		Return a dictionary of sets to answer the question:
		For each symbol, what terminal symbols might it start with?
		
		This is a least-fixed-point problem particularly suited to Tarjan's
		strongly-connected-components algorithm.
		
		NB: A nontrivial SCC means the grammar is ill-suited to deterministic methods.
		    Proof is left as an exercise for the reader.
		"""
		
		# Structure the problem as a graph, called ``first``
		first = {
			s: set() if s in self.symbol_rule_ids else {s}
			for s in self.symbols
		}
		
		# Each nonterminal absorbs "first" sets from particular others:
		nullable = self.find_nullable()
		for rule in self.rules:
			for symbol in rule.rhs:
				first[rule.lhs].add(symbol)
				if symbol not in nullable: break
		
		# Gather up the answer in topological order:
		for component in foundation.strongly_connected_components_hashable(first):
			# All the members of a component share a first-set, here called ``f``.
			f = set()
			for symbol in component:  # Not sure about performance with large SCCs.
				f.update(*(first[x] for x in first[symbol]))
				first[symbol] = f
			f.difference_update(self.symbol_rule_ids) # Thus subtracting out nonterminals
		return first
	
	def assert_well_founded(self, fault_handler: FaultHandler):
		"""
		Here, "well-founded" means "can possibly produce a finite sequence of terminals."
		The opposite is called "ill-founded".

		Here are two examples of ill-founded grammars:
			S -> x S   -- This is ill-founded because there's always one more S.
			A -> B y;  B -> A x     -- Similar, but with mutual recursion.

		A terminal symbol is well-founded. So is a nullable symbol, since zero is finite.
		A rule with only well-founded symbols in the right-hand side is well-founded.
		A non-terminal symbol with at least one well-founded rule is well-founded.
		Induction applies. That induction happens to be called ``bipartite_closure``.

		A grammar with only well-founded symbols is well-founded.
		"""
		well_founded = self._bipartite_closure(self.apparent_terminals() | self.find_nullable())
		ill_founded = self.symbol_rule_ids.keys() - well_founded
		if ill_founded:
			fault_handler.ill_founded_symbols(ill_founded)
	
	def assert_no_orphans(self, fault_handler:FaultHandler):
		"""
		Every symbol should be reachable from the start symbol(s).
		This is a simple transitive closure.
		"""
		produces = collections.defaultdict(set)
		for rule in self.rules: produces[rule.lhs].update(rule.rhs)
		unreachable = self.symbols - foundation.transitive_closure(self.start, produces.get)
		if unreachable:  # NB: Bogons are not among self.symbols.
			fault_handler.unreachable_symbols(unreachable)
			
	def assert_no_rename_loops(self, fault_handler:FaultHandler):
		""" If a symbol may be replaced by itself (possibly indirectly) then it is diseased. """
		renames = collections.defaultdict(set)
		for rule in self.rules:
			if len(rule.rhs) == 1:
				if rule.lhs == rule.rhs[0]:
					fault_handler.self_recursive_loop(rule.lhs)
				else:
					renames[rule.lhs].add(rule.rhs[0])
		for component in foundation.strongly_connected_components_hashable(renames):
			if len(component) > 1: fault_handler.mutual_recursive_loop(component)
	
	def assert_no_nullable_loops(self, fault_handler:FaultHandler):
		""" Nullable Left-Self-Recursion is OK. All other recursive-nullable-loops are pathological. """
		nullable = self.find_nullable()
		reaches = collections.defaultdict(set)
		for rule in self.rules:
			nullable_prefix = list(itertools.takewhile(nullable.__contains__, rule.rhs))
			if not nullable_prefix: continue
			if nullable_prefix[0] == rule.lhs: nullable_prefix.pop(0)
			if rule.lhs in nullable_prefix:
				# Somehow this case seems qualitatively different.
				fault_handler.nullable_right_recursion(rule)
			reaches[rule.lhs].update(nullable_prefix)
		for component in foundation.strongly_connected_components_hashable(reaches):
			if len(component) > 1:
				fault_handler.mutual_nullable_recursion(component)
	
	def assert_no_duplicate_rules(self, fault_handler:FaultHandler):
		for symbol, rule_ids in self.symbol_rule_ids.items():
			inverse = collections.defaultdict(list)
			for r in rule_ids:
				inverse[tuple(self.rules[r].rhs)].append(r)
			for rs in inverse.values():
				if len(rs) > 1:
					fault_handler.duplicate_rules([self.rules[r] for r in rs])
	
	def validate(self, fault_handler=SimpleFaultHandler(), allow_duplicate_rules=False):
		"""
		Calls the fault handler with every identified fault. The default fault handler
		raises an exception (derived from Fault, above) for the first error noticed.
		"""
		self.ops.validate(fault_handler, self.rules)
		self.assert_well_founded(fault_handler)
		self.assert_no_orphans(fault_handler)
		self.assert_no_rename_loops(fault_handler)
		self.assert_no_nullable_loops(fault_handler)
		if not allow_duplicate_rules:
			self.assert_no_duplicate_rules(fault_handler)
			
	@classmethod
	def shorthand(cls, start:str, rules:dict):
		""" Just a quick way to enter a test-grammar where semantic-value is irrelevant. """
		cfg = cls()
		cfg.start.append(start)
		for lhs, rhs in rules.items():
			for alt in rhs.split('|'):
				cfg.add_rule(Rule(lhs, tuple(alt), None, 0, None))
		return cfg

