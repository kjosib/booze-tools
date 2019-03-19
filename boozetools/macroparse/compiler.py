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
from boozetools import miniscan, regular, context_free, foundation, algorithms
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
		'version': (0,0,0),
		'scanner': modified_aho_corasick_encoding(nfa.subset_construction().minimize_states().minimize_alphabet(), scan_actions),
		'parser': some_encoding_of(ebnf.plain_cfg.lalr_construction(ebnf.start))
	}

def modified_aho_corasick_encoding(dfa:regular.DFA, scan_actions:list) -> dict:
	"""
	Alfred V. Aho and Margaret J. Corasick discovered a truly wonderful algorithm for a particular class
	of string search problem in which there are both many needles and lots of haystack data. It works by
	the construction of a TRIE for identifying needles, together with a failure pointer for what state to
	enter if the present haystack character is not among the outbound edges from the current state. The
	structure so constructed is queried at most twice per character of haystack data on average, because
	the failure pointers always point to a node at least one edge less deep into the TRIE.
	
	That structure provides the inspiration for a fast, efficient encoding of an arbitrary DFA. The key
	idea is to observe that any given state is likely to much in common with another, shallower state.
	Therefore, it is sufficient to store the identity of a well-chosen shallower state and a sparse list
	of exceptions. If the sparse list results in expansion, a dense row may be stored instead.
	
	For the sake of brevity, the "jam state" is implied to consist of nothing but jam-transitions, and
	is not explicitly stored.
	
	It may be said that today's fast machines and big memories mean little need to compress scanner
	tables. However, compression can help the tables fit in a cache. Alternatively, a driver may
	trivially uncompress the exception tables into the raw tables to avoid a level of indirection
	during actual scanning; this still saves disk space. Non-trivially, the compressed form could
	be translated to machine code and use the program counter to encode the current state...
	"""
	# To begin, we need to renumber the states according to a breadth-first topology, and also determine
	# the resulting depth boundaries.
	dfa.stats()
	jam = dfa.jam_state()
	bft = foundation.BreadthFirstTraversal()
	states = []
	def renumber(src): states.append([jam if dst == jam else bft.lookup(dst) for dst in dfa.states[src]])
	initial = {condition: (bft.lookup(q0), bft.lookup(q1)) for condition, (q0, q1) in dfa.initial.items()}
	bft.execute(renumber)
	final = {bft.lookup(q): rule_id for q, rule_id in dfa.final.items()}
	depth = bft.depth_list()
	
	# Next, we need to construct the compressed structure. For simplicity, this will be three arrays
	# named for their function and indexed by state number.
	default, sparse_index, sparse_data = [], [], []
	for i, row in enumerate(states):
		# Find the shortest encoding by reference to shallower states:
		pointer, best = jam, [k for k,x in enumerate(row) if x != jam]
		for j in range(i):
			if depth[j] == depth[i]: break
			contender = [k for k,x in enumerate(states[j]) if x != row[k]]
			if len(contender) < len(best): pointer, best = j, contender
		# Append the chosen encoding into the structure:
		if len(best) * 2 < len(row): # If the compression actually saves space on this row:
			default.append(pointer)
			sparse_index.append(best)
			sparse_data.append([row[k] for k in best])
		else: # Otherwise, a dense storage format is indicated.
			default.append(None)
			sparse_index.append(None)
			sparse_data.append(row)
	# At this point, the DFA is represented in about as terse a format as makes sense.
	metric = len(default) + sum(map(len, sparse_data)) + sum(x is None or len(x) for x in sparse_index)
	print('Matrix compressed into %d cells.' % metric)
	return {
		'dfa': {'default':default, 'column':sparse_index, 'edge':sparse_data, 'initial':initial, 'final':final,},
		'action': scan_actions,
		'alphabet': {'bounds': dfa.alphabet.bounds, 'classes': dfa.alphabet.classes,}
	}

def some_encoding_of(dbt:context_free.DragonBookTable) -> dict:
	assert False, 'Code for this block is not designed yet.'
	pass

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
