# Context Free Error Recovery

## Abstract

Robust error handling (reporting and recovery) are an integral part of a mature
parsing system. The usual literature on parsing leaves a reader with subtle
flaws in their understanding of good error handling strategies. A naive
error handling strategy based on that literature is not too difficult to code,
but will tend to reject much larger segments, and have worse error-cascade
behavior, than what a grammar author probably expects. Particularly, the
method of "error productions" sounds promising but is easy to get wrong.
By careful consideration of the consequences of error-productions on the
contents of LR-style parse tables, it's shown how to design an error recovery
strategy that hits the high notes.

## Intro

In parsing (a.k.a. syntax-directed analysis) the usual practice for non-trivial problems is to write
a formal grammar in some variant of [BNF](https://en.wikipedia.org/wiki/Backus%E2%80%93Naur_form)
and let the computer transform that grammar into the (sub-)program which finally analyses some
input according to the grammar specification. This last program is called a "parser", and the
program that generates a parser from a grammar is, in a stroke of inspired genius, called a
"parser generator".

Anyone with recent undergraduate degree in computer science is likely to have a general idea
how parser generators work. If they're as insane as I am, they've written their own and solved
a few of the deeper mysteries in the process. But one mystery separates the men from the boys.

How shall our generated parser respond to erroneous input?

In a toy, it's enough to just abandon hope, throw an exception, abort the process.
A good parser should report the error and then attempt to recover and do as good a
job as possible of parsing the remaining input. It should also not much fall prey to
so-called "error cascades", in which poor decisions about recovery cause the parser
to badly misinterpret large fractions of the input and swamp the user with useless
or misleading error reports.

In the rest of this document, it's assumed we're dealing with a shift-reduce parser
in the LR(1) class. The LALR(1) class can also get away with the same techniques.
The differences between them are immaterial to the topic.

## Prior Art

There's actually a lot out there. We can look at the source code to highly-regarded
tools like BISON, but that's sort of cheating, so I'll not be analyzing other wares.

Search the web on the subject and you mainly find three categories of sources
in decreasing abundance:
1. Would-be tutorial and question/answer sites.
2. Notes from college classes on compilers.
3. Actual academic research papers, many of which are behind paywalls.

Therefore, here's a quick summary of what I've managed to absorb from the second category:

1. "Fast Failure" is sometimes considered a feature.

2. "Panic mode": The grammar author designates certain
tokens as "synchronizing". When an error is detected, the parser discards tokens
until a synchronizing token appears, then pops the stack until such a token can be shifted.

3. Error productions are what the big boys use, but we're not going to explain
them because the magic involved is too deep and dark. (BISON uses this.)

4. Occasionally there is mention of "automatic" recovery: this is typically presented
as an area of open research.

A real survey of the available academic research does not appear here: This document is
not really an academic paper despite adopting the general form. I'm not doing this for
school. Much of the corpus in the public domain is either dated and opaque or available
in books. And frankly, I've forgotten where or how I learned some of this stuff.

## The Naive Mechanism

_Error-productions_ seem like a reasonable choice for designing the strategy
for how a parser will respond to error conditions.

We posit a special terminal symbol (spelled `$error$` in this document) which
is not part of the lexicon but represents a string of incorrect or missing
terminal symbols. In the grammar definition, we allow this terminal to appear
in a production rule's right-hand-side (RHS) just like any other -- possibly
with the added restriction that it may not precede a non-terminal, or itself
(directly or indirectly).

During a parse, in the event of an unacceptable token, the naive mechanism
performs the following steps:

0. Notify the user -- typically by calling a pre-arranged function.
0. Pop states until the top-of-stack has a transition for `$error$`.
	* If this fails, give up on recovery.
0. Reduce as necessary and shift `$error$`.
0. Discard tokens from the input stream until arriving at one for which the
current state of the LR tables have an instruction.
0. Perform that instruction.
0. Perhaps announce that error recovery is "complete" by calling another pre-arranged function.
0. Set some flags and/or counters in such a way as to avoid calling the notification functions
again too soon before some number (usually 3) of tokens have been processed without error.

On balance, this roughly paraphrases the relevant section of the BISON manual.
However, this algorithm has a flaw.

## The Flaw in the Naive Mechanism

Suppose a typical programming language in the style of Pascal.
The grammar author might offer the following error productions:
```
statement -> $error$ ';'
statement -> BEGIN $error$ END
expression -> '(' $error$ ')'
```
On the surface, these all make perfect sense:
* A statement is usually terminated by a semicolon; an erroneous statement probably also is.
* A `BEGIN .. END` block delimits a compound statement; it can also delimit some garbage.
* A mathematical or logical expression may be enclosed in parentheses; they may also enclose garbage.

But let's see what happens if we build the tables corresponding to the naive approach!

&lt;begin hand-wavy part&gt;

Suppose some otherwise-well-formed input contains:

	x := a * (b + c ;
	y := perfectly_good_function_call;

As a human reviewer you can see at once that the problem is a missing
close-parenthesis.

Once the parser shifts that first open-parenthesis, it's in a state that
accepts the `$error$` symbol. Shift `$error$`, and now the parser is in a
state that only knows what to do about a closing parenthesis. But in reality,
we ought to also recognize the semicolon and `END` tokens as an indication that
the scope of the error is larger than the smallest enclosing error-production.

As a result, the parser will continue to spurn tokens until the next parenthetical
expression, by which point it will be confused beyond all hope of redemption.

&lt;end hand-wavy part&gt;

## The Smarter Mechanism

Let us take special note of those parse states
for which `$error$` may be -- or has been -- shifted. Let us call these
"recoverable" and "recovery" states, respectively.

From the preceding section we discern that the uppermost recoverable
state is not necessarily the correct one for recovering from whichever
sort of error may happen to present itself.

Upon entering error-recovery mode, let us instead take note of every
recoverable state presently on the stack -- or at least the most recent
occurrence of each. Then, the recovery token we seek is the first to
have a valid entry in the table for at least one of these states.

Only upon finding the recovery token, we roll the stack back to the
correct recoverable state, then process the `$error$` token and the
recovery token in the usual manner.

To make sure this all works correctly, it's preferable that recovery states
(i.e. those whose reaching-symbol is `$error$`) do not have a default-reduction.
That's because we'd like to retain the full discriminating power of the look-ahead
token to determine if that (or some deeper) state is the correct recovery state.

In the alternative, it's possible to recover the lookahead set from a point on
the stack, but this is a bit of a pain. (A method is described later on.)

## Making the Smarter Mechanism Fast

Perhaps error-recovery is allowed to be slow. Perhaps not.

Idea: If every state is marked with the minimum inbound path length to a
recoverable state, then a search for recoverable states in the stack can
probably go quite a bit faster.

Idea: Some (perhaps most) tokens can never be recovery-tokens. If you know in advance
which tokens are possibly recoverable, then skipping garbage is probably much faster.

Idea: There are only so many possible permutations of (most-recent) recoverable
states on the stack. In fact that set forms a prefix-tree: its maximum conceivable
depth is however many recoverable states there are. The tree will generally be much
more shallow. Some few nodes deep into that tree, the set of valid recovery tokens
is also determined. With a bit of pre-processing and a small table, you won't
have to scan the entire stack but only enough to decide which equivalence class
you've landed in. It's kind of like the previous idea, but situation-dependent.

To be fair, that last idea is probably overkill. But it's cool!

## Towards an Even-Smarter Mechanism

### Multi-token look-ahead for error recovery:

Recall that we usually squelch notifications of errors in the first few tokens
after purported recovery. There's a good reason for this: A wrong recovery
is a likely cause of further (and rather prompt) error detection.

Another thing a wrong recovery can do is drop states out of the stack that
otherwise would inform the correct recovery, especially if the purported
(but ill-chosen) recovery-token causes a reduce action.

So here's an idea: We don't go back to normal parsing right away, just because
we've shifted a recovery token. Instead, we SIMULATE (but do not perform)
the recovery action. (We need only an offset into the state stack, and a
small private branch stack.) We continue to work in trial-parse mode until
at least three successive tokens "shift", taking simulated reductions into
account. A failure in this mode simply means trying again from the top, either
one error-state deeper on the stack or one more token to the right. Once the
trial-parse is convinced things are smooth again, then re-process the chosen
recovery string on the real stack before reporting a successful recovery.

There are two caveats and a bonus:
* End-of-text: don't try to read past it. If you're in trial-parse mode, commit.
* Interactive parsing: An error production rule could be declared as
 "interactive", making the error response engine commit to the current
 recovery guess.
* It's no longer necessary in this scheme to prevent recovery-states from
 having default-reductions -- but still quite helpful to minimize false
 starts, and cheap enough in terms of storage, even for embedded systems.

### Better "expected-token" reporting:

It's often desirable, in an error message, to say what token was actually
observed and what (other) tokens might have made sense in that position.

Naively we might just look at the ACTION table for the current state
(the one the parser was in at the instant an error was detected) and
all possible tokens. Generally this works fine for the SHIFT set.
The complete reduce-set is often lost to the table compaction method,
particularly for states that have been coded with a default-reduction.
You can recover a (context-perfect) reduce-set from a parse stack by
recursively simulating the effects of every possible token to see if
it would eventually lead to a shift. This is a bit of work, and it
requires special care around epsilon-productions, but requires
no extra data. Much of the mechanism could be shared with the
trial-parse machinery from the previous section.

## Experiments

None. Yet. But perhaps eventually.

## Conclusion

Good error recovery is challenging. It adds significant complexity
over a basic "happy-path" parsing algorithm. But it's worthwhile.
This document has explored some issues and formulated a plan.
Everything else is a
[small matter of programming](https://en.wikipedia.org/wiki/Small_matter_of_programming).
