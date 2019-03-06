"""
MacroParse will be built atop the existing "mini" parsing and scanning tools.
It extends the language of attributed context-free grammars with additional features described on the wiki page.

The design for this module is still in flux, although most of the main ideas are laid out.
The concept is a single-file definition of both lexical and syntactic analysis embedded within MarkDown text.

Most components of such a format are straightforward to analyze with available string operations or
simple applications of standard Python regex machinery. However, because the "productions" blocks support
a no-kidding macro language, it's both expedient and illustrative to use miniparse and miniscan definitions
to analyze that portion of the definitions.

For the moment, some lexical and production rules are here:

========================================
\s+         :ignore
\l\w*       :name
:\l\w*      :action
%\l+        :pragma
[.]/\S      :capture
[][(),|]    :passthru
'\S+'       :literal
"\S+"       :literal
[-=>:<]+    :arrow
========================================
For the purpose of getting the macroparse compiler up and running with minimal fuss, the moral equivalent of
two macro definitions will be implemented: these are list_of(what, sep) and one_or_more(what).
These will be helper functions which create a gensym, add the two constituent rules to it, and return
the gensym. Those rules look like:

list_of(what, sep) -> what :first | .list_of(what, sep) sep .what :append
one_or_more(what) -> what :first | .one_or_more(what) .what :append

From the structure of the above, it is apparent that elaborating a macro call is a tricky
business. The algorithm is:
1. Using an equivalence classifer, determine the gensym appropriate to the call.
2. If the gensym is freshly allocated this call, then:
	Make sure it won't be seen as fresh in case of recursion, and then
	for each formal production:
		Substitute the bound symbols corresponding to the call into actual productions on the gensym.
 
========================================
production -> .head arrow .list_of(rewrite, '|')
head -> :use_prior | name | .name '(' .list_of(name, ',' ) ')'
rewrite -> one_or_more(element) :normal_rewrite
| .one_or_more(element) pragma_precsym .[name literal] :prec_rewrite
element -> symbol | capture symbol :capturing
symbol -> actual | action
actual -> name | literal
| '[' .one_or_more(actual) ']' :gensym_renaming
| .name '(' .list_of(actual, ',') ')' :macro_call

"""
import re
from boozetools import context_free, miniscan, regular, foundation, miniparse, algorithms

class DefinitionError(Exception): pass

def compile_file(pathname):
	with(open(pathname)) as fh: document = fh.read()
	return compile_string(document)

PROD_LEX = miniscan.Definition()

### Here's a set of semantic categories for the breakdown of rewrite rules:
class Element:
	""" Base class of RHS elements -- more a marker than anything here... """

class Action(Element):
	def __init__(self, name): self.name = name

class Symbol(Element):
	def __init__(self, name): self.name = name

class GensymRenaming(Element):
	def __init__(self, alternatives): self.alternatives = alternatives

class MacroCall(Element):
	def __init__(self, name, actuals): self.name, self.actuals = name, actuals

class Rewrite:
	def __init__(self, elements:list, precsym):
		self.elements = elements
		self.precsym = precsym
		self.message = self.elements.pop(-1).name if isinstance(self.elements[-1], Action) else None
		self.__args = args = []
		self.size = len(self.elements)
		for i,elt in enumerate(self.elements):
			if hasattr(elt, 'capture'): args.append(i)
		if not args: args.extend(range(self.size)) # Pick up everything if nothing is special.
	def prefix_capture(self, size:int):
		return tuple(c - size for c in self.__args if c < size)


# The MacroParse metagrammar makes use of macro facilities.
# Here's one way to bake something like it atop the miniparser:
def list_of(what, sep):
	head = 'list_of(%r,%r)'%(what,sep)
	PRODUCTION.rule(head, '.%s'%what)(FIRST)
	PRODUCTION.rule(head, '.%s %s .%s'%(head, sep, what) )(APPEND)
	return head
def one_or_more(what):
	head = 'one_or_more(%r)' % (what)
	PRODUCTION.rule(head, '.%s' % what)(FIRST)
	PRODUCTION.rule(head, '.%s .%s' % (head, what))(APPEND)
	return head
def FIRST(element): return [element]
def APPEND(the_list, element):
	the_list.append(element)
	return the_list

# Now that the meta-macro-facility is supplied, the syntax definition for production rule lines is fairly mechanical.
PRODUCTION = miniparse.MiniParse('production')
PRODUCTION.rule('production', '.head arrow .'+list_of('rewrite', '|'))
PRODUCTION.rule('head', '', lambda :None)
PRODUCTION.renaming('head', 'name',)
PRODUCTION.rule('.name ( .%s )'%list_of('name', ','))(tuple) # I'll represent macro heads with (name, args) tuples.


def compile_string(document:str):
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
		rule_id = foundation.allocate(nfa_actions, (action, parameter, trail, line_number))
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
		nonlocal recent_nonterminal
		try: head, list_of_rewrites = PRODUCTION.parse(PROD_LEX.scan(s))
		except algorithms.LanguageError: raise DefinitionError()
		# Deal with nonterminal elision:
		if head is None:
			if recent_nonterminal is None: raise DefinitionError('At line %d, there should be a nonterminal introduced before rewrites make sense.' % line_number)
			else: head = recent_nonterminal
		else:
			recent_nonterminal = head
			if isinstance(head, tuple):
				name, formals = head
				if name in macro_definitions:
					_, _, prior = macro_definitions[name]
					raise DefinitionError('Macro %r is first declared on line %d, then redeclared on line %d. Place all alternatives together between \'|\' symbols, please.'%(name, prior, line_number))
				else:
					macro_definitions[name] = formals, [], line_number
		if isinstance(head, tuple): macro_definitions[head[0]][1].extend(list_of_rewrites)
		else:
			for rewrite in list_of_rewrites:
				assert isinstance(rewrite, Rewrite)
				rule_id = alloc_production(rewrite.message, rewrite.prefix_capture(rewrite.size))
				cfg.rule(head, desugar(rewrite, {}), rule_id, rewrite.precsym)
				
	
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
			nonlocal recent_nonterminal
			recent_nonterminal = None
			for t in tokens[1:]:
				if t not in start:
					start.append(t)
			return productions
		return None
	# Supporting functions:
	def alloc_production(message, captures): return foundation.allocate(cfg_actions, (message, captures, line_number))
	def desugar(rewrite:Rewrite, env:dict) -> list:
		for i, elt in enumerate(rewrite.elements):
			pass
		assert False, 'Code for this block is not designed yet.'
		pass
	
	# The context-free portion of the definition:
	recent_nonterminal = None
	cfg = context_free.ContextFreeGrammar()
	cfg_actions = [] # The format of a cfg action entry shall be the tuple <message_name, tuple-of-offsets, line_number>
	start = []
	macro_definitions = {}
	
	# The regular (finite-state) portion of the definition:
	env = miniscan.PRELOAD['ASCII'].copy()
	nfa = regular.NFA()
	nfa_actions = [] # That of a regular-language rule entry is <message, parameter, trail, line_number>
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
	try:
		compile_file(args.source_path).serialize_to(target_path)
	except DefinitionError as e:
		import sys
		print(e.args[0], file=sys.stderr)
		exit(1)
	else:
		pass

if __name__ == '__main__': main()
