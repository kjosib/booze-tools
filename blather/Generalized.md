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

## The "Brute Force" Cactus-Stack Algorithm

Suppose we allow non-deterministic LR parse tables. What does this mean
exactly? It means that, for any given parsing situation, the table can
specify a shift (if appropriate) and zero or more reduction rules that apply.

What again does LR parsing normally entail? Simple: Shifts `push` states
onto a stack, and reductions `pop` them off again (immediately followed by
`push`ing a GOTO state). The reason for the stack is so the parser can remember
which constructions it might have been in the middle of, and how deeply
nested those constructions might be.

Suppose an LR-parser encounters a non-deterministic table entry:
Conceptually the simplest idea is to make however many copies of the
stack, and then carry out the different possible actions on each copy.
If any spawned stack cannot accept a next token, it dies. If all stacks
die, the whole parser dies.

It's inefficient to make copies of large structures. Instead, each `push`
operation simply creates an entry with a new top-of-stack and a pointer
to a previous `push` entry. (Base-case, empty stack, is `nil`.)

This is simple enough to code and works well enough in some applications, but:

* it's still prone to exponential behavior,
* linked-lists generate lots of garbage,
* it can't handle hidden-left recursion (by infinite allocation loop), and

## Tomita's GSS Algorithm:

When you boil it all down, Tomita's chief contribution is the idea to use
a directed acyclic graph rather than a tree of states: each node could have
more than one predecessor, and so after any given machine cycle, you have
at most one active graph-node per LR table state. (In practice, you'll have
many fewer such active nodes).

Neglecting epsilon rules, this works pretty well: You still have search
problem to carry out reductions, but the performance bounds are polynomial
in the size of the input string.

The problem with epsilon-rules is not immediately obvious, but it's easy
to trigger with a hidden-left-recursive grammar such as this:

```
S -> E S a     (rule 1)
S -> b         (rule 2)
E -> :epsilon  (rule 3)
```

It should be clear upon inspection that this context-free grammar describes
in fact a regular language (`ba*`) but the obvious variations on Tomita all
fail to recognize the string `baa`. Why? Well, with lookahead `b` we can
certainly shift the first token of rule 2 (where we'll soon recognize `S`)
but we can also possibly reduce rule 3 before shifting the `b`, but we wind
up in the same state after shifting `b` both ways. Now if you carefully
play this scenario forward: The first branch dies; the second allows `ba`
but then can't go back in time to recognize however many `E` symbols must
have preceeded the first `b` so as to consume all the right number of `a`
tokens which follow.

There are a number of hacks which solve the problem for subsets of the
epsilon-grammars, but no simple solution for all of them.

Tomita recognized these difficulties but did not offer a complete solution.

## Farshi's Refinement (and the cost)

Recognizing an epsilon-rule means adding an edge to the stack-graph.
if that edge connects into a state from which reduction is again possible,
should we perform that new reduction? Well, the answer is yes, obviously.
But only those new reductions which become possible on account of the new
edge, lest we repeat the work corresponding to the old edges.

This change appears to fix hidden-left-recursion but breaks
hidden-right-recursion! Why? Well, in a hidden-right-recursive scenario
(Like the above but change rule 1 to `S -> a S E`) then
each time you recognize rule 3 you've got to go back
and recognize rule 1 again -- and again -- and again, potentially
many times. But what's happening is we recognize rule 3 once and only once,
because it can only have one predecessor node, because we're keeping it to
one node per state in the "current situation". No new node means no new edge
whenever (the new) rule 1 is recognized a second time, and so it won't be
considered for a third go-round, even though that may be necessary.

Farshi figured out that, if a node _has been involved_ in recognizing a rule
(even if it's not the "recognizing" node, and you add a predecessor to that
node, then you're adding recognition paths for that rule. Given ordinary
(non-deterministic) LR parse tables, the only sure way to know this event
has happened (and to what rule) involves some computationally-expensive
steps whenever an epsilon-rule is recognized at all.

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
are present in the grammar. In fact, they fully recover the original
Tomita speed and then some.

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
