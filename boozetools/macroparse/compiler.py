"""
MacroParse will be built atop the existing "mini" parsing and scanning tools.
It extends the language of attributed context-free grammars with additional features described on the wiki page.

The design for this module is still in flux, although most of the main ideas are laid out.
"""
import re
from boozetools import context_free, miniscan, regular

INITIAL = 'INITIAL'

def compile_file(pathname):
	with(open(pathname)) as fh: document = fh.read()
	return compile_string(document)

def compile_string(document:str):
	# The approach is a sort of outside-in parse. The outermost layer concerns the overall markdown document format,
	# which is dealt with in the main body of this routine prior to determinizing and serializing everything.
	# Each major sub-language is line-oriented and interpreted with one of the following five subroutines:

	def definitions():
		name, regex = s.split(None, 1)
		assert name not in env, 'You cannot redefine named subexpression %r.'%name
		assert re.fullmatch(r'[A-Za-z][A-Za-z_]+', name), 'Subexpression %r ought to obey the rule here.'%name
		env[name] = miniscan.rex.parse(miniscan.META.scan(regex, env=env), language='Regular')
		assert isinstance(env[name], regular.Regular), "This would be a bug."
	
	def conditions():
		assert False, 'Code for this block is not designed yet.'
		pass
	
	def patterns():
		assert False, 'Code for this block is not designed yet.'
		pass
	
	def precedence():
		assert False, 'Code for this block is not designed yet.'
		pass
	
	def productions():
		assert False, 'Code for this block is not designed yet.'
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
			group = tokens[1] if len(tokens)>1 else INITIAL
			if group not in pattern_groups: pattern_groups[group] = nfa.condition(group)
			return patterns
		if head == 'precedence': return precedence
		if head == 'productions':
			for t in tokens[1:]:
				if t not in start:
					start.append(t)
			return productions
		return None
	
	# The context-free portion of the definition:
	cfg = context_free.ContextFreeGrammar()
	cfg_actions = [] # The format of a cfg action entry shall be the pair <message_name, tuple-of-offsets>
	start = []
	
	# The regular (finite-state) portion of the definition:
	env = miniscan.PRELOAD['ASCII'].copy()
	nfa = regular.NFA()
	nfa_actions = [] # That of a regular-language rule entry is <message, parameter>
	pattern_groups = {}


	# Here begins the outermost layer of grammar definition parsing, which is to comprehend the
	# structure of a supplied mark-down document just enough to extract headers and code-blocks.
	section, in_code = None, False
	for s in document.splitlines(keepends=False):
		if in_code:
			s = s.strip()
			if '```' in s: in_code = False
			elif s and section: section()
		elif s.startswith('#'): section = decide_section()
		elif s.strip().startswith('```'): in_code = True
		else: continue
	
	# Validate everything possible:
	if not start:
		print('Inferring CFG start symbol from earliest production because none was given on a #Productions header.')
		start.append(cfg.rules[0].lhs)
	cfg.validate(start)
	
	# Compose, compress, and serialize the control tables.
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
	compile_file(args.source_path).serialize_to(target_path)

if __name__ == '__main__': main()
