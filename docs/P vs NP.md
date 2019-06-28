# Why `P < NP` must be:

There must be a function in P whose inverse is not.

The inverse of a function in P is trivially in NP: Either reverse all the
"arrows" of the forward-program, or apply the following infinite-monkeys construction:

	0. Assume a program (deterministic or otherwise) computes a function of the left-tape.
	1. Non-deterministically either write any symbol (space or mark) and move right, or
	2. Execute the deterministic computation until it would halt, and then
	3. Compare the result against the intended post-image:
		a. Halt/succeed if they match.
		b. Loop/expire otherwise.


The major stumbling block is the imprecise way that complexity-class `P` is defined:
it says the deterministic work factor is polynomial in the size of the input, but
leaves unspecified the degree of that polynomial. Fortunately, there is a way to
attack this particular Hydra: prove that the only relevant polynomial is **LINEAR.**

I'd better support that assertion.

## Lemma: Linear Time is Sufficient Consideration.

An algorithm either consults its entire input or it does not.

* If it does, then at least consulting the input is at least linear in the input.
* If it does not, then it rules some portion of that input out from consideration
	either by non-deterministic oracle or by means of a transitive relation over
	equivalence-classes on the (abstract) addresses of the inputs. The algorithm
	is then linear over the portion of the input which it DOES consult in making
	its computations about the transitive relation on equivalence classes.

An algorithm which not linear in the size of the input is still linear in the size
of some other object: to wit, its "search path" which is equivalent to the number
of decisions taken to arrive at its conclusion.

The search path is smaller than the search-space only so far as decisions can be made
to rule out portions of that search-space. For example: consulting an element of an
unsorted array can rule out that one element. Consulting an element of a sorted array
can rule out approximately half the remaining search space. Either form of search is
linear in the number of elements consulted because the relevant comparison takes
constant time (assuming random-access memory). But a non-deterministic machine can
rule out half the search space simply by taking a correct non-deterministic guess,
regardless of any ordering relation between the elements of an array.

We take as a constant-time step any concrete, discrete ALU-type decision, and
also each bit's worth of non-determinism yanked from the ether. The remainder
contributes at most a constant factor of overhead about which we do not care.

A nondeterministic search can therefore operate in logarithmic time on an unsorted
array, because it can spend the first log(N) steps consulting the oracle for bits
of the answer and then "collapse the waveform" by a constant-time "verification".

**OBJECTION:**
Even a nondeterministic Turing machine must still spend linear-time traversing the
tape out to the correct answer?

**Reply:**
Yes, but just to *test* the answer, not to generate it. That linear factor is exactly
compensated by the deterministic machine having to *test each* hypothesis, which
presumably takes linear time *each time* in the Turing model. For unsorted search,
non-determinism saves a power of `N` in the asymptote.

**OBJECTION:**
The deterministic TM could simply drag a copy of the needle through the haystack.

**Reply:**
Consider the work-factor to actually write out an answer: Unary or binary?
Where should it start? The classical Turing-machine formulation leaves a great
many things unspecified. Just assume random-access memory and go with it.

**Synthesis:**
Unsorted search is an extreme example of a particular kind of function: one for
which no transitive relation can be relied upon to partition the search space, and
accordingly no deterministic test can rule out any constant fraction of that space
in less than linear time.

It is exactly those functions for which non-determinism poses a clear advantage.

More to the point: That a deterministic unsorted search *must* be linear follows directly
from the observation that "you have to look". But unquestioned goes that observation! *Why*
must we look? The answer is that, without looking, we do not know: and why should it matter
whether "looking" is done by retrieving a value from memory OR by composing that value
just in time? The former can be done in constant time, while the later may not be so quick.
A non-deterministic machine simply *posits* that *some* answer exists (without computing)
and later just collapses into the state of having selected the correct one. A deterministic
machine is not so lucky: unable to try all possible answers in parallel, it must resort to
trying possible answers one-at-a-time.

## Upper and Lower Bounds on the Power of Non-Determinism.

Obviously non-determinism buys you nothing for, say, addition: verifying the answer is
indeed the same operation as computing it in the first place no matter how big the inputs.

Now consider sorting as a search for a correct permutation. The verification is easy:
you check sortedness by observing the correctness of all neighboring pairs, of which
there are linearly many. Additionally, there are `log(n)` bits of the final position
for each element of the permutation, which (together) form a clear argument why
`O(n*log(n))` is indeed the best you can hope for in a deterministic, comparison-based
sort algorithm. Can non-determinism do any better? Assuming each oracular consultation
yields at most one bit of "just-so" data, then not by more than a constant factor.
Why? It takes at least as many decisions (whether by comparison or by magic) and indeed
every necessary decision can be made deterministically with respect to a transitive
relation over the search space (as evidenced by, say, Quick-Sort or Merge-Sort).

