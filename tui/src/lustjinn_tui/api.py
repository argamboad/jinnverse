"""The client's one way to the outside: the Lustjinn API over HTTP, nothing else.

airp's terminal called its services in-process; this one only speaks to the same API the PWA
uses, so the same stories are playable from either. The shapes are pydantic models of the API's
responses (the TypeScript interfaces of ``web/src/lib/api.ts``, in Python); a refusal becomes an
``ApiError`` carrying the API's own sentence, a server that cannot be reached becomes
``UnreachableError``, and a ``401`` becomes ``SignedOutError`` — three different things to a screen.

A turn is a POST that streams server-sent events: ``delta`` as the text arrives, then one
``done`` or ``error``. httpx2's ``EventSource`` cuts the stream into events; this module types
them.

.NET readers: a typed ``HttpClient`` wrapper with ``System.Text.Json`` records, and
``HttpCompletionOption.ResponseHeadersRead`` for the stream.
"""

from __future__ import annotations

import re
import ssl
import uuid
from collections.abc import AsyncIterator, Sequence
from datetime import UTC, datetime
from decimal import Decimal
from typing import Annotated, Any, Literal, cast
from urllib.parse import quote

import certifi
import httpx2
from pydantic import BaseModel, Field, TypeAdapter

from lustjinn_tui.config import TokenStore

# -- errors ------------------------------------------------------------------------------------


class ApiError(Exception):
    """The API answered, and refused. ``detail`` is its own sentence."""

    def __init__(self, status: int, detail: str) -> None:
        super().__init__(detail)
        self.status = status
        self.detail = detail


class SignedOutError(ApiError):
    """A 401: no token, or one the API no longer accepts. The token is forgotten."""


class UnreachableError(Exception):
    """No answer at all: the server is asleep, down, or the network is."""


class InterceptedError(UnreachableError):
    """Something on the way answered for the server with a certificate no public authority
    issued — what a TLS-inspecting proxy (iBoss and the like) presents. Nothing was sent."""


def public_trust() -> ssl.SSLContext:
    """Certificates are checked against the public authorities only (Mozilla's list, through
    certifi), never the machine's own store. A proxy whose root certificate was installed on the
    machine so it can read HTTPS cannot pass for the server: the connection is refused instead."""
    return ssl.create_default_context(cafile=certifi.where())


def _failed_to_connect(error: httpx2.TransportError, server: str) -> UnreachableError:
    """An unreachable server, unless the handshake was refused for its certificate."""
    seen: BaseException | None = error
    while seen is not None:
        if isinstance(seen, ssl.SSLCertVerificationError) or "CERTIFICATE_VERIFY_FAILED" in str(
            seen
        ):
            return InterceptedError(
                f"The connection to {server} was intercepted: it answered with a certificate no "
                "public authority issued, as a TLS-inspecting proxy does. Nothing was sent. "
                'With proxy = "none" in config.toml the client connects directly.'
            )
        seen = seen.__cause__ or seen.__context__
    return UnreachableError(str(error))


class ConflictError(ApiError):
    """A 409 on a library save that carries the entry as it is now, so a screen can show both
    texts and let the reader decide instead of losing either."""

    def __init__(self, detail: str, current: EntryFull) -> None:
        super().__init__(409, detail)
        self.current = current


# -- shapes ------------------------------------------------------------------------------------


class Health(BaseModel):
    status: str
    commit: str | None = None


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_at: datetime


Role = Literal["user", "assistant", "system"]


class Message(BaseModel):
    id: uuid.UUID
    sequence: int
    role: Role
    text: str
    model: str | None = None
    provider: str | None = None
    sent_at: datetime


class Story(BaseModel):
    id: uuid.UUID
    name: str
    character_id: uuid.UUID
    character_name: str
    persona_id: uuid.UUID | None = None
    persona_name: str | None = None
    created_at: datetime
    last_message_at: datetime | None = None
    last_message_preview: str | None = None


class StoryWithMessages(Story):
    messages: list[Message]


Shelf = Literal["characters", "personas", "snippets", "pieces"]


class Entry(BaseModel):
    """A library entry as a list shows it: the name and a taste of the text."""

    id: uuid.UUID
    name: str
    hidden: bool = False
    version: int
    updated_at: datetime
    preview: str
    description: str | None = None
    """The owner's short note; shown in place of the preview when there is one."""
    used: int = 0
    """How many live stories use it; always 0 for a snippet, which is copied, never used live."""


