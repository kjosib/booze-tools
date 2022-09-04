"""
MacroParse will be built atop the existing "mini" parsing and scanning tools.
It extends the language of attributed context-free grammars with additional features described on the wiki page.

The design for this module is still in flux, although most of the main ideas are laid out.
The concept is a single-file definition of both lexical and syntactic analysis embedded within MarkDown text.

Markdown as a container format is straightforward to analyze with available string operations or
simple applications of standard Python regex machinery. However, the miniscan/miniparse machinery is
extremely handy for recovering the syntactic structure of actual rules, so that's used here.

========================================

"""
import re, os, collections
from typing import NamedTuple, List
from ..support import foundation, failureprone
from ..parsing.context_free import ContextFreeGrammar
from ..parsing.automata import DragonBookTable, ParsingStyle, GeneralizedStyle, DeterministicStyle, HFA, tabulate
from ..parsing.all_methods import PARSE_TABLE_METHODS
from ..scanning import finite, regular, charset
from ..scanning.interface import INITIAL
from . import grammar, compaction
from .interface import ScanAction


class TextBookForm:
	""" This provides the various views of the text-book form of scan and parse tables. """
	def __init__(self, *, dfa: finite.DFA, scan_actions:List[ScanAction], parse_table: DragonBookTable):
		self.dfa = dfa
		self.scan_actions = scan_actions
		self.parse_table = parse_table
	def as_compact_form(self, *, filename):
		return {
			'description': 'MacroParse Automaton',
			'version': (0, 0, 3),
			'source': filename,
			'scanner': self.compact_scanner(),
			'parser': self.compact_parser(),
		}
	def compact_scanner(self):
		dfa = self.dfa
		if dfa is None: return
		return {
			'dfa': compaction.compress_scanner(initial=dfa.initial, matrix=dfa.states, final=dfa.final),
			'action': dict(zip(ScanAction._fields, zip(*self.scan_actions))),
			'alphabet': {'bounds': dfa.alphabet.bounds, 'classes': dfa.alphabet.classes,}
		}
	def compact_parser(self):
		table = self.parse_table
		if table is None: return
		symbol_index = {s: i for i, s in enumerate(table.terminals + table.nonterminals)}
		symbol_index[None] = None
		form = {
			'initial': table.initial,
			'action': compaction.compress_action_table(table.action_matrix, table.nonassoc_errors),
			'goto': compaction.compress_goto_table(table.goto_matrix),
			'terminals': table.terminals,
			'nonterminals': table.nonterminals,
			'breadcrumbs': [symbol_index[s] for s in table.breadcrumbs],
			'rule': encode_parse_rules(table.rule_table, table.constructors, table.rule_provenance),
		}
		if table.splits: form['splits'] = table.splits
		return form
	def pretty_print(self):
		if self.dfa is not None:
			self.dfa.stats()
			self.dfa.display()
		if self.parse_table is not None:
			self.parse_table.display()
	def make_csv(self, pathstem):
		if self.dfa is not None:
			self.dfa.make_csv(pathstem)
		if self.parse_table is not None:
			self.parse_table.make_csv(pathstem)

class IntermediateForm(NamedTuple):
	nfa: finite.NFA
	scan_actions: List[ScanAction]
	hfa: HFA
	cfg: ContextFreeGrammar
	parse_style:ParsingStyle
	def determinize(self) -> TextBookForm:
		dfa = self.nfa.subset_construction().minimize_states().minimize_alphabet() if self.nfa.states else None
		return TextBookForm(dfa=dfa, scan_actions=self.scan_actions, parse_table=tabulate(self.hfa, self.cfg, style=self.parse_style))
	def make_dot_file(self, path): self.hfa.make_dot_file(path)


def compile_string(document:str, *, method="LR1") -> IntermediateForm:
	text = failureprone.SourceText(document)
	return _compile_text(text, method=method)

