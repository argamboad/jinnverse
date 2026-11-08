# What the model reads last

Step 25 began with a message from the owner: the lorebook chat had been a disaster. It ended
four days later with a one-line change to the builder, a lesson added to the kickoff, and three
hosts of the same model each found wanting in a different way. The feature from chapter 20 was
not the cause. This chapter is the diagnosis as it happened, because the method taught more than
the fix: which instruments the app already had, which suspects were cleared in which order, and
how a prompt that was right about the cache turned out to be wrong about its end.

## Two chats, two failures that looked alike

The lorebook chat on the split *BJU · Lorebook* card had 18 replies and 9 of them hidden: the
owner had rerolled half of it. Five replies collapsed partway into word salad, two of them to the
1,600-token ceiling, and one narrated the lore layer itself as a document in the scene. The
accepted replies carried odd phrases too: "beelines to people with sunscreen and studio light
work, nicer attitudes."

The normal chat on the original 26,600-token card looked different and was called the same
thing. From reply 74 on, the model answered with rules instead of the scene: "No numbered
sections, no bold, no letters", then the dials list recited back with "Lust: Unhinged" first,
then "If changes to the scene title or to a character's outfit or mood would break this rule,
simply leave them as they are." The owner kept five such replies visible, and from then on each
reply copied the last, until the final one was 78 tokens of nothing but instructions and the
same message had been sent six times into it.

Salad and recited rules are different failures. One is sampling drifting token by token; the
other is the model answering the wrong message. They had one thing in common that took four
days to find.

## The instruments the app already had

Nothing was added to find this. Every figure below came from three places chapter 3 and chapter
7 built, read from Neon without writing a row:

- **The ledger.** One `spend` row per billed call, with `provider`, `prompt_tokens`,
  `cached_tokens` and `cost`. It is the only record of *who* wrote a reply, and it survives a
  purge: 1,686 replies since October 8, every one from the same host, GMICloud.
- **The audit line** on each reply: `character 26610 · persona 756 · directives 274 · world 1154
  · summaries 11558 · history 44319 · memories 1871 · status 406 · reminders 38 · total 86986/90000`.
  Per layer, per turn, for every reply including the hidden ones.
- **The hidden replies.** A reroll hides the old reply and keeps it (chapter 3). The visible
  transcript shows what the owner accepted; the hidden rows show what the model actually
  produced, which is the evidence. Nine of eighteen, eighteen of fifty-seven.

::: dotnet
This is what structured logging with a correlation id buys in ASP.NET Core, except that here the
log *is* the data: a row per call in the same database as the story, joinable by `story_id`.
Application Insights would show the same figures as custom dimensions; the difference is that
nothing had to be remembered to turn on. The lesson from chapter 3, *audit every reply*, paid for
itself four weeks later.
:::

## Clearing the suspects

The suspects were cleared in the order a reader of the earlier chapters would name them, and
every one was wrong before the right one was found. That order is worth keeping.

**The lorebook.** The owner's first question, and the natural one: the feature was new. But the
normal chat's card had zero entries, no reply in it carried a `lore` figure, and the builder skips
an empty layer. Reading the diff is not proof, so the proof was built: the prompt of a card
without entries, assembled by the October 28 code and by the current code from the same inputs,
compared byte for byte. 118,466 bytes, the same SHA-256. The deploy had changed nothing the model
received.

::: dotnet
A golden-file test, done once by hand: the same approach as a `Verify` snapshot in .NET, where the
serialised output of two versions is diffed rather than asserted field by field. When the
question is "did this change anything the consumer sees", a byte comparison answers it in a way
no amount of reading does.
:::

**The dials.** The lorebook chat ran the Creativity dial at 1.2; the one chat that wrote cleanly
that week ran at 1.0. True, and a reason for the salad in that one chat, and the owner's answer
was fair: the dials are the app's own levels, and a reader using them should not get garbage.
Blaming settings is where a diagnosis goes to rest. The normal chat had no Creativity dial at all
and broke anyway.

**The status block.** Both broken chats had it on, the clean one did not, and the recited rules
were formatting rules. A good story, and wrong: the owner had used the block on this card since
the day it was built. A factor the clean chat lacks is not a cause if the broken chats had it for
weeks without harm.

**The deploy.** Every clean reply was written before the Step 24 deploy and every broken one
after. The byte comparison had already answered this, and the timing was a coincidence worth
naming as one: the owner started both BJU chats the evening the deploy went out.

What was left standing was the host and the shape of the prompt's end, and the two were separated
by changing one thing at a time.

## Three hosts, three failures

OpenRouter serves one model name from fourteen hosts, and the app had been ignoring two of them
since October for reasons nobody wrote down, which left GMICloud writing every reply for a month.
Adding it to `JINNVERSE_IGNORE_PROVIDERS` moved the chat to Baidu, and a hundred and fifty turns
followed with no salad and no rules. GMICloud was the salad. Then Baidu refused an explicit
scene, politely and in full, with a model that refuses nowhere else: a content filter in front of
it, or a safety-tuned copy. Preferring SiliconFlow produced four replies in a row that were the
trailing system text, 17 to 133 tokens each, at a cent a call, because SiliconFlow keeps no
prompt cache and the prompt was 88,000 tokens.