class EntryFull(Entry):
    text: str
    opening: str | None = None
    used_by: list[str] = Field(default_factory=list[str])


class Version(BaseModel):
    """One saved version of an entry, as its history keeps it."""

    version: int
    name: str
    text: str
    opening: str | None = None
    description: str | None = None
    saved_at: datetime


class Defaults(BaseModel):
    default_persona_id: uuid.UUID | None = None
    default_persona_name: str | None = None


class Hidden(BaseModel):
    characters: int = 0
    personas: int = 0
    snippets: int = 0


class Counts(BaseModel):
    """How many entries each shelf holds, as its list shows them; the pieces are counted too."""

    characters: int = 0
    personas: int = 0
    snippets: int = 0
    pieces: int = 0
    hidden: Hidden = Field(default_factory=Hidden)


Voice = Literal["he", "she", "they", "any"]


class Slot(BaseModel):
    """One of the fixed places a persona is built from, in the order a builder shows them."""

    key: str
    label: str
    paragraph: int | None = None
    """Which paragraph it writes; None for the name, which is written into the others."""


class Piece(BaseModel):
    """One piece of a persona: a slot, a voice, a name for the picker and the text."""

    id: uuid.UUID
    slot: str
    voice: Voice
    name: str
    text: str
    short: str | None = None
    description: str | None = None
    version: int = 1
    updated_at: datetime | None = None


class Preview(BaseModel):
    """The persona a pick would make, and the library name it would get (None: nothing says)."""

    name: str | None = None
    text: str


class Built(BaseModel):
    id: uuid.UUID
    name: str
    text: str


class PieceEntry(EntryFull):
    """A persona piece as the library screen shows it: an entry whose name says its slot and its
    voice, so the shelf reads grouped by slot and two pieces of one name stay apart."""

    slot: str = ""
    slot_label: str = ""
    voice: Voice = "he"
    short: str | None = None
    piece_name: str = ""
    """The piece's own name, which is what a rename changes."""


def piece_entry(piece: Piece, label: str) -> PieceEntry:
    return PieceEntry(
        id=piece.id,
        name=f"{label} · {piece.name} ({piece.voice})",
        version=piece.version,
        updated_at=piece.updated_at or datetime.now(UTC),
        preview=piece.text[:200],
        description=piece.description,
        text=piece.text,
        slot=piece.slot,
        slot_label=label,
        voice=piece.voice,
        short=piece.short,
        piece_name=piece.name,
    )


class Cut(BaseModel):
    """What deleting from a message left behind."""

    story: StoryWithMessages
    hidden: int
    summaries_removed: int = 0
    facts_removed: int = 0
    facts_reopened: int = 0


class ByKind(BaseModel):
    kind: str
    calls: int
    cost: Decimal
    unpriced: int = 0


class StorySpend(BaseModel):
    """What one story has cost: the priced calls, and the share rerolled or cut away."""

    story_id: uuid.UUID
    name: str
    calls: int
    cost: Decimal
    discarded_calls: int = 0
    discarded_cost: Decimal = Decimal(0)
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cached_tokens: int = 0
    cached_share: float | None = None
    unpriced: int = 0
    by_kind: list[ByKind] = Field(default_factory=list[ByKind])


class Fact(BaseModel):
    id: uuid.UUID
    subject: str
    text: str
    valid_from_sequence: int
    valid_to_sequence: int | None = None
    model: str | None = None
    pinned: bool = False


class Proposal(BaseModel):
    """One change a review proposes: the facts it would touch, what they become, and why."""

    action: str
    facts: list[Fact]
    subject: str | None = None
    text: str | None = None
    reason: str = ""


class Reviewed(BaseModel):
    """What a review answered — or, as a dry run, what one would cost."""

    dry_run: bool
    estimated_cost: Decimal | None = None
    based_on: int = 0
    proposals: list[Proposal] = Field(default_factory=list[Proposal])
    skipped: int = 0
    cost: Decimal | None = None


class Applied(BaseModel):
    retired: int
    added: int


class Condensed(BaseModel):
    """What a condense did — or, as a dry run, what one would merge and cost."""

    dry_run: bool
    summaries: int
    from_sequence: int | None = None
    to_sequence: int | None = None
    tokens_before: int = 0
    tokens_after: int | None = None
    estimated_cost: Decimal | None = None
    based_on: int = 0
    cost: Decimal | None = None


