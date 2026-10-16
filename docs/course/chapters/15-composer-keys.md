# Keys that never arrive

Step 16 was two bug reports from the owner on the same day, one per client, and the same bug in
both: **the key for a new line never reached the composer.** In the terminal, Alt+Enter turned
Windows Terminal full screen. On the phone, the keyboard showed a Send key and nothing else. Both
fixes came from the same habit: do not ask what a key is called, ask what actually arrives.

It was three issues in one pull request: #209 for the terminal, #210 for the web, and this
chapter.

## What a terminal hands over

A terminal application does not receive *keys*. It receives characters, and a key that types no
character of its own has to be spelled with others. The old encoding, still the default
everywhere, is short:

| You press | The app receives |
|---|---|
| `a` | `a` |
| Enter | `\r`, carriage return (13) |
| Ctrl+J | `\n`, line feed (10): Ctrl plus a letter is that letter's control character |
| Alt+x | Esc, then `x` |
| Shift+Enter | `\r`, the same as Enter: there is no character for it |

That last row is why chat clients in a terminal have always struggled with Shift+Enter. The
**kitty keyboard protocol** is the modern fix: the app writes `ESC [ > 1 u` to ask the terminal
to spell ambiguous keys out in full, so Shift+Enter becomes `ESC [ 13 ; 2 u` (key 13, modifier
2 = Shift). Textual asks for it as it starts and withdraws the request as it exits, and Windows
Terminal learnt to answer it in version 1.25. On paper, Shift+Enter should have worked.

It did not, and guessing would have been expensive: in this composer a key that arrives as a
plain Enter **sends**, and a send is permanent and billed. So before choosing a key, the step
measured. Twenty lines of Textual that print every key they receive:

```python
class KeyProbe(App[None]):
    def compose(self) -> ComposeResult:
        yield RichLog()

    def on_key(self, event: events.Key) -> None:
        self.query_one(RichLog).write(f"key={event.key!r}  character={event.character!r}")
```

In the owner's Windows Terminal, Enter, Shift+Enter and Ctrl+Enter all printed
`key='enter'  character='\r'`. Indistinguishable.

The reason is in how Textual reads a *Windows* console. On Linux and macOS it reads the byte
stream, where the kitty sequences live. On Windows it reads **console input records**, one per
key event, each with the key, the character it typed and the state of the modifier keys. And it
keeps only the character:

```python
# textual/drivers/win32.py, EventMonitor.run, abridged
if event_type == KEY_EVENT:
    key_event = input_record.Event.KeyEvent
    key = key_event.uChar.UnicodeChar  # the character the key typed...
    if key_event.bKeyDown:
        append_key(key)  # ...and only that goes on to the parser
```

Shift+Enter types `\r`, so it *is* Enter by the time anything looks at it. Alt+Enter is a
different story with the same ending: Windows Terminal binds it to *Toggle full screen*, and a
key the terminal takes for itself never reaches the app at all.

::: dotnet
`Console.ReadKey()` reads the same console input records and returns a `ConsoleKeyInfo`: `Key`
(the key), `KeyChar` (the character it typed) and `Modifiers` (Shift, Alt, Control). Textual's
Windows reader keeps what .NET calls `KeyChar` and drops `Modifiers`. If you have ever written
`if (info.Key == ConsoleKey.Enter && info.Modifiers.HasFlag(ConsoleModifiers.Shift))`, that is
precisely the information that is not there.
:::

The answer is the one key in the table that *is* a character of its own: **Ctrl+J**, the line
feed. Every terminal and every driver passes a character through, and Textual's parser names
it `ctrl+j`. The composer now advertises it everywhere a key is named: the caption, the legend,
help, and the phone's hints. The other keys stay accepted, so a terminal that does tell them
apart still gets a line break:

```python
NEWLINE_KEY: Final = "ctrl+j"
"""The one the hints name: it reaches the app in every terminal."""
NEWLINE_KEYS: Final = frozenset({NEWLINE_KEY, "alt+enter", "shift+enter", "ctrl+enter"})
```

A test presses all four and expects four line breaks and no request to the server.

::: try
Run the probe in each terminal you use: Windows Terminal, VS Code's, WSL. Press Shift+Enter
and Ctrl+Enter in each. The answers can differ, and it is the terminal and the driver that
decide, not the app.
:::

## What a phone keyboard shows

The web composer had the same problem with a different cause. Its textarea said
`enterkeyhint="send"`, a hint that tells the on-screen keyboard to label its Enter key *Send*,
and its key handler sent on every Enter without Shift. A phone keyboard has no Shift+Enter, so a
turn could not have a second paragraph.

The terminal client settled this for phones in step 9 (#53): **on a touch keyboard, Enter is a
new line**, as in every other text box on the device, and only the Send button sends. The web
now follows the same rule. What it needed was a way to tell a touch keyboard from a real one,
and width is the wrong question: a tablet is wide, and a narrow desktop window still has a
keyboard. The right question is what the main pointer is:

```ts
/** A finger: the main pointer is a touch screen, so the keyboard is the one on the screen. */
export const TOUCH = '(pointer: coarse)';
```

`pointer: coarse` matches when the primary input is something imprecise, such as a finger. The
rule itself is a pure function, so vitest can test it without a browser:

```ts
export function sends(keys: Keys, touch: boolean): boolean {
	if (keys.key !== 'Enter' || keys.shiftKey) return false;
	if (keys.ctrlKey || keys.metaKey) return true;
	return !touch;
}
```

On a desk nothing changes: Enter sends and Shift+Enter breaks the line. On a touch screen Enter
breaks the line and `enterkeyhint` becomes `enter`, so the keyboard shows its usual key again.
Ctrl+Enter (Cmd+Enter on Apple) sends on both, so an iPad with a keyboard still has a key that
sends.

::: dotnet
`enterkeyhint` is MAUI's `Entry.ReturnType`: `ReturnType.Send`, `Next`, `Done`, the label on the
soft keyboard's return key. WPF's `TextBox.AcceptsReturn` is the desk half of the same question:
does Enter belong to the text, or to the window's default button? And `(pointer: coarse)` is
close to MAUI's `DeviceInfo.Idiom`, except that it asks about the input, not the device.
:::

## What this step teaches

- **Measure what arrives.** A key's name is what the app hopes for. What the terminal sends, and
  what the driver keeps of it, is what the app gets. A twenty-line probe settled in a minute
  something documentation would have got wrong.
- **A key that sends money must never be an accident.** The probe came first because a wrong
  answer would have turned "new line" into "send half a message".
- **One rule, two clients.** The terminal decided in step 9 what Enter means on a phone, and the
  web now follows it. When a behaviour is a product rule rather than a widget detail, the clients
  agree on it.
