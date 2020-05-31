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
import re, os, collections, typing
from ..support import foundation, compaction, interfaces
from ..parsing import automata
from ..scanning import regular, miniscan
from . import grammar


def compile_file(pathname, *, method, strict=False) -> dict:
	with(open(pathname)) as fh: document = fh.read()
	return compile_string(document, method=method).determinize().as_compact_form(filename=os.path.basename(pathname))

class TextBookForm:
	""" This provides the various views of the text-book form of scan and parse tables. """
	def __init__(self, *, dfa: regular.DFA, scan_actions:list, parse_table: automata.DragonBookTable):
		self.dfa = dfa
		self.scan_actions = scan_actions
		self.parse_table = parse_table
	def as_compact_form(self, *, filename):
		return {
			'description': 'MacroParse Automaton',
			'version': (0, 0, 1),
			'source': filename,
			'scanner': self.compact_scanner(),
			'parser': self.compact_parser(),
		}
	def compact_scanner(self):
		dfa = self.dfa
		if dfa is None: return
		return {
			'dfa': compaction.compress_scanner(initial=dfa.initial, matrix=dfa.states, final=dfa.final),
			'action': dict(zip(['message', 'parameter', 'trail', 'line_number'], zip(*self.scan_actions))),
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
			'rule': encode_parse_rules(table.rule_table, table.constructors, table.rule_origin),
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

class IntermediateForm(typing.NamedTuple):
	nfa: regular.NFA
	scan_actions: list
	hfa: automata.HFA
	parse_style:automata.ParsingStyle
	def determinize(self) -> TextBookForm:
		dfa = self.nfa.subset_construction().minimize_states().minimize_alphabet() if self.nfa.states else None
		return TextBookForm(dfa=dfa, scan_actions=self.scan_actions, parse_table=automata.tabulate(self.hfa, style=self.parse_style))
	def make_dot_file(self, path): self.hfa.make_dot_file(path)


def compile_string(document:str, *, method) -> IntermediateForm:
	""" This has the job of reading the specification and building the textbook-form tables. """
	# The approach is a sort of outside-in parse. The outermost layer concerns the overall markdown document format,
	# which is dealt with in the main body of this routine prior to determinizing and serializing everything.
	# Each major sub-language is line-oriented and interpreted with one of the following five subroutines:
	
	def handle_meta_exception(e: Exception):
		if isinstance(e, miniscan.PatternError):
			raise grammar.DefinitionError('At line %d: %s'%(line_number, e.args[0])) from None
		elif isinstance(e, interfaces.LanguageError):
			raise grammar.DefinitionError('At line %d: Malformed pattern.' % line_number) from None
		else: raise e

	def definitions():
		name, regex = current_line_text.split(None, 1)
		if name in env: raise grammar.DefinitionError('You cannot redefine named subexpression %r at line %d.'%(name, line_number))
		if not re.fullmatch(r'[A-Za-z][A-Za-z_]+', name): raise grammar.DefinitionError('Subexpression %r ought to obey the rule at line %d.'%(name, line_number))
		try: env[name] = miniscan.rex.parse(miniscan.META.scan(regex, env=env), language='Regular')
		except Exception as e: handle_meta_exception(e)
		assert isinstance(env[name], regular.Regular), "This would be a bug."
	
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
	
	def patterns():
		# This could be done better: a nice exercise might be to enhance the present regex parser to also
		# grok actual scanner rules as an alternate language start-symbol; such could eliminate some of
		# this contemptible string hackery and thereby enable things like embedded spaces where they make sense.
		# Such would also involve hacking the metascanner bootstrap code to track paren depth and recognize
		# the other tokens that can appear.
		def note_pattern(pattern):
			# Now patterns that share a trail length can also share a rule ID number.
			try: bol, expression, trail = miniscan.analyze_pattern(pattern, env)
			except Exception as e: handle_meta_exception(e)
			else: pending_patterns[trail].append((bol, expression))
		if current_line_text.endswith('|'):
			pattern = current_line_text[:-1].strip()
			if re.search(r'\s', pattern): raise grammar.DefinitionError('Unable to analyze pattern/same-as-next structure at line %d.')
			note_pattern(pattern)
			return
		m = re.fullmatch(r'(.*?)\s*:([A-Za-z][A-Za-z_]*)(?:\s+([A-Za-z_]+))?(?:\s+:(0|[1-9][0-9]*))?', current_line_text)
		if not m: raise grammar.DefinitionError('Unable to analyze overall pattern/action/parameter/(rank) structure at line %d.'%line_number)
		pattern, action, parameter, rank_string = m.groups()
		rank = int(rank_string) if rank_string else 0
		note_pattern(pattern)
		for trail, list_of_patterns in pending_patterns.items():
			rule_id = foundation.allocate(scan_actions, (action, parameter, trail, line_number))
			for bol, expression in list_of_patterns:
				src = nfa.new_node(rank)
				dst = nfa.new_node(rank)
				for q,b in zip(nfa.condition(current_pattern_group), bol):
					if b: nfa.link_epsilon(q, src)
				nfa.final[dst] = rule_id
				regular.Encoder(nfa, rank, env).visit(expression, src, dst)
		pending_patterns.clear()
		pass
	
	def precedence(): ebnf.read_precedence_line(current_line_text, line_number)
	
	def productions(): ebnf.read_production_line(current_line_text, line_number)
	
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
			current_pattern_group = tokens[1] if len(tokens)>1 else interfaces.DEFAULT_INITIAL_CONDITION
			return patterns
		if head == 'precedence': return precedence
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
	env = miniscan.PRELOAD['ASCII'].copy()
	nfa = regular.NFA()
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
	for current_line_text in document.splitlines(keepends=False):
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
	hfa = automata.PARSE_TABLE_METHODS[method](ebnf.sugarless_form())
	if ebnf.nondeterministic_symbols:
		style = automata.GeneralizedStyle(len(hfa.graph), ebnf.nondeterministic_symbols)
	else:
		style = automata.DeterministicStyle(False)
	return IntermediateForm(nfa=nfa, scan_actions=scan_actions, hfa=hfa, parse_style=style,)


def encode_parse_rules(rules:list, constructors:list, origins:list) -> dict:
	assert isinstance(rules, list), type(rules)
	return {'rules': rules, 'line_number': origins, 'constructor': constructors, }

def main():
	import sys, argparse, json
	parser = argparse.ArgumentParser(
		prog='py -m boozetools.macroparse.compiler',
		description='Compile a macroparse grammar/scanner definition from a markdown document into a set of parsing and scanning tables in JSON format.',
	)
	parser.add_argument('source_path', help='path to input file')
	parser.add_argument('-f', '--force', action='store_true', dest='force', help='allow to write over existing file')
	parser.add_argument('-o', '--output', help='path to output file')
	parser.add_argument('-i', '--indent', help='indent the JSON output for easier reading.', action='store_const', dest='indent', const=2, default=None)
	parser.add_argument('--pretty', action='store_true', help='Display uncompressed tables in attractive grid format on STDOUT.')
	parser.add_argument('--csv', action='store_true', help='Generate CSV versions of uncompressed tables, suitable for inspection.')
	parser.add_argument('--dev', action='store_true', help='Operate in "development mode" -- which changes from time to time.')
	parser.add_argument('--dot', action='store_true', help="Create a .dot file for visualizing the parser via the Graphviz package.")
	parser.add_argument('-m', '--method', choices=automata.PARSE_TABLE_METHODS, default='LR1', type=str.upper, help="Which parser table construction method to use.")
	parser.add_argument('-v', '--verbose', action='store_true', help="Squawk, mainly about the table compression stats.")
	if len(sys.argv) < 2: exit(parser.print_help())
	args = parser.parse_args()
	if args.verbose: compaction.VERBOSE = True
	stem, extension = os.path.splitext(args.source_path)
	target_path = args.output or stem+'.automaton'
	if os.path.exists(target_path) and not args.force:
		print('Target file already exists and --force command-line argument was not given.', file=sys.stderr)
		exit(1)
	with(open(args.source_path)) as fh:document = fh.read()
	try:
		intermediate_form = compile_string(document, method=args.method)
		if args.dot: intermediate_form.make_dot_file(target_path+'.dot')
		textbook_form = intermediate_form.determinize()
	except grammar.DefinitionError as e:
		print(e.args[0], file=sys.stderr)
		exit(1)
	else:
		compact = textbook_form.as_compact_form(filename=os.path.basename(args.source_path))
		if args.pretty: textbook_form.pretty_print()
		if args.csv: textbook_form.make_csv(target_path)
		if args.dev:
			compact_goto = compact['parser']['goto']
			for listname in ['row_index', 'col_index', 'quotient']:
				print(listname+':', compact_goto[listname], len(compact_goto[listname]))
			print('mark:', compact_goto['mark'], 'residue:', len(compact_goto['quotient'])-compact_goto['mark'])
		json.dump(compact, open(target_path, 'w'), separators = (',', ':'), sort_keys = False, indent = args.indent)
		print('Wrote automaton in JSON format to:')
		print('\t'+target_path)

if __name__ == '__main__': main()