class Tracker(BaseModel):
    id: uuid.UUID
    name: str
    value: float
    max: float
    delta: float = 0
    note: str | None = None
    means: str | None = None
    anchors: str | None = None
    rule: str | None = None
    updated_at_sequence: int | None = None


class StatusField(BaseModel):
    """One line of the status block a story's replies open with."""

    key: str
    label: str
    icon: str | None = None
    hint: str | None = None
    kind: Literal["text", "words"] = "text"
    scope: Literal["scene", "character"] = "scene"
    words: list[str] | None = None
    enabled: bool = True
    position: int = 0


class StatusStarter(BaseModel):
    """A shipped starter field the story does not have yet."""

    key: str
    label: str
    icon: str | None = None
    hint: str | None = None
    kind: Literal["text", "words"] = "text"
    scope: Literal["scene", "character"] = "scene"


class StatusValue(BaseModel):
    field: str
    who: str = ""
    """Empty for the scene."""
    value: str
    by_hand: bool = False
    seen: int | None = None
    """The message that last wrote it."""


class StatusBlock(BaseModel):
    """A story's status block: its fields, what they hold, and who is pinned."""

    fields: list[StatusField] = Field(default_factory=list[StatusField])
    starters: list[StatusStarter] = Field(default_factory=list[StatusStarter])
    values: list[StatusValue] = Field(default_factory=list[StatusValue])
    pins: list[str] = Field(default_factory=list[str])


class TurnAudit(BaseModel):
    sequence: int
    sent_at: datetime
    hidden: bool = False
    model: str | None = None
    provider: str | None = None
    estimated_prompt_tokens: int | None = None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    context: str | None = None


class AsideAudit(BaseModel):
    sequence: int
    asked_at: datetime
    model: str | None = None
    provider: str | None = None
    estimated_prompt_tokens: int | None = None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    context: str | None = None


class Audit(BaseModel):
    turns: list[TurnAudit]
    asides: list[AsideAudit] = Field(default_factory=list[AsideAudit])


class Hit(BaseModel):
    scope: Literal["name", "message"]
    story_id: uuid.UUID
    story_name: str
    message_id: uuid.UUID | None = None
    sequence: int | None = None
    role: Role | None = None
    speaker: str | None = None
    sent_at: str | None = None
    snippet: str
    score: int = 0


class Results(BaseModel):
    hits: list[Hit]
    searched: int


ExportFormat = Literal["markdown", "json", "text"]
EXTENSIONS: dict[str, str] = {"markdown": "md", "json": "json", "text": "txt"}


class Export(BaseModel):
    filename: str
    text: str


class Shortcode(BaseModel):
    """One emoji shortcode, as ``GET /emoji`` lists it: ``:smile:`` becomes 😄."""

    name: str
    emoji: str
    keywords: str = ""

    @property
    def search_text(self) -> str:
        """What the picker's fuzzy search reads: the name, then the keywords."""
        return self.name if not self.keywords else f"{self.name} {self.keywords}"


class Spec(BaseModel):
    """One slash command the API recognises, as ``GET /commands`` lists it."""

    name: str
    usage: str
    summary: str
    cost: Literal["free", "billed", "write"]
    needs_argument: bool = True


class DialLevel(BaseModel):
    label: str
    text: str | None = None
    value: float | None = None
    description: str | None = None


class DialOption(BaseModel):
    key: str
    label: str
    text: str


DialKind = Literal["scale", "toggle", "choice", "list", "text"]


class Dial(BaseModel):
    """One dial of the pack, with the text each level or option sends."""

    key: str
    kind: DialKind
    lever: str = "prompt"
    maps: str | None = None
    enabled: bool = True
    default: str | None = None
    title: str
    help: str = ""
    levels: list[DialLevel] = Field(default_factory=list[DialLevel])
    options: list[DialOption] = Field(default_factory=list[DialOption])
    on_text: str | None = None
    template: str | None = None
    accepts: str | None = None
    examples: list[str] = Field(default_factory=list[str])


class StoryDial(BaseModel):
    """One dial as it stands for one story."""

    key: str
    title: str
    kind: DialKind
    enabled: bool = True
    stored: str | None = None
    effective: str | None = None
    label: str | None = None


