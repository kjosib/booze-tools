"""
Compile a macroparse grammar/scanner definition from a markdown document
into a set of parsing and scanning tables in JSON format.

The resulting tables are suitable for use with the included runtime modules.
  Pypi: https://pypi.org/project/booze-tools/
  GitHub: https://github.com/kjosib/booze-tools/wiki
  ReadTheDocs: https://boozetools.readthedocs.io/en/latest/
"""

import sys, os, argparse, json

from boozetools.macroparse.compiler import compile_string
from boozetools.macroparse.grammar import DefinitionError
from boozetools.macroparse import compaction

def parse_arguments():
	parser = argparse.ArgumentParser(prog='py -m boozetools', description=__doc__,)
	parser.add_argument('source_path', help='path to input file')
	parser.add_argument('-f', '--force', action='store_true', dest='force', help='allow to write over existing file')
	parser.add_argument('-o', '--output', help='path to output file')
	parser.add_argument('-i', '--indent', help='indent the JSON output for easier reading.', action='store_const', dest='indent', const=2, default=None)
	parser.add_argument('--pretty', action='store_true', help='Display uncompressed tables in attractive grid format on STDOUT.')
	parser.add_argument('--csv', action='store_true', help='Generate CSV versions of uncompressed tables, suitable for inspection.')
	parser.add_argument('--dev', action='store_true', help='Operate in "development mode" -- which changes from time to time.')
	parser.add_argument('--dot', action='store_true', help="Create a .dot file for visualizing the parser via the Graphviz package.")
	parser.add_argument('-v', '--verbose', action='store_true', help="Squawk, mainly about the table compression stats.")
	# if len(sys.argv) < 2: exit(parser.print_help())
	return parser.parse_args()

def main(args):
	if args.verbose: compaction.VERBOSE = True
	stem, extension = os.path.splitext(args.source_path)
	target_path = args.output or stem+'.automaton'
	if os.path.exists(target_path) and not args.force:
		print('Target file already exists and --force command-line argument was not given.', file=sys.stderr)
		exit(1)
	with(open(args.source_path)) as fh:document = fh.read()
	try:
		intermediate_form = compile_string(document)
		if args.dot: intermediate_form.make_dot_file(target_path+'.dot')
		textbook_form = intermediate_form.determinize()
	except DefinitionError as e:
		print(e.args[0], file=sys.stderr)
		exit(1)
	else:
		if args.pretty: textbook_form.pretty_print()
		if args.csv: textbook_form.make_csv(target_path)
		compact = textbook_form.as_compact_form(filename=os.path.basename(args.source_path))
		if args.dev:
			compact_goto = compact['parser']['goto']
			for listname in ['row_index', 'col_index', 'quotient']:
				print(listname+':', compact_goto[listname], len(compact_goto[listname]))
			print('mark:', compact_goto['mark'], 'residue:', len(compact_goto['quotient'])-compact_goto['mark'])
		json.dump(compact, open(target_path, 'w'), separators = (',', ':'), sort_keys = False, indent = args.indent)
		print('Wrote automaton in JSON format to:')
		print('\t'+target_path)

if __name__ == '__main__': main(parse_arguments())

