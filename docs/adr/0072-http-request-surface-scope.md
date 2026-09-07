# ADR 0072 — HTTP Request Surface Scope for `0.1.0a4`

- Status: Proposed
- Date: 2026-09-07
- Initiative: I7 HTTP request surface
- Tracking: GitHub Issue #298
- Amends: ADR 0026
- Related: ADR 0032, ADR 0035, ADR 0068, ADR 0070, ADR 0071

## Context

ADR 0026 gave the adapter path, query, header and one JSON body binding, and
recorded that "forms, multipart, files, streaming application inputs, cookies,
and content negotiation require separate reviewed work". `docs/INITIATIVES.md`
I7 names the `0.1.0a4` half: cookies, forms, multipart and file uploads, "the
gaps that stop `agnara-http` being usable for ordinary applications", then
separately CORS, compression, static files, proxy headers, trusted hosts and a
cross-cutting extension point.

ADR 0071 made the adapter consumable. An application can declare routes and
serve them through public API, and cannot read a session cookie, accept an
HTML form post or receive a file. That gap is what this decision closes, and
it is also where a web framework starts growing features without end. So the
first half of this record is a classification, and the second is the smallest
implementation that satisfies it.

## Decision — the classification

Every I7 subfeature the planning documents mention, classified. Nothing here
is left implicit.

### Required for `0.1.0a4`, and implemented

| Feature | Shape |
| --- | --- |
| **Cookies** | `BindingSource.COOKIE`, one RFC 6265 pair read by name, scalar schema. |
| **Forms** | `BindingSource.FORM`, one field from an URL-encoded *or* multipart body. |
| **File uploads** | `BindingSource.UPLOAD`, one file part as `bytes`. |
| **Multipart parsing** | The `multipart/form-data` reader both of the above use. |
| **Content type handling** | Per-route media-type selection, settled before the body is read. |

### Already supported

| Feature | Where |
| --- | --- |
| Path, query, header and JSON body binding | ADR 0026, unchanged. |
| Per-route body size limit | `max_body_bytes`, public since ADR 0071. |
| Structured failure mapping | RFC 9457, ADR 0028 and ADR 0030. |
| OpenAPI parameter and request-body projection | ADR 0032, extended here. |

### Deferred, with the reason

| Feature | Reason |
| --- | --- |
| **Multiple files, and repeated form fields** | Both need a collection binding. ADR 0026 rejected repeated scalar values deliberately and said "collection bindings require a later explicit design". That design is not HTTP-local: it decides how a list arrives through *every* transport. |
| **Client filename and per-part content type** | Both need a public upload value type carrying filename, content type and content. A value type is a core-visible schema shape — MCP and introspection project it too — so its design is not the HTTP adapter's to make alone. And the filename is attacker-controlled: every safe use generates a name anyway, so a4 exposes none. |
| **Streaming and large uploads** | An upload is bounded `bytes`. Streaming request bodies need the streaming model, which is I2 and belongs to `0.1.0a5` (ADR 0068). |
| **CORS, compression, static files, proxy headers, trusted hosts** | These are ASGI-layer or reverse-proxy concerns and none of them needs a capability. See "Where these belong instead" below. |
| **Generic middleware / interceptor hook** | `docs/INITIATIVES.md` states the reason and this decision keeps it: "middleware in most frameworks is where transport types leak into application code, and Agnara must not reproduce that". Adding a hook now, before the extension model (I13) and the embedding contract (RFC 0008), would fix the wrong shape permanently. |
| **Sessions, authentication** | Not request binding. Authentication is the security program, I10. |

### Requires a future RFC

| Feature | Question it must answer |
| --- | --- |
| Collection bindings | How a repeated wire value becomes a list input, across every transport. |
| Upload value type | What a file is as a schema, such that MCP and introspection can project it. |
| Content negotiation, conditional and range requests | Whether a capability result has representations at all, which is a response-model question, not a request one. |

### Where these belong instead

An application that needs a deferred cross-cutting feature in `0.1.0a4` puts
it where it already lives, outside Agnara:

- **CORS, compression, trusted hosts, proxy header trust** — the reverse proxy
  or ASGI server in front of the application, or a third-party ASGI middleware
  wrapping the `HttpApplication`. It is an ASGI 3 callable, so any ASGI
  middleware composes with it.
- **Static files** — a web server or CDN. Agnara serves capabilities.
- **Sessions** — a cookie binding plus the application's own store, which is
  exactly what `BindingSource.COOKIE` makes possible.

This is not a promise that Agnara will never own them. It is a statement that
`0.1.0a4` owns none of them, and that wrapping an ASGI application is already
the supported answer.

## Decision — the implementation

### Three new binding sources, no new public types

`BindingSource` gains `COOKIE`, `FORM` and `UPLOAD`. That is the entire public
API change: no new class, no new function, no new error. Each is a new source
for the binding machinery ADR 0026 already established, which is what
`docs/INITIATIVES.md` predicted ("each is a new binding source rather than new
architecture").

### One request has one body

`BODY`, `FORM` and `UPLOAD` all consume the body, so a route combining `BODY`
with either of the others is refused at compile time. `FORM` and `UPLOAD`
combine freely, because that is what an upload form posts: some text fields
and a file.

A `FORM` binding accepts both `application/x-www-form-urlencoded` and
`multipart/form-data`, because an application asked for a *field*, not for an
encoding, and an HTML form picks the encoding from its `enctype`. A route that
also declares an `UPLOAD` accepts multipart only: a URL-encoded body cannot
carry a file part, so advertising it would be untrue.

### An upload is `bytes`, and the filename is not exposed

`UPLOAD` requires the input to be annotated `bytes`; the compiler refuses
anything else. Accepting `str` would decode arbitrary uploaded bytes as text
and fail on the first PNG.

Nothing touches the filesystem. There is no temporary file, so there is
nothing to leak and nothing to clean up on cancellation or error — an upload
is bytes owned by the invocation payload and released with it. The ceiling is
`max_body_bytes`, and that is stated in `docs/HTTP_COMPOSITION.md` rather than
implied.

### The media type is settled before the body is read

ADR 0026 forbids reading a body without a binding. The same reasoning extends
to a body this route cannot decode: buffering megabytes only to answer 415 is
work an unauthenticated client should not be able to ask for. Content type and
multipart boundary are validated from the headers first, then the body is
read under `max_body_bytes`, then it is decoded.

An implementation of this task initially read the body first and was caught by
the existing tests, which is why the ordering is written down here.

### Part count is bounded separately from size

`max_parts` defaults to 64 and is overridable per route. A body well inside
`max_body_bytes` can still carry tens of thousands of empty parts, and each
costs a dictionary entry and a header parse, so the count needs its own bound.

### A malformed cookie pair is skipped, not fatal

A browser sends cookies this application never set. One pair whose name is not
an HTTP token must not become a 400 for every request on the route, so
unparseable pairs are skipped and named cookies are still read. Cookie names
are case-sensitive, unlike headers, so they are validated but never folded.
Cookie values are opaque: percent, base64 and quoted forms are left exactly as
sent, because guessing an encoding would corrupt a value the capability is
about to validate.

### OpenAPI describes what the adapter accepts

A cookie binding projects `in: cookie`. Form fields and uploads project one
`requestBody` object — they are properties of a body, not parameters — with
`additionalProperties: false`, the required fields listed, an upload as
`{"type": "string", "format": "binary"}`, and `encoding` carrying the part's
content type as RFC 7578 requires. The advertised media types are exactly the
ones the route accepts: multipart only when an upload is declared, both
otherwise.

## Threat analysis

**Oversized body.** Unchanged and now applied earlier: `max_body_bytes` is
checked while chunks arrive, before concatenation, and now before any decode.
A wrong-content-type request is refused from the headers, so it never buffers.

**Oversized multipart.** The whole body is inside `max_body_bytes` before the
parser sees it, so no part can exceed the route's limit. `max_parts` bounds the
count independently, and exceeding it answers 413 rather than parsing on.

**Malicious filenames.** Not reachable. The filename is never returned, never
compared, never used to name anything. Path traversal, null bytes, control
characters and Unicode confusables in a filename cannot affect this adapter,
because the value is discarded after being recognized as a filename marker.

**Header and cookie parsing.** Header names remain ASCII tokens with the
existing validation. Cookie names are validated against the RFC 6265 token
grammar; a non-token pair is skipped. Neither parser allocates per pair beyond
the header bytes already received.

**Malformed encoding.** A multipart body that does not start with its
boundary, a part with no header block, a part that is not `form-data`, a part
with no name, a boundary outside the RFC 7578 grammar, a boundary with a
trailing space, and a non-UTF-8 form field each produce a structured
`invalid_input` problem. Nothing is guessed and nothing is repaired.

**Sensitive values in errors and logging.** A binding failure reports the
*location* — `form.password`, `cookie.session` — and never the value. Cookie
and form values therefore cannot reach a problem document, a log line or an
OpenAPI document. The upload path reports no content either. This is the
existing `_RequestBindingError` contract and the new sources use it unchanged.

**Resource exhaustion.** Three bounds: total body size, part count, and the
absence of any per-part allocation before the size check. Cookies are parsed
once per request and only when a cookie binding exists, so a route that reads
no cookie pays nothing for a large `Cookie` header beyond receiving it.

**Cleanup on cancellation or error.** Nothing to clean up, by construction: no
temporary file, no file handle, no background task. `CancelledError` continues
to propagate untranslated, as ADR 0026 requires.

**Residual risk, stated.** An upload is buffered in memory. A route that
declares `max_body_bytes=100_000_000` will hold 100 MB per concurrent request.
That is the application's decision and the guide says so; the default remains
1 MiB.

## Consequences

### Positive

- A login form, a session cookie and a file upload are expressible, which is
  most of what "ordinary HTTP application" means.
- No new public type, so the surface stays at seven names plus three enum
  members.
- The deferred list is now a record rather than an omission, and each entry
  names what would have to be decided first.

### Negative

- One upload per part name only. An application needing several files must
  declare several parts with different names, which is legal but clumsy, and
  the natural spelling waits on collection bindings.
- No filename means an application that wants to preserve a file extension
  must ask for it as a separate form field. That is a real cost and it is the
  price of not exposing an attacker-controlled string.
- The adapter now contains a multipart parser. It is bounded and small, but it
  is a parser, and parsers are where protocol bugs live.
- `_BindingSource` has seven members and three of them mean "read the body",
  which is a shape a future refactor may want to make explicit.

## Alternatives considered

**Defer multipart and uploads entirely, shipping cookies and forms only.**
Rejected: `docs/INITIATIVES.md` names uploads as part of what stops the adapter
being usable, and a bounded in-memory upload answers the common case honestly.
Deferring would have left the largest gap open while claiming I7 complete.

**Ship an `UploadedFile` value type with filename and content type.**
Rejected for a4. It is a core-visible schema shape that MCP and introspection
also project, and `DataclassSchema.json_schema()` would describe a file as an
object with a bytes field — misleading everywhere except HTTP, where the
projection would have to special-case it. Issue #296 shows what happens when a
projected schema and the accepted value disagree.

**Use `email.parser` for multipart.** Rejected: it parses MIME messages, not
HTTP multipart, and its lenience is the wrong default here. A bounded parser
that refuses everything unexpected is smaller than the code needed to make a
lenient one strict.

**Infer the body encoding from the request instead of the declaration.**
Rejected: a route that accepts JSON *or* a form is two contracts, and OpenAPI
would have to advertise both for every operation. Declaring the reading keeps
the document truthful.

**Add a middleware hook now, so CORS and compression become the
application's problem inside Agnara.** Rejected, for the reason
`docs/INITIATIVES.md` already gives: middleware is where transport types leak
into application code. An `HttpApplication` is an ASGI 3 callable, so any ASGI
middleware already wraps it, from outside, where transport concerns belong.

## Revisit when

The collection binding RFC lands — repeated form fields and multiple files
become expressible together, and this record's largest deferral closes. Also
at `0.1.0a5`, when I2 decides streaming: a streamed request body would replace
the bounded-`bytes` upload contract rather than extend it, and that is a
breaking change this alpha is allowed to make.