class Aside(BaseModel):
    id: uuid.UUID
    sequence: int
    question: str
    answer: str
    model: str | None = None
    provider: str | None = None
    asked_at: datetime


class Delta(BaseModel):
    """A piece of the reply, as it arrives."""

    text: str


class TurnDone(BaseModel):
    kind: Literal["turn"] = "turn"
    sent: Message | None = None
    reply: Message
    replayed: bool = False


class AsideDone(BaseModel):
    kind: Literal["aside"] = "aside"
    aside: Aside


class Said(BaseModel):
    """An answer shown once and stored nowhere: a recap, a tracker set by hand."""

    kind: Literal["said"] = "said"
    text: str


class Failed(BaseModel):
    kind: Literal["error"] = "error"
    detail: str
    sent: Message | None = None


Done = Annotated[TurnDone | AsideDone | Said | Failed, Field(discriminator="kind")]
Event = Delta | TurnDone | AsideDone | Said | Failed

_stories = TypeAdapter(list[Story])
_entries = TypeAdapter(list[Entry])
_versions = TypeAdapter(list[Version])
_slots = TypeAdapter(list[Slot])
_pieces = TypeAdapter(list[Piece])
_facts = TypeAdapter(list[Fact])
_dials = TypeAdapter(list[Dial])
_story_dials = TypeAdapter(list[StoryDial])
_trackers = TypeAdapter(list[Tracker])
_starters = TypeAdapter(list[StatusStarter])
_specs = TypeAdapter(list[Spec])
_shortcodes = TypeAdapter(list[Shortcode])
_done = TypeAdapter[TurnDone | AsideDone | Said | Failed](Done)


# -- the client --------------------------------------------------------------------------------


