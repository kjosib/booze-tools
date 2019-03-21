"""
MacroParse will be built atop the existing "mini" parsing and scanning tools.
It extends the language of attributed context-free grammars with additional features described on the wiki page.

The design for this module is still in flux, although most of the main ideas are laid out.
The concept is a single-file definition of both lexical and syntactic analysis embedded within MarkDown text.

Most components of such a format are straightforward to analyze with available string operations or
simple applications of standard Python regex machinery. However, b

========================================
========================================

"""
import re
from boozetools import miniscan, regular, context_free, foundation, algorithms, compaction
from boozetools.macroparse import grammar

class DefinitionError(Exception): pass

def compile_file(pathname) -> dict:
	with(open(pathname)) as fh: document = fh.read()
	return compile_string(document)

def compile_string(document:str) -> dict:
	# The approach is a sort of outside-in parse. The outermost layer concerns the overall markdown document format,
	# which is dealt with in the main body of this routine prior to determinizing and serializing everything.
	# Each major sub-language is line-oriented and interpreted with one of the following five subroutines:

	def definitions():
		name, regex = s.split(None, 1)
		if name in env: raise DefinitionError('You cannot redefine named subexpression %r at line %d.'%(name, line_number))
		if not re.fullmatch(r'[A-Za-z][A-Za-z_]+', name): raise DefinitionError('Subexpression %r ought to obey the rule at line %d.'%(name, line_number))
		env[name] = miniscan.rex.parse(miniscan.META.scan(regex, env=env), language='Regular')
		assert isinstance(env[name], regular.Regular), "This would be a bug."
	
	def conditions():
		assert False, 'Code for this block is not designed yet.'
		pass
	
	def patterns():
		m = re.fullmatch(r'(.*?)\s*:([A-Za-z][A-Za-z_]*)(\s+[A-Za-z_]+)?(?:\s+:(0|[1-9][0-9]*))?', s)
		if not m: raise DefinitionError('Unable to analyze overall pattern/action/parameter/(rank) structure at line %d.'%line_number)
		pattern, action, parameter, rank_string = m.groups()
		rank = int(rank_string) if rank_string else 0
		try: bol, expression, trail = miniscan.analyze_pattern(pattern, env)
		except algorithms.LanguageError as e: raise DefinitionError('Malformed pattern on line %d.'%line_number) from e
		rule_id = foundation.allocate(scan_actions, (action, parameter, trail, line_number))
		src = nfa.new_node(rank)
		dst = nfa.new_node(rank)
		for q,b in zip(nfa.condition(group), bol):
			if b: nfa.link_epsilon(q, src)
		nfa.final[dst] = rule_id
		expression.encode(src, dst, nfa, rank)
		pass
	
	def precedence():
		assert False, 'Code for this block is not designed yet.'
		pass
	
	def productions():
		ebnf.read_one_line(s, line_number)
		pass
	
	def decide_section():
		# Looks at a header line to see which parsing mode/section to shift into based on a leading keyword,
		# and also performs any clerical duties associated with said shift.
		tokens = ''.join([c if c.isalnum() else ' ' for c in s]).split()
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
			nonlocal group
			group = tokens[1] if len(tokens)>1 else 'INITIAL'
			return patterns
		if head == 'precedence': return precedence
		if head == 'productions':
			ebnf.current_head = None
			for t in tokens[1:]:
				if t not in ebnf.start:
					ebnf.start.append(t)
			return productions
		return None

	# The context-free portion of the definition:
	ebnf = grammar.EBNF_Definition()
	
	# The regular (finite-state) portion of the definition:
	env = miniscan.PRELOAD['ASCII'].copy()
	nfa = regular.NFA()
	scan_actions = [] # That of a regular-language rule entry is <message, parameter, trail, line_number>
	group = None


	# Here begins the outermost layer of grammar definition parsing, which is to comprehend the
	# structure of a supplied mark-down document just enough to extract headers and code-blocks.
	section, in_code, line_number = None, False, 0
	for s in document.splitlines(keepends=False):
		line_number += 1
		if in_code:
			s = s.strip()
			if '```' in s: in_code = False
			elif s and section: section()
		elif s.startswith('#'): section = decide_section()
		elif s.strip().startswith('```'): in_code = True
		else: continue
	
	# Validate everything possible:
	ebnf.validate()
	
	# Compose and compress the control tables. (Serialization will be straight JSON via standard library.)
	return {
		'version': (0, 0, 0),
		'scanner': scan_table_encoding(nfa.subset_construction().minimize_states().minimize_alphabet(), scan_actions),
		'parser': parse_table_encoding(ebnf.plain_cfg.lalr_construction(ebnf.start))
	}

def scan_table_encoding(dfa:regular.DFA, scan_actions:list) -> dict:
	dfa.stats()
	return {
		'dfa': compaction.modified_aho_corasick_encoding(initial=dfa.initial, matrix=dfa.states, final=dfa.final, jam=dfa.jam_state()),
		'action': scan_actions,
		'alphabet': {'bounds': dfa.alphabet.bounds, 'classes': dfa.alphabet.classes,}
	}

def parse_table_encoding(table:context_free.DragonBookTable) -> dict:
	symbol_index = {s: i for i, s in enumerate(table.terminals + table.nonterminals)}
	symbol_index[None] = None
	return {
		'initial': table.initial,
		'action': compaction.compress_action_table(table.action_matrix, table.essential_errors),
		'goto': compaction.compress_goto_table(table.goto_matrix),
		'terminals': table.terminals,
		'nonterminals': table.nonterminals,
		'breadcrumbs': [symbol_index[s] for s in table.breadcrumbs],
		'rule': encode_parse_rules(table.rule_table),
	}

def encode_parse_rules(rules:list) -> dict:
	assert isinstance(rules, list), type(rules)
	result = {'head': [], 'size': [], 'message': [], 'view':[], 'line_nr':[]}
	unit = (None, None, None)
	for head, size, attribute in rules:
		message, view, line_nr = unit if attribute is None else attribute
		compaction.multi_append(result, {'head': head, 'size':size, 'message': message, 'view':view, 'line_nr':line_nr})
	return result

def main():
	import argparse
	parser = argparse.ArgumentParser()
	parser.add_argument('source_path', help='location of the markdown document containing a macroparse grammar definition')
	parser.add_argument('-o', '--output', help='path to deposit resulting serialized automaton data')
	args = parser.parse_args()
	assert args.source_path.lower().endswith('.md')
	target_path = args.output or args.source_path[:-3]+'.mdc'
	try:
		compile_file(args.source_path).serialize_to(target_path)
	except DefinitionError as e:
		import sys
		print(e.args[0], file=sys.stderr)
		exit(1)
	else:
		pass

if __name__ == '__main__': main()
