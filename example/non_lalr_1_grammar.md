# Simple LR(1) but NOT LALR(1) Grammar

This is a simple example of something that breaks the LALR(1) algorithm. As such, it makes a good test case
for something smarter. It's also a useful case to show that the MacroParse compiler does something sensible
despite the lack of a scanner definition here.

# Productions S:
```
S -> a X d    :one
S -> a Y e    :two
S -> b X e    :three
S -> b Y d    :four

X -> c    :as_X
Y -> c    :as_Y

```
This grammar clearly means to produce the four strings { `a c d`, `a c e`, `b c d`, `b c e` }, and application
of canonical LR(1) yields a parse table that recognizes all four strings without any trouble.

In LALR(1), we first build the LR(0) state table and then consider which look-aheads should result in which
actions within each state. Because LR(0) isn't concerned with look-ahead, it yields a single state (call it
California) containing the core: `{ (X -> c .), ( Y -> c .)) }` -- i.e., about to recognize a `c` as either
an `X` or a `Y` -- and reaches that same state from each of two predecessors, depending on whether the
prefix was `a c` or `b c`.

The problem is that the correct reduction depends on more than just the look-ahead. It depends also on the
path by which California was reached.

# Solving The Problem:

There are a number of approaches and trade-offs. Canonical LR(1) is certainly an option, but for practical
grammars it remains prone to producing unconscionably-large, redundant tables. IELR(1) is another option,
but frankly I find the official description [1] a bit hard to follow.

I suspect the following would accomplish much the same, so it's an avenue for exploration:

1. Use the LR(0) subset construction to generate a NON-DETERMINISTIC parse table.
2. Follow the ordinary LALR(1) approach to determine the first- and follow-sets for each action.
3. Identify conflicts by `<LR(0) state, production, look-ahead>` triples.
4. Trace these conflicts back to their apparent source, which is any LR(0) `<state, leftmost-parse-item>`
pair which leads to the conflicted state; annotate these with the conflicting `<production, look-ahead>` pairs.
5. Test the annotations: `lookahead in self.shifts[production.head].first_set`  
6. If at least one annotation "fails", that identifies a "false conflict". Perform a modified LR(x)
subset construction in which conflicted productions get the canonical treatment specifically for their
viable look-aheads (as identified during steps 1 and 2) but non-conflicting productions do not.
7. Finally, apply precedence declarations to disambiguate any remaining shift-reduce conflicts.

What if instead `c` were a non-terminal? Then reducing TO `c` would be unambiguous but the next further
reduction would have the conflicts on `d` and `e`, and the above would solve them. Furthermore, the
(non-initial) states within the recognition of the non-terminal version of `c` would not contain any
blameworthy parse-items, so they would not be needlessly duplicated.

What if, after step 6, there are still conflicts? (Many practical grammars contain S/R conflicts normally
resolved by precedence declarations or the like.) The answer is: repeat steps 2-6 as long as step 5
identifies false conflicts. Afterward, if my argument holds, then any remaining conflicts will be relative
to LR(1). Step 7 applies.

# Footnotes:
[1]
Joel E. Denny and Brian A. Malloy.
*The IELR(1) algorithm for generating minimal LR(1) parser tables for non-LR(1) grammars with conflict resolution.*
https://www.sciencedirect.com/science/article/pii/S0167642309001191