class Api:
    def __init__(
        self,
        server: str,
        tokens: TokenStore,
        *,
        direct: bool = False,
        transport: httpx2.AsyncBaseTransport | None = None,
    ) -> None:
        """``direct`` ignores the machine's proxy settings (``HTTPS_PROXY`` and the rest) and
        connects straight to the server; otherwise the client goes the way the system says."""
        self.server = server
        self._tokens = tokens
        self._client = httpx2.AsyncClient(
            base_url=server,
            transport=transport,
            verify=public_trust(),
            trust_env=not direct,
            timeout=httpx2.Timeout(30.0, read=180.0),  # a reply can take its time
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    @property
    def signed_in(self) -> bool:
        return self._tokens.read() is not None

    def _headers(self) -> dict[str, str]:
        token = self._tokens.read()
        return {"Authorization": f"Bearer {token}"} if token else {}

    # -- plumbing -------------------------------------------------------------------------

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json: object | None = None,
        params: dict[str, str] | None = None,
    ) -> Any:
        try:
            response = await self._client.request(
                method, path, json=json, params=params, headers=self._headers()
            )
        except httpx2.TransportError as error:
            raise _failed_to_connect(error, self.server) from error
        self._check(response.status_code, response)
        if response.status_code == 204 or not response.content:
            return None
        return response.json()

    def _check(self, status: int, response: httpx2.Response) -> None:
        if status < 400:
            return
        detail = _detail(response)
        if status == 401:
            self._tokens.forget()
            raise SignedOutError(status, detail)
        if status == 409:
            current = _current(response)
            if current is not None:
                raise ConflictError(detail, current)
        raise ApiError(status, detail)

    async def _stream(self, method: str, path: str, json: object | None) -> AsyncIterator[Event]:
        try:
            async with self._client.stream(
                method, path, json=json, headers=self._headers()
            ) as response:
                if response.status_code >= 400:
                    await response.aread()
                    self._check(response.status_code, response)
                async for event in httpx2.EventSource(response):
                    if event.event == "delta":
                        yield Delta.model_validate_json(event.data)
                    elif event.event in {"done", "error"}:
                        yield _done.validate_json(event.data)
        except httpx2.TransportError as error:
            raise _failed_to_connect(error, self.server) from error

    # -- open to anyone ---------------------------------------------------------------------

    async def health(self) -> Health:
        return Health.model_validate(await self._request("GET", "/health"))

    async def sign_in(self, username: str, password: str) -> Token:
        issued = Token.model_validate(
            await self._request(
                "POST", "/auth/sign-in", json={"username": username, "password": password}
            )
        )
        self._tokens.write(issued.access_token)
        return issued

    def sign_out(self) -> None:
        self._tokens.forget()

    # -- stories ------------------------------------------------------------------------------

    async def stories(self) -> list[Story]:
        return _stories.validate_python(await self._request("GET", "/stories"))

    async def story(self, story_id: uuid.UUID) -> StoryWithMessages:
        return StoryWithMessages.model_validate(await self._request("GET", f"/stories/{story_id}"))

    async def create_story(
        self,
        name: str,
        character_id: uuid.UUID,
        persona_id: uuid.UUID | None = None,
    ) -> StoryWithMessages:
        body: dict[str, object] = {"name": name, "character_id": str(character_id)}
        if persona_id is not None:
            body["persona_id"] = str(persona_id)
        return StoryWithMessages.model_validate(await self._request("POST", "/stories", json=body))

    async def rename_story(self, story_id: uuid.UUID, name: str) -> Story:
        return Story.model_validate(
            await self._request("PATCH", f"/stories/{story_id}", json={"name": name})
        )

    async def delete_story(self, story_id: uuid.UUID) -> None:
        await self._request("DELETE", f"/stories/{story_id}")

    async def branch(
        self, story_id: uuid.UUID, message_id: uuid.UUID, name: str | None = None
    ) -> StoryWithMessages:
        """A copy of the story up to that message, under ``name`` or one the server picks."""
        return StoryWithMessages.model_validate(
            await self._request(
                "POST",
                f"/stories/{story_id}/branch",
                json={"message_id": str(message_id), "name": name},
            )
        )

    async def delete_from(self, story_id: uuid.UUID, message_id: uuid.UUID) -> Cut:
        return Cut.model_validate(
            await self._request("DELETE", f"/stories/{story_id}/messages/{message_id}")
        )

    async def story_spend(self, story_id: uuid.UUID) -> StorySpend:
        return StorySpend.model_validate(await self._request("GET", f"/stories/{story_id}/spend"))

    # -- what a story holds beside its turns -------------------------------------------------

    async def facts(self, story_id: uuid.UUID, *, all: bool = False) -> list[Fact]:
        """The live facts, or every fact there ever was with ``all``."""
        params = {"all": "true"} if all else None
        return _facts.validate_python(
            await self._request("GET", f"/stories/{story_id}/facts", params=params)
        )

    async def add_fact(self, story_id: uuid.UUID, subject: str, text: str) -> Fact:
        return Fact.model_validate(
            await self._request(
                "POST", f"/stories/{story_id}/facts", json={"subject": subject, "text": text}
            )
        )

    async def review_facts(self, story_id: uuid.UUID, *, dry_run: bool = False) -> Reviewed:
        """The model's proposals for the live facts — billed — or, with ``dry_run``, only what
        the call would cost."""
        params = {"dry_run": "true"} if dry_run else None
        return Reviewed.model_validate(
            await self._request("POST", f"/stories/{story_id}/facts/review", params=params)
        )

    async def apply_review(self, story_id: uuid.UUID, confirmed: Sequence[Proposal]) -> Applied:
        """Applies the proposals the reader kept, all or none. No model call."""
        body = [
            {
                "action": p.action,
                "fact_ids": [str(f.id) for f in p.facts],
                "subject": p.subject,
                "text": p.text,
            }
            for p in confirmed
        ]
        return Applied.model_validate(
            await self._request("POST", f"/stories/{story_id}/facts/review/apply", json=body)
        )

    async def condense(
        self, story_id: uuid.UUID, count: int | None = None, *, dry_run: bool = False
    ) -> Condensed:
        """Merges the oldest ``count`` summaries (all but the newest when not given) into one —
        billed — or, with ``dry_run``, says what it would merge and cost."""
        params: dict[str, str] = {}
        if count is not None:
            params["count"] = str(count)
        if dry_run:
            params["dry_run"] = "true"
        return Condensed.model_validate(
            await self._request(
                "POST", f"/stories/{story_id}/memory/condense", params=params or None
            )
        )

    async def trackers(self, story_id: uuid.UUID) -> list[Tracker]:
        return _trackers.validate_python(
            await self._request("GET", f"/stories/{story_id}/trackers")
        )

    # -- the status block ---------------------------------------------------------------------
    # Every change answers with the whole block, so a screen draws one response.

    async def status_starters(self) -> list[StatusStarter]:
        """The shipped starter fields, which need no story: the new-story form offers them."""
        return _starters.validate_python(await self._request("GET", "/status-starters"))

    async def status_block(self, story_id: uuid.UUID) -> StatusBlock:
        return StatusBlock.model_validate(await self._request("GET", f"/stories/{story_id}/status"))

    async def adopt_status_fields(self, story_id: uuid.UUID, keys: list[str]) -> StatusBlock:
        return StatusBlock.model_validate(
            await self._request("POST", f"/stories/{story_id}/status/adopt", json={"keys": keys})
        )

    async def add_status_field(
        self,
        story_id: uuid.UUID,
        label: str,
        *,
        scope: str = "character",
        words: list[str] | None = None,
    ) -> StatusBlock:
        body: dict[str, object] = {
            "label": label,
            "scope": scope,
            "kind": "words" if words else "text",
            "words": words or None,
        }
        return StatusBlock.model_validate(
            await self._request("POST", f"/stories/{story_id}/status/fields", json=body)
        )

    async def change_status_field(
        self, story_id: uuid.UUID, key: str, **changes: object
    ) -> StatusBlock:
        return StatusBlock.model_validate(
            await self._request(
                "PATCH", f"/stories/{story_id}/status/fields/{quote(key, safe='')}", json=changes
            )
        )

    async def remove_status_field(self, story_id: uuid.UUID, key: str) -> StatusBlock:
        return StatusBlock.model_validate(
            await self._request(
                "DELETE", f"/stories/{story_id}/status/fields/{quote(key, safe='')}"
            )
        )

    async def set_status_pins(self, story_id: uuid.UUID, names: list[str]) -> StatusBlock:
        return StatusBlock.model_validate(
            await self._request("PUT", f"/stories/{story_id}/status/pins", json={"names": names})
        )

    async def set_status_value(
        self, story_id: uuid.UUID, field: str, who: str, value: str
    ) -> StatusBlock:
        """What a field holds, for the scene (``who`` empty) or one character; blank clears it."""
        body = {"field": field, "who": who or None, "value": value}
        return StatusBlock.model_validate(
            await self._request("PUT", f"/stories/{story_id}/status/values", json=body)
        )

    async def audit(self, story_id: uuid.UUID) -> Audit:
        return Audit.model_validate(await self._request("GET", f"/stories/{story_id}/audit"))

    async def search(self, query: str, story_id: uuid.UUID | None = None) -> Results:
        params = {"q": query}
        if story_id is not None:
            params["story_id"] = str(story_id)
        return Results.model_validate(await self._request("GET", "/search", params=params))

    async def commands(self) -> list[Spec]:
        return _specs.validate_python(await self._request("GET", "/commands"))

    async def emoji(self) -> list[Shortcode]:
        """The shortcode table both composers expand; public, and read once."""
        return _shortcodes.validate_python(await self._request("GET", "/emoji"))

    async def export(self, story_id: uuid.UUID, fmt: ExportFormat) -> Export:
        """The transcript as a document, with the file name the server suggests."""
        try:
            response = await self._client.request(
                "GET",
                f"/stories/{story_id}/export",
                params={"format": fmt},
                headers=self._headers(),
            )
        except httpx2.TransportError as error:
            raise _failed_to_connect(error, self.server) from error
        self._check(response.status_code, response)
        disposition = response.headers.get("content-disposition", "")
        found = re.search(r'filename="([^"]+)"', disposition)
        return Export(
            filename=found.group(1) if found else f"transcript.{EXTENSIONS[fmt]}",
            text=response.text,
        )

    # -- the library ---------------------------------------------------------------------------

    async def entries(self, shelf: Shelf, *, hidden: bool = False) -> list[Entry]:
        """The shelf as its list shows it; with ``hidden``, the ``_name`` entries too."""
        if shelf == "pieces":
            return list(await self._piece_entries())
        params = {"hidden": "true"} if hidden else None
        return _entries.validate_python(
            await self._request("GET", f"/library/{shelf}", params=params)
        )

    async def entry(self, shelf: Shelf, entry_id: uuid.UUID) -> EntryFull:
        if shelf == "pieces":
            found = next((e for e in await self._piece_entries() if e.id == entry_id), None)
            if found is None:
                raise ApiError(404, "There is no piece with that id.")
            return found
        return EntryFull.model_validate(await self._request("GET", f"/library/{shelf}/{entry_id}"))

    async def history(self, shelf: Shelf, entry_id: uuid.UUID) -> list[Version]:
        """Every version of an entry ever saved, newest first."""
        return _versions.validate_python(
            await self._request("GET", f"/library/{shelf}/{entry_id}/history")
        )

    async def _piece_entries(self) -> list[PieceEntry]:
        """The pool as library entries, in the persona's slot order and then by name."""
        slots = await self.piece_slots()
        labels = {slot.key: slot.label for slot in slots}
        order = {slot.key: i for i, slot in enumerate(slots)}
        pieces = sorted(
            await self.pieces(), key=lambda p: (order.get(p.slot, len(order)), p.name.lower())
        )
        return [piece_entry(p, labels.get(p.slot, p.slot)) for p in pieces]

    async def _piece_saved(self, piece: Piece) -> PieceEntry:
        labels = {slot.key: slot.label for slot in await self.piece_slots()}
        return piece_entry(piece, labels.get(piece.slot, piece.slot))

    async def save_piece(
        self,
        piece_id: uuid.UUID,
        version: int,
        *,
        voice: Voice | None = None,
        short: str | None = None,
    ) -> PieceEntry:
        """Changes a piece's voice or short form over ``version``; a stale save raises
        ``ConflictError`` with the piece as it is now."""
        body: dict[str, object] = {"version": version}
        if voice is not None:
            body["voice"] = voice
        if short is not None:
            body["short"] = short
        piece = Piece.model_validate(
            await self._request("PATCH", f"/persona-pieces/{piece_id}", json=body)
        )
        return await self._piece_saved(piece)

    async def defaults(self) -> Defaults:
        return Defaults.model_validate(await self._request("GET", "/library/settings"))

    async def set_default_persona(self, persona_id: uuid.UUID | None) -> Defaults:
        body = {"default_persona_id": None if persona_id is None else str(persona_id)}
        return Defaults.model_validate(await self._request("PUT", "/library/settings", json=body))

    async def counts(self) -> Counts:
        return Counts.model_validate(await self._request("GET", "/library/counts"))

    async def create_entry(
        self,
        shelf: Shelf,
        name: str,
        text: str,
        opening: str | None = None,
        description: str | None = None,
    ) -> EntryFull:
        body: dict[str, object] = {"name": name, "text": text}
        if opening is not None:
            body["opening"] = opening
        if description is not None:
            body["description"] = description
        return EntryFull.model_validate(await self._request("POST", f"/library/{shelf}", json=body))

    async def save_entry(
        self,
        shelf: Shelf,
        entry_id: uuid.UUID,
        version: int,
        *,
        name: str | None = None,
        text: str | None = None,
        opening: str | None = None,
        clear_opening: bool = False,
        description: str | None = None,
        clear_description: bool = False,
    ) -> EntryFull:
        """Saves what is given over ``version``; a save over a newer one raises
        ``ConflictError`` with the entry as it is now."""
        body: dict[str, object] = {"version": version}
        if name is not None:
            body["name"] = name
        if text is not None:
            body["text"] = text
        if opening is not None or clear_opening:
            body["opening"] = opening
        if description is not None or clear_description:
            body["description"] = description
        if shelf == "pieces":
            piece = Piece.model_validate(
                await self._request("PATCH", f"/persona-pieces/{entry_id}", json=body)
            )
            return await self._piece_saved(piece)
        return EntryFull.model_validate(
            await self._request("PATCH", f"/library/{shelf}/{entry_id}", json=body)
        )

    async def delete_entry(self, shelf: Shelf, entry_id: uuid.UUID) -> None:
        if shelf == "pieces":
            await self._request("DELETE", f"/persona-pieces/{entry_id}")
            return
        await self._request("DELETE", f"/library/{shelf}/{entry_id}")

    # -- persona pieces -------------------------------------------------------------------------

    async def piece_slots(self) -> list[Slot]:
        return _slots.validate_python(await self._request("GET", "/persona-pieces/slots"))

    async def pieces(self, *, voice: Voice | None = None) -> list[Piece]:
        """The pool; with a ``voice``, the pieces a persona of that voice may use."""
        params = {"voice": voice} if voice is not None else None
        return _pieces.validate_python(await self._request("GET", "/persona-pieces", params=params))

    async def create_piece(
        self,
        slot: str,
        voice: Voice,
        name: str,
        text: str,
        short: str | None = None,
        description: str | None = None,
    ) -> Piece:
        body: dict[str, object] = {"slot": slot, "voice": voice, "name": name, "text": text}
        if short is not None:
            body["short"] = short
        if description is not None:
            body["description"] = description
        return Piece.model_validate(await self._request("POST", "/persona-pieces", json=body))

    @staticmethod
    def _pick(voice: Voice, picks: dict[str, list[uuid.UUID]], name: str | None) -> dict[str, Any]:
        body: dict[str, Any] = {
            "voice": voice,
            "pieces": {slot: [str(i) for i in ids] for slot, ids in picks.items() if ids},
        }
        if name:
            body["name"] = name
        return body

    async def preview_persona(
        self, voice: Voice, picks: dict[str, list[uuid.UUID]], name: str | None = None
    ) -> Preview:
        """The persona a pick would make; saves nothing."""
        return Preview.model_validate(
            await self._request(
                "POST", "/persona-pieces/preview", json=self._pick(voice, picks, name)
            )
        )

    async def build_persona(
        self, voice: Voice, picks: dict[str, list[uuid.UUID]], name: str | None = None
    ) -> Built:
        """Makes an ordinary persona in the library from a pick."""
        return Built.model_validate(
            await self._request(
                "POST", "/persona-pieces/build", json=self._pick(voice, picks, name)
            )
        )

    # -- dials ----------------------------------------------------------------------------------

    async def dial_pack(self) -> list[Dial]:
        return _dials.validate_python(await self._request("GET", "/dials"))

    async def story_dials(self, story_id: uuid.UUID) -> list[StoryDial]:
        return _story_dials.validate_python(
            await self._request("GET", f"/stories/{story_id}/dials")
        )

    async def set_dial(self, story_id: uuid.UUID, key: str, value: str) -> StoryDial:
        return StoryDial.model_validate(
            await self._request("PUT", f"/stories/{story_id}/dials/{key}", json={"value": value})
        )

    async def clear_dial(self, story_id: uuid.UUID, key: str) -> None:
        await self._request("DELETE", f"/stories/{story_id}/dials/{key}")

    # -- turns: streamed --------------------------------------------------------------------

    def send(self, story_id: uuid.UUID, text: str) -> AsyncIterator[Event]:
        return self._stream("POST", f"/stories/{story_id}/send", {"text": text})

    def carry_on(self, story_id: uuid.UUID) -> AsyncIterator[Event]:
        return self._stream("POST", f"/stories/{story_id}/continue", None)

    def reroll(
        self, story_id: uuid.UUID, reason: str | None = None, instructions: str | None = None
    ) -> AsyncIterator[Event]:
        body: dict[str, str] = {}
        if reason:
            body["reason"] = reason
        if instructions:
            body["instructions"] = instructions
        return self._stream("POST", f"/stories/{story_id}/reroll", body)