| Host | Quantisation | At 88,000 tokens | Caches | Refuses |
|---|---|---|---|---|
| GMICloud | fp8 | word salad, then recited rules at 43,000 | yes | no |
| Baidu | fp8 | clean, 150 turns | yes | explicit scenes |
| SiliconFlow | fp8 | recited rules, 4 of 4 | no, ~1 cent a reply | no |

The kickoff said hosts differ in caching and in returning garbage. They also differ in what they
refuse and in what they tolerate, and the same model name is not the same model. The lever the app
has is the `provider` routing object from chapter 3, ignore and prefer by slug; it will not route
by content, for the reasons chapter 20 gave.

## The defect: a chat has no "post-history" slot

Here is what GMICloud at 43,000 tokens and SiliconFlow at 88,000 had in common with each other
and not with Baidu. Chapter 5 laid the prompt out least volatile first, for the prefix cache, and
put retrieval after the history for the same reason. Step 7's reminders, step 11's status block
and step 24's lore joined it there. So the prompt ended like this:

```
assistant   *Debby leads you inside…*
user        Hostias! A Oberheim Polyphonic Synthesizer…
system      Earlier in this conversation: …
system      Every reply begins with a status block … Where things stand now: …
system      Standing instructions for this reply, set above and repeated here: …
```

The reader's turn was never the last thing the model read. SillyTavern calls the same idea
"post-history instructions" and gives it a slot in its prompt manager, which hides what it is:
in a chat-completions API there is no slot, only a list, and a trailing `system` message is a
message like any other. A model is trained to answer the last message. On a 10,000-token prompt
the user turn two messages up still dominates; on a 45,000-token one, with 500 tokens of rules
in the last position, some hosts' deployments answered the rules. The recited text was always
the content of those trailing messages, paraphrased, and once a few such replies were kept in the
transcript the model had an example to copy. That is the fingerprint, and it was in the data from
the first hour. It took four days to read because the first three suspects were more
interesting.

The fix is the shape of the end:

```python
    messages = [m for m in before if m is not None]
    transcript = [ChatMessage(turn.role.value, turn.text) for turn in history]
    trailing = [m for m in after if m is not None]
    if instruction is not None:
        trailing.append(instruction)
    if transcript and transcript[-1].role == "user":
        messages += [*transcript[:-1], *trailing, transcript[-1]]
    else:
        messages += [*transcript, *trailing]
```

When the transcript ends on the reader's turn, everything that changes with the scene goes in
before it and the reader's own words close the prompt. When it ends on a reply, carry on from
chapter 7, the instruction is already the reader's turn and closes it as before. `ORDER`, the
caps, the budget and the audit line did not change: this is where the messages sit, not what they
cost. The cached prefix loses one message, the newest turn, which the status block changing every
turn was already costing.

::: dotnet
With `Microsoft.Extensions.AI` or Semantic Kernel the same list is a `List<ChatMessage>`, and
the same mistake is as easy: append a `ChatRole.System` note after the user's message because
"system outranks user". The role names the author, not the priority. If a model must read
something last, make it the user's turn or put it before the user's turn; there is no third
position.
:::

The tests that pinned the old positions were the cost of the change, and the useful part of it.
Nine files asserted that a layer was `sent[-1]` or that the reader's message was `sent[-2]`.
Each moved by one, and two new builder tests say the rule out loud: every scene layer between the
previous reply and the reader's newest turn, in `ORDER`; after a reply, the instruction closes the
prompt. A test that pins a position is a test that will complain when the position matters, which
is exactly when you want it to.

::: warning
A frame that says "this is a note, not a message" is necessary and not sufficient. The regenerate
directive of chapter 7 says precisely that, and at 88,000 tokens SiliconFlow read it back as the
reply. Where a message sits outranks what it says about itself.
:::

## What the step cost

One builder change of eleven lines, nine test files moved by one position, two new tests, three
lessons in the kickoff, a chapter, and no migration. Around four hours of reading Neon and the
Render logs beside the owner, and about three cents of model calls, most of them SiliconFlow's.
Two things were taken out of the way for good: GMICloud is ignored, and the budget lesson now says
what a budget is relative to.

What was not done, and is the owner's issue (#283): the host for the BJU card at 88,000 tokens,
chosen between Baidu, which writes and caches and refuses, and a host not yet tried; and the
comparison chapter 20 promised. Both cards have now been played on the same host for the same
opening, not under controlled conditions, and the figures at the fifteenth reply are already the
whole argument:

| | Original card | Lorebook card |
|---|---|---|
| character | 26,610 | 3,882 |
| lore | — | 3,518 |
| history at the fifteenth reply | 2,541 | 1,785 |
| total | 30,454 | 10,456 |

Twenty thousand tokens a turn, for forty-three sheets of people who were not in the room. The
controlled version, ten turns on one host with both cards, goes into this table when #283 is done.

The lesson of the step is the title. The prompt was designed from the top down, for the cache,
and every layer added since took the last slot because it was the cheapest one. Nobody asked what
the model would make of the end. It made of it exactly what a model makes of the last message:
the thing to answer.
