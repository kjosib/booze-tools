# Bipartite Propagation Closure:

Suppose a graph. Each node has an input frontier and an output frontier.
There are two kinds of nodes:

In one kind, if ALL inputs become active, then the output is active. Call this a conjunct. (If it has no input, the output is active.)
In the other, if EVEN ONE input becomes active, then the output is active. Call this a disjunct. (And conversely.)
Say, then, that conjuncts and disjuncts alternate; and they even have their own namespace (or numbering, if you prefer).

The question, then, is what sort of algorithm makes sense to propagate signal through this kind of network.

Now it happens the graph is bipartite, in this sense:

*For epsilon computation:*
A rule is conjunct from its symbols. A symbol is a disjunct from all its rules (or at least those without terminals.)
The initial set of rules are the empty ones. (Or perhaps you consider their symbols.)

*For well-foundedness:*
A rule is an AND gate over symbols; a symbol is an OR gate from rules.
The initial set of symbols are the terminals.

=============

How can you deal well with this?

It's a data-flow problem with a pleasing symmetry. It should have a work-flow solution involving, say, three or four colors.

Suppose we break the problem into a game of tennis: alternately dealing with disjuncts that need to be shaded and conjuncts that need it.
Each conjunct (rule) holds a count of remaining inputs (symbols). Each disjunct (symbol) holds a list of outputs (rule IDs) mentioning that symbol. Critically, if the rule mentions the same symbol more than once, then the rule appears more than once in the symbol's rule-list.

You process a disjunct by subtracting one from the count associated with each output conjunct.
If any hit zero, their collective output (which will be again a disjunct (symbol)) becomes eligible for the next round.

All of this means a transitive closure, but with one special complication: there's a stateful collaboration among the conjunct nodes.

=============

*Coda:* Thinking this problem through as a graph algorithm (and trying to ignore the semantics, and getting some sleep)
yielded a much better solution than the ad-hoc brute-force ideas that came before. As of this writing, you can find the
result as the `bipartite_closure` method on the `ContextFreeGrammar` class. With theory firmly in mind, practice finally
became possible.

Even still, the method *as now coded* is stil interwoven with the specific structure of the class.
If and when applications for this algorithm come up in different places, I'll have another look at factoring it further.

