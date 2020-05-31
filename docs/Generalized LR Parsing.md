# Comments on Generalized LR Parsing

Generalized-LR parsing amounts to direct simulation of a non-deterministic handle-finding
automaton (HFA). There are two key design decisions: How to represent the stack(s), and how
to orchestrate the operation of semantic actions. In other tools there are various approaches
taken. I'd like to survey those approaches, comment on their strengths and weaknesses, and
provide the ability to choose among them according to your specific parsing needs.

## The General Idea

Conceptually, the idea is to proceed as in ordinary LR parsing, but at
each non-deterministic decision point, copy the current parse stack into as
many cases as necessary for each possible outcome and run all stacks in
parallel. Whenever one stack meets an error condition, it dies. If all
stacks ever die, the entire parse fails.

## Variations on the Theme

While conceptually simple, one should not take the above explanation too
literally. Copying stack data gets old fast. A first simple improvement
treats the state of the parsing machine as a tree of possibilities, where
each node represents a shifted symbol and edges point toward the bottom
of the stack. This approach is easy to understand, easy to code, still
promptly leads to exponential storage requirements, and often does more
work than necessary, but it's adequate for some problems. Code for this
is at `boozetools.parsing.general.brute_force`.

> At this point, I would like to break the flow with an operational concern.
> What do we do about side effects of reduction rule actions? When a parser
> is in a non-deterministic situation, should the action run or not?
> 
> There are two reasonable responses. One is to require actions to be pure
> functions without side effects. The other is to attempt gymnastics to delay
> the invocation of actions until any ambiguity is resolved.

Tomita was concerned with parsing strings of natural language where
ambiguity and puns run rampant. Rather than a tree, he used a directed
acyclic graph. If decision points
("inadequacies" in the lingo of parse tables) represent fan-in, then fan-out
must be caused by cases where there is more than one viable rightmost
derivation leading to the same HFA state. This, along with suitable handling
of reduction rules, is Tomita's idea, although his original algorithm had a
few limitations which other authors have since fixed.
Code for an algorithm in this family is at `boozetools.parsing.general.gss`.

> Tomita's Graph-Structured Stack approach also has the advantage of
> identifying puns at the earliest possible point. This means you can
> either record them as such or decide which rule to respect. It easily
> eliminates double-work for shared sections of the parse tree. However,
> it does not completely eliminate the need for care with side effects.

In many applications, most of the
parsing steps are deterministic. If your branching factor
is relatively low, you can win by keeping a portion of a deterministic stack
in each graph node and using the ordinary LR parsing algorithm as much as
possible, because it runs much faster. In particular, reductions which
consume no more than the deterministic suffix of a stack need not invoke
graph algorithms. This is the approach taken by the
"Elkhound" engine, and it works pretty well. Their example application is
parsing C++: its most natural context-free grammar is ambiguous, but only in
small ways which are resolved by preferring one production over another.
Code for this idea is not here yet, but it's planned.

Still other, deeper magics have been discovered which require various
interventions and pre-processing. Indeed, GLR efficiency is apparently
still wide open for research. Two directions of development I've seen
are to significantly reduce stack activity and to bound the work factor
of popping a stack. Code for any of these ideas is beyond the current
scope of this package.


## A few bits on implementation:

It's about this point that the necessary interface to a non-deterministic
parse table is made plain: GOTO can work just like in the deterministic case
(because it's not affected by non-determinism) but ACTION needs the
additional skill to store non-deterministic entries. There are a thousand
ways to do it. One way? Any instruction greater than the maximum valid state
number refers instead to a "non-determinism" entry consisting of a list of
shift/reduce instructions. Another would be to use numbers more negative than
the number of rules. I'm not bumming cycles right now, but at the moment the
second way seems probably slightly more efficient. It's a pity I've already
written it the first way... Ah well. Maybe I'll build a test someday.