def compile_file(pathname, *, method, verbose=False) -> dict:
	filename = os.path.basename(pathname)
	with(open(pathname)) as fh: text = failureprone.SourceText(fh.read(), filename=filename)
	intermediate_form = _compile_text(text, method=method)
	textbook_form = intermediate_form.determinize()
	if verbose:
		print("\n  -- ", pathname, " --")
		textbook_form.pretty_print()
	return textbook_form.as_compact_form(filename=filename)

STRERROR = {
	regular.VariableTrailingContextError: "Variable size for both stem and trailing context is not currently supported.",
}

def _compile_text(document:failureprone.SourceText, *, method) -> IntermediateForm:
	""" This has the job of reading the specification and building the textbook-form tables. """
	# The approach is a sort of outside-in parse. The outermost layer concerns the overall markdown document format,
	# which is dealt with in the main body of this routine prior to determinizing and serializing everything.
	# Each major sub-language is line-oriented and interpreted with one of the following five subroutines:
	
	def handle_meta_exception(e: Exception, pattern_text:str):
		if isinstance(e, regular.PatternError):
			raise grammar.DefinitionError('At line %d: %s'%(line_number, STRERROR[type(e)].format(e.args))) from None
		else:
			raise grammar.DefinitionError('At line %d: Malformed pattern.' % line_number) from None

	def definitions():
		name, subexpression = current_line_text.split(None, 1)
		regular.let_subexpression(env, name, subexpression)
	
	def conditions():
		"""
		The first token will be a condition name. Thereafter, maybe an arrow and one or more included groups.
		Pattern groups named on the LEFT hand side are real start conditions, accessible in the final scanner.
		Those which appear only on the right hand side are "virtual", usable only by inclusion.
		At some point it might be nice to add validation that these are all used correctly...
		"""
		name, includes = error_help.parse(current_line_text, line_number, "condition")
		if name in condition_definitions: error_help.gripe('Re-declared scan-condition %r; this is unexpected.'%name)
		condition_definitions[name] = includes

	def note_pattern(pattern_text):
		# Now patterns that share a trail length can also share a rule ID number.
		try: rule_pattern = regular.analyze_pattern(pattern_text, env)
		except regular.PatternError as e:
			handle_meta_exception(e, pattern_text)
		else: pending_patterns[rule_pattern.trail_code].append(rule_pattern)

	def patterns():
		# This could be done better: a nice exercise might be to enhance the present regex parser to also
		# grok actual scanner rules as an alternate language start-symbol; such could eliminate some of
		# this contemptible string hackery and thereby enable things like embedded spaces where they make sense.
		# Such would also involve hacking the metascanner bootstrap code to track paren depth and recognize
		# the other tokens that can appear.
		if current_line_text.endswith('|'):
			pattern_text = current_line_text[:-1].strip()
			if re.search(r'\s', pattern_text): raise grammar.DefinitionError('Unable to analyze pattern/same-as-next structure at line %d.')
			note_pattern(pattern_text)
		else:
			m = re.fullmatch(r'(.*?)\s*:([A-Za-z][A-Za-z_]*)(?:\s+([A-Za-z_]+))?(?:\s+:(0|[1-9][0-9]*))?', current_line_text)
			if not m: raise grammar.DefinitionError('Unable to analyze overall pattern/action/argument/(rank) structure at line %d.'%line_number)
			pattern_text, action, argument, rank_string = m.groups()
			message = [action]
			if argument is not None: message.append(argument)
			rank = int(rank_string) if rank_string else 0
			note_pattern(pattern_text)
			for trail_code, list_of_patterns in pending_patterns.items():
				rule_id = foundation.allocate(scan_actions, ScanAction(trail_code, message, line_number))
				for rule_pattern in list_of_patterns:
					dst = nfa.new_node(rank)
					nfa.final[dst] = rule_id
					encoder = regular.Encoder(nfa, annotation=rule_pattern.annotation, rank=rank)
					src = encoder(rule_pattern.tree, dst)
					for q,b in zip(nfa.condition(current_pattern_group), rule_pattern.bol):
						if b: nfa.link_epsilon(q, src)
			pending_patterns.clear()
		pass
	
	def precedence():
		ebnf.read_precedence_line(current_line_text, line_number)
	
	def productions():
		ebnf.read_production_line(current_line_text, line_number)
	
	def decide_section():
		# Looks at a header line to see which parsing mode/section to shift into based on a leading keyword,
		# and also performs any clerical duties associated with said shift.
		tokens = ''.join([c if c.isalnum() or c=='_' else ' ' for c in current_line_text]).split()
		if not tokens: return None
		head = tokens[0].lower()
		if head == 'definitions': return definitions
		if head == 'conditions':
			# The way to handle it is to set up epsilon-connections between the conditions
			# as specified in the source definition, and then delete "virtual" conditions
			# from nfa.initial before performing the subset construction. If no "virtual"
			# conditions are determined, then there's nothing to delete, and all groups get presented.
			return conditions
		if head == 'patterns':
			nonlocal current_pattern_group
			current_pattern_group = tokens[1] if len(tokens)>1 else INITIAL
			return patterns
		if head in ('precedence', 'declarations'): return precedence
		if head == 'productions':
			ebnf.current_head = None
			for t in tokens[1:]:
				if t not in ebnf.plain_cfg.start:
					ebnf.plain_cfg.start.append(t)
			return productions
		return None

	# The context-free portion of the definition:
	error_help = grammar.ErrorHelper()
	ebnf = grammar.EBNF_Definition(error_help)
	
	# The regular (finite-state) portion of the definition:
	env = charset.mode_normal.new_child(document.filename or "text")
	nfa = finite.NFA()
	pending_patterns = collections.defaultdict(list) # Those awaiting an application of the `|` action...
	scan_actions = [] # That of a regular-language rule entry is <message, parameter, trail, line_number>
	current_pattern_group = None
	condition_definitions = {}
	
	def tie_conditions():
		declared = set(condition_definitions.keys())
		declared.update(*condition_definitions.values())
		forgot_to_define = declared - set(nfa.initial.keys())
		if forgot_to_define: raise grammar.DefinitionError('These pattern groups were declared in the conditions block but never defined:\n'+repr(forgot_to_define))
		forgot_to_declare = set(nfa.initial.keys()) - declared
		if forgot_to_declare: raise grammar.DefinitionError('These pattern groups appear, but are not declared in the conditions block:\n'+repr(forgot_to_declare))
		# TODO: Check for no cycles in the inclusion graph...
		virtual_groups = declared - set(condition_definitions.keys())
		for name, includes in condition_definitions.items():
			for i in includes:
				nfa.link_condition(name, i)
		for name in virtual_groups:
			del nfa.initial[name]

	# Here begins the outermost layer of grammar definition parsing, which is to comprehend the
	# structure of a supplied mark-down document just enough to extract headers and code-blocks.
	section, in_code, line_number = None, False, 0
	for current_line_text in document.content.splitlines(keepends=False):
		line_number += 1
		if in_code:
			current_line_text = current_line_text.strip()
			if '```' in current_line_text:
				in_code = False
				if pending_patterns: raise grammar.DefinitionError("Consecutive group of patterns lacks a scanner action before end of code block at line %d."%line_number)
			elif current_line_text and section: section()
		elif current_line_text.startswith('#'): section = decide_section()
		elif current_line_text.strip().startswith('```'): in_code = True
		else: continue
	if in_code and section: raise grammar.DefinitionError("A code block fails to terminate before the end of the document.")
	
	# Compose the control tables. (Compaction is elsewhere. Serialization will be straight JSON via standard library.)
	if condition_definitions: tie_conditions()
	cfg = ebnf.sugarless_form()
	hfa = PARSE_TABLE_METHODS[method](cfg)
	if ebnf.is_nondeterministic:
		style = GeneralizedStyle(len(hfa.graph))
	else:
		style = DeterministicStyle(False)
	return IntermediateForm(nfa=nfa, scan_actions=scan_actions, hfa=hfa, cfg=cfg, parse_style=style,)

def encode_parse_rules(rules:list, constructors:list, origins:list) -> dict:
	assert isinstance(rules, list), type(rules)
	return {'rules': rules, 'line_number': origins, 'constructor': constructors, }