You want to know if a graph has a Hamiltonian Path? A non-deterministic machine can
do it in time proportional to the size of the certificate, which is the path itself.
It's not just polynomial. It's *linear* in the bits that count. Oh sure, there is some extra factor to do
things like check if a node is listed twice in a purported path, but that does not
hurt the argument because those sub-programs are all clearly in P (since verifying
the certificate overall is), so they may as well be deemed constant-time for our
purpose, which is to drive a clear logical wedge between P and NP. The question is
whether non-determinism affords an exponential advantage in a case like this.

The thrust of the argument is that non-determinism gives you two very specific,
unreasoningly-powerful tools:
1. The ability to take a "correct decision" without knowing why it's correct until
later. This violates a fundamental law of logic, which is that the cause must precede
the effect: a deterministic system must therefore learn the cause first before finally
taking the decision.
2. The ability to stack as many such "correct decisions" as you like before
having to discern the reasons behind any of them, which creates a Towers-of-Hanoi
style exponential-exhaustive search for causality in the deterministic model.

**Summary So Far:**
Nondeterministic machines can compute at least certain things in constant or logarithmic
time for which deterministic machines clearly must use linear (or polynomial) time.
That is to say `N.LOGTIME >= D.LINEARTIME`. Inverting the logarithm strongly suggests
that `N.LINEARTIME >= D.EXPTIME`, but it's just a suggestion. It relies on the assumption
that the deterministic system cannot be so organized to produce better results. Indeed
we have seen some example problems where nondeterminism buys you nothing.

**OBJECTION:**
At about this point, the skeptic might simply say I've only proved exhaustive search
is exhaustive: a trivial circularity. *What if*, as the search space grows past some
ridiculously-large polynomial of N, *you could* deterministically collapse large constant
fractions of it back in on itself?

**Reply:**
Were that to be true, it would be after some particular degree of polynomial -- let's say
`N^120`, because there are only about `10^120` particles in the universe, so that's as
good a stopping point as any. And so there's a little bit more work to do.

## Lemma: There are no universal optimizers.

A universal optimizer purports to compute, in fewer than K total steps, what some
other program computes in K steps, for ALL values of "some-other-program".

The number of distinct functions computable in K steps is more than are computable
in fewer-than-K steps.

Suppose it were otherwise for some K: then K steps of simulation would be sufficient
to operate a general halting oracle. It is not.

Corresponding arguments apply whether you allow non-determinism or not.

## Lemma: Closure under UNION.
Consider the set of all initial-conditions and final-conditions for which some
arbitrary (maybe-deterministic) Turing machine halts (by entering a designated HALT
state). This forms a relation: initial-configuration to final-configuration.

Non-deterministic Turing machines are closed under **UNION**: If you *add* new instructions
to a prior Turing machine, you *cannot decrease* the number of distinct final configurations
in which the machine may halt, or the number of distinct initial configurations for which
the machine does halt (in at least one way). Equivalently, by removing rules one cannot
increase (but may decrease) the size of the corresponding relation.

By simply throwing both sets of rules into the same machine (with appropriate state
renaming), a nondeterministic machine can compute the union of any two functions
in the same number of steps as either function individually. In that sense, the machine is
literally in two states at once, and thus (in some sense) performing twice the computation
per step as either machine independently. But what is that sense?

## Lemma: Deterministic Bounded Halting is Deterministic-Complete.
Deterministic Bounded Halting is the question whether, given some particular program and
initial condition, a deterministic Turing machine would halt within K steps. A general
solution cannot on average do better than direct simulation because it could
then be submitted to itself and count as a universal optimizer (which cannot exist).

For the sake of argument, let us assume simulation carries zero overhead
and consider the question of whether either of two distinct deterministic
machines (or equivalently, the same program for distinct initial conditions)
halts within K steps.

We have essentially three options:

1. We can simulate the two machines in lock step: Call this breadth-first.
2. We can simulate one machine and then the other: Call this depth-first.
3. We can attempt to show the machines K-equivalent in less than 2K' steps on average.
Call this impossible, because (as mentioned) there are no universal optimizers.

Conclusion: The number of simultaneous configurations is the work factor to simulate
those configurations; there are no shortcuts.

## Lemma: Non-deterministic Bounded Halting is EXPTIME-hard.

Letting arbitrary non-determinism into the mix allows a Turing machine to be in
a power-set of configurations, any element of which counts as distinct for the purpose of
the bounded-halting question. After K bits of non-determinism up to 2^K deterministic
steps may be required to simulate each step: shrinking this number requires recognizing
Turing-equivalent configurations, which (by the no-universal-optimizers lemma) we can do
no faster on average than exhaustive simulation.

## Lemma: There is a minimal (linear-size) certificate of Bounded Halting:

Simply taking note of the history of non-deterministic rule choices as they are made
is sufficient to generate this certificate: A deterministic machine may then verify
halting by direct simulation, but consulting the certificate whenever a non-deterministic
choice presents itself. A valid certificate will lead to a halted simulation.

No smaller certificate is worthwhile: a simulator would then have to consider both
options for at least some non-deterministic choice, and this would get exponential
in the number of missing certificate bits.

# CONCLUSION: There is a function in P whose inverse is not.

Verifying a certificate of non-deterministic bounded halting is clearly in P,
but coming up with that certificate was shown not to be.
