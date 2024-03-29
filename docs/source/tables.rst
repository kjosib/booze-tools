Format of Tables
================

.. contents:: Table of Contents
    :depth: 2


The .automaton files could be of interest to someone who wants to:

* implement alternative rule-following strategies.
* write specialized post-processing tools.
* write a driver in another host language than Python.
* be curious for curiosity's own sake.

What's here describes the most current version of these files.

General Structure
-------------------

An ``.automaton`` file is a `JSON (JavaScript Object Notation) <https://json.org>`_ object
with keys as follows:

* description: A string. Currently always ``"MacroParse Automaton"``, but in principle could be taken from the grammar definition.
* parser: Another JSON object described below.
* scanner: Another JSON object described below.
* source: The base-name of the file from which the grammar definition came.
* version: An array of three small integers meant to obey the conventions of `semantic versioning <https://semver.org>`_.

Scanner Table
--------------

Overview
..........
Booze-Tools scanners are based on deterministic finite state machines.
To scan a lexeme, it begins in the initial state for its current scan condition,
then follows a delta function of (state, character) until no further progress is possible.
At that point, the scanner follows the rule corresponding to the leftmost-longest-match.
Rather, the states are annotated such that the leftmost-longest-match is selected in this process.

The source code for the algorithm is pretty short and illustrative.
Start with the function ``scan_one_raw_lexeme`` in module ``boozetools.scanning.recognition``.

Top-Level Fields
.................
* action: a table of information telling the scan algorithm what to do once it's found a match.
* alphabet: encodes a function from character code-point to character class.
* dfa: encodes the deterministic finite state automaton which the scanner follows.

Fields of the DFA
.................
* delta: encodes the transition function from *<state, a character class>* to *<subsequent state>*.
* final: a list of accepting states.
* rule: a corresponding list of rule numbers as accepted by those states.
* initial: a mapping from scan-condition string (such as ``"INITIAL"``) to a pair initial states.

The exact form of the ``delta`` table is based on a lot of experimentation to do a good job compacting otherwise-large tables.
Probably a future version will allow to build a much simpler format for tables that are inherently fairly small to begin with.

Parser Table
-------------

Booze-Tools parsers are based on pushdown automata.
A simplified version of the algorithm is the function ``trial_parse``
in the module ``boozetools.parsing.shift_reduce``. That version handles
neither semantic values nor error recovery.
When you feel ready for the rest, check out the ``parse`` function in the same file.

Top-Level Fields
.................
action
    Tells the parser how to respond to a terminal symbol,
    and when the right-hand side of a production rule is recognized.
breadcrumbs
    Used in error reporting; maps states to the symbols that reach those states.
goto
    Tells how to respond once a non-terminal symbol has been synthesized.
initial
    Tells where to start for each supported language.
nonterminals
    A list of the non-terminal symbols used in defining the grammar.
    This list is useful principally for error-reporting.
rule
    Tells how to synthesize a non-terminal symbol from a sequence of symbols from the stack.
    These are described in greater detail below.
terminals
    A list of the string representations of the terminals from the grammar.
    Useful in error reporting, but you might use it to prepare a reserved-word table.

Encoding of Rules
..................
The format of the parser's ``rule`` object is probably sub-optimal, but is also:

constructor
    | List of distinct possible messages from the ends of production rules.
    | ``null`` means to just create a tuple of the (non-void) right-hand-side symbols.
    | Strings that begin with ``:`` are considered *mid-rule actions*.
    | All other strings are the names of ordinary *constructor* messages.
line_number
    List of the grammar definition source line number for each rule.
rules
    List of 4-tuples for each right-hand side.

The 4-tuples for a parser rule are:

Non-terminal index.
    This can index into the ``nonterminals`` list, mentioned earlier.
Length of the rule's right-hand side.
    | This number of symbols get popped before pushing the non-terminal symbol.
    | Zero is a valid size: Epsilon rules and mid-rule actions both use it.
Constructor index:
    | If negative: the stack offset of the semantic value.
    | If zero or positive: an index into the ``constructor`` list, mentioned earlier.
Capture list.
    This list of integer offsets from top-of-stack (before any popping) describe where to find the arguments for the constructor.
    In case of a bracketing rule (negative constructor index), the capture-list is meaningless.

.. Note:: Note that all stack-offsets are negative, with -1 being the top-of-stack.