def _current(response: httpx2.Response) -> EntryFull | None:
    """The entry a library 409 carries, when it carries one."""
    try:
        body: object = response.json()
    except ValueError:
        return None
    if not isinstance(body, dict):
        return None
    detail = cast(dict[str, object], body).get("detail")
    if not isinstance(detail, dict):
        return None
    current = cast(dict[str, object], detail).get("current")
    if not isinstance(current, dict):
        return None
    try:
        # A piece's conflict carries no preview, which a list entry needs: it is the text's start.
        text = str(cast(dict[str, object], current).get("text", ""))
        return EntryFull.model_validate({"preview": text[:200], **current})
    except ValueError:
        return None


def _detail(response: httpx2.Response) -> str:
    """The API's sentence, from FastAPI's ``{"detail": …}``; the status text when there is none."""
    try:
        body: object = response.json()
    except ValueError:
        return response.text.strip() or f"HTTP {response.status_code}"
    if isinstance(body, dict):
        typed = cast(dict[str, object], body)
        detail = typed.get("detail")
        if isinstance(detail, str):
            return detail
        if isinstance(detail, dict):  # a refusal with more than a sentence: the sentence
            message = cast(dict[str, object], detail).get("message")
            if isinstance(message, str):
                return message
        if isinstance(detail, list):  # a validation error: one line per field
            items = cast(list[object], detail)
            parts = [
                str(cast(dict[str, object], item)["msg"])
                for item in items
                if isinstance(item, dict) and "msg" in cast(dict[str, object], item)
            ]
            if parts:
                return "; ".join(parts)
    return response.text.strip() or f"HTTP {response.status_code}"
