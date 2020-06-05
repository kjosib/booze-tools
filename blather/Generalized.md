# Considerations on Generalized LR Parsing

Right now the `.parsing.general` submodule is a bit short on
exposition. It would make a lot of sense to build a simple framework
and then illustrate the development of GLR ideas through time.

This would begin with the simple "Brute Force" cactus-stack idea,
then progress to the simpler graph-structured stacks, then RNGLR,
and perhaps give a nod to the more sophisticate techniques.

It should probably also explore hybrid parsing like Elkhound,
which (for the uninitiated) is a GLR engine that tries to minimize
graph-node activity by using deterministic array-oriented behavior
wherever it makes sense to do so.

## Tomita's GSS Algorithm:

## Farshi's Refinement (and the cost)

## Right-Nullable GLR Algorithm:

In RNGLR, an instruction can possibly say (with look-ahead T):

> This state leads, by a sequence of N epsilon reductions, to another
> state which will reduce symbol A by rule R.

The reason for these extra-spiffy instructions is to simplify much
troublesome logic (rife with subtle pitfalls and unpleasant trade-offs)
which tries _at runtime_ to recover the same fact from the state of the
parse engine. 

If you know this much of the parser's fate in advance, then
a recognizer can perform the larger reduction right away without
waiting for the epsilon chain to develop, although in general the chain
must develop anyway. For actual parsing, correct behavior for
these "right-nulled" instructions depends on how the parse tree is
exposed to the application. For example, a constant fragment of
"semantic content" could be shared among all paths to it.

Clearly such rules add complexity; both to the parser generator and
the parse table data structure. They also add to the non-determinism
inherent in the parse tables. However, they do speed things up
considerably vs the Farshi approach whenever right-nullable rules
are present in the grammar.

## Moose-Dog

There are mostly-deterministic parsing applications: either the
most natural grammar is just not LR(1), or else it's actually
ambiguous in some areas, but where the ambiguous portions typically
make up a very small fraction of the overall input.

In cases like this it's quite sensible to stick with ordinary LR parsing
until meeting an unresolved conflict, and then use an oracle to
work out what the correct parsing decision *in this case* is, and
then go back to the normal LR approach. 

What does this "oracle" look like?

One method is something like a GLR parser, but with normal semantic
processing on hold, its job is to record a correct set of parsing
decisions which then get played back with the semantic values along
for the ride.

This oracle needs to be able to examine the deterministic stack
as well as anything it's speculating about.  (Also you need to
decide how to deal with puns.) If the contents of those
speculations are themselves "mostly-deterministic" then traditional
GSS nodes are no longer appropriate. Instead, the nodes can hold
arrays of symbols and the back-pointers can say how deep into those
arrays they point: this means chasing a lot fewer pointers on average
to perform a trial parse.

Obviously this idea is not appropriate for all grammars, but in
practice it gets performance comparable to traditional linear-time
deterministic parsing for many real-world scenarios.

In broad brush strokes, this is the method used by the "Elkhound"
parser-generator system, which has reported excellent results
parsing C++ with a grammar corresponding naturally to the language
definition rather than requiring janky contrivances to work within
the limitations of YACC. (For the uninitiated, C++ has various
production rules which can possibly produce identical terminal
strings (although in different ways), and the language standard
says "if it looks like a duck, it's a duck.")

## Binary RNGLR

One remaining problem with RNGLR is the asymptotic worst-case complexity,
which is `O(n^k)` where `n` is the size of the input and `k` is one more
than the length of the longest grammar rule.

The `k` comes from the branching factor as you explore predecessor nodes
to perform reductions. In the worst case, you can have every node linking
to every previous node; thus the exponent. 

In practice such behavior is limited to highly-ambiguous natural
grammars, but these have applications so it's worth thinking about
how to address it.

One approach is to limit the depth of necessary explorations.
Consider if a long rule were broken into "prefix" and "suffix" parts:
then `k` would drop. Of course you'd have extra non-terminals.

Rather than manually tweaking the grammar, it's possible to perform a
transformation on the parse table. The intuition is as follows:
Each time you've just recognized two symbols of a longer rule, make
some kind of special bookkeeping note so the search-problem at the end
of the handle is only two nodes deep.

Due to the complexity of Binary RNGLR, it has comparatively high
constant-factor overhead. No implementation is currently
planned for Booze-Tools. 
