# Failure modes reference

The dense checklist behind step 4 of the review. Read the sections that match the design under review — walking all of them on every design produces padding, and padding is what makes reviews get skipped.

Each entry is written as a trigger and a mechanism, because that is the form a finding has to take in the output. An entry is worth raising only when you can complete the chain for *this* design: trigger → mechanism → blast radius → fixable or not.

## Contents

- [Data & state](#data--state)
- [Coordination & concurrency](#coordination--concurrency)
- [Failure & recovery](#failure--recovery)
- [Boundaries & coupling](#boundaries--coupling)
- [Scale & performance](#scale--performance)
- [Operability & change](#operability--change)
- [Security, tenancy & compliance](#security-tenancy--compliance)
- [Implementation level](#implementation-level)
- [Archetypes](#archetypes)
- [Reviewer failure modes](#reviewer-failure-modes)

---

## Data & state

**Dual writes.** Any handler that writes to the database and also publishes an event, updates a cache, writes to a search index, or calls another service's write API is two writes with no shared transaction. A crash, a timeout, or a deploy between them leaves the two stores disagreeing permanently. This is the single most common fatal flaw in modern designs and it never appears in the box-and-arrow diagram. Fixes: transactional outbox + CDC, or making the second write a derived read from the first.

**Source of truth ambiguity.** Two systems that both accept writes for the same fact will diverge; the design has to name which one loses. "We'll sync them" is a plan to discover the divergence in production.

**Schema that cannot express the domain.** One-to-many modeled as a column, history modeled as an overwrite, money as a float, a state machine as a boolean, an enum in application code that the database will happily violate. The cost lands as a backfill under time pressure, and backfills against a live table are where outages come from.

**Unbounded growth.** Tables with no retention or archival story, event logs kept forever, JSONB columns that accumulate, per-request rows at a rate nobody multiplied out. Compute the row count at 1 and 3 years and check what breaks first — index size, vacuum, backup window, or the query plan flipping to a sequential scan.

**Hot keys and skew.** A partition, shard, or tenant key with a Pareto distribution turns a "horizontally scalable" store into one overloaded node. Ask what the largest single key looks like, not the average.

**Deletes and erasure.** GDPR/DPA erasure, tenant offboarding, and "undo" are design constraints. Immutable event logs, denormalized copies, backups, and downstream caches each need an answer, and retrofitting one is architectural, not a task.

**Migration reversibility.** Any schema change that runs after code depends on it is a one-way door under incident pressure. Expand → migrate → contract, or an explicit statement of why not.

## Coordination & concurrency

**Read-modify-write races.** Fetch a row, compute, write it back — correct on one instance, silently lossy on three. Needs optimistic locking (version column), a database-level constraint, an atomic update expression, or a lock with an owner and a TTL. Test suites almost never catch this because they run single-threaded.

**Idempotency that isn't.** A key generated per attempt instead of per request makes retries indistinguishable from new requests. The key must be derived from the caller's request and the dedup window must exceed the maximum retry horizon, including manual replays.

**Exactly-once delivery.** It does not exist across a network boundary. Designs that assume it are designs with an unhandled duplicate. At-least-once plus idempotent effects, or at-most-once plus reconciliation — pick one explicitly.

**Ordering assumptions.** Queues guarantee ordering per partition at best, and only if a single consumer processes it. Wall-clock timestamps from different machines do not order events. If the design needs causal order, it needs sequence numbers or a partition key, stated.

**Distributed transactions.** Two-phase commit across services is usually a rejected option pretending to be a design. Sagas are the alternative and they are not free: every step needs a compensating action, and compensations that can themselves fail need their own recovery path. A saga drawn without compensations is not a saga.

**Lock scope and lifetime.** Locks held across a network call, locks without TTL, and locks whose holder can die mid-work. Ask what happens to the lock when the process is SIGKILLed.

**Cron/scheduler overlap.** A job that runs every 5 minutes and sometimes takes 7 minutes will eventually run concurrently with itself. Single-flight guard, or an idempotent job.

## Failure & recovery

**The dependency matrix.** For each dependency, three states: down, slow, wrong. Down is usually handled. Slow is what causes the outage — a dependency at p99 = 30 s with no timeout consumes the caller's thread/connection pool and the failure propagates upward as a full outage.

**Timeout budget inversion.** Caller timeout must exceed the sum of downstream timeouts plus retries, or the caller gives up while work is still in flight — producing duplicate work, orphaned state, and retry amplification. Write out the budget: edge 2 s → service 1.5 s → DB 500 ms, and check the arithmetic.

**Retry storms.** Retries without exponential backoff and jitter, retries at multiple layers multiplying (3 × 3 × 3 = 27 requests per user action), and retries on non-idempotent operations. A dependency recovering from an outage gets hit by the entire backlog at once unless something sheds load.

**Missing backpressure.** Unbounded in-memory queues, unbounded consumer prefetch, unlimited concurrency on a fan-out. The system's failure mode becomes OOM instead of a clean rejection. Bounded queues plus explicit shedding fail better than infinite buffering.

**Partial failure state.** Multi-step flows that leave state half-written with no path forward or back. Ask: after a crash at each step, what does the state look like and what process fixes it?

**Poison messages.** A message that always fails, retried forever, blocking a partition. Needs a DLQ with a retry count, and someone whose job is to look at the DLQ.

**Cold start and thundering herd.** Cache flush, deploy, or restart sends full traffic to the origin at once. Ask what the origin does at 100% miss rate — usually the answer is "falls over".

**Blast radius.** How many users, tenants, or transactions are affected by one instance failing, one bad deploy, one bad row? Shared fate across tenants is a design property, not an accident.

## Boundaries & coupling

**Distributed monolith.** Services that must be deployed together, share a database, or call each other synchronously in a chain. All the operational cost of distribution, none of the independence. Symptoms: a shared "common" library with domain types in it, a release train, a schema change that requires coordinating three teams.

**Availability multiplication.** Three synchronous hops at 99.9% each yields 99.7% — roughly a day of downtime a year — before adding network flakiness. Every sync hop also adds its p99 to the caller's tail, and tails compound faster than averages.

**Seams that follow the org chart.** Boundaries drawn around teams rather than around data ownership produce chatty interfaces and transactions that span services. The test: can one service's data be changed without another service's release?

**Chatty interfaces.** An API that requires N calls to render one screen turns network latency into user-visible latency and makes the client's failure handling combinatorial.

**Shared mutable infrastructure.** One database, one Redis, one Kafka cluster with no quotas: any one consumer can starve the rest. Noisy-neighbor isolation is either designed or discovered.

**Versioning and contract breaks.** Additive-only changes, consumer-driven contracts, or a versioning scheme — otherwise every producer deploy is a potential consumer outage. Also applies to event schemas, which are APIs that nobody documents.

## Scale & performance

**Do the arithmetic before the argument.** rps × payload = bandwidth. rows × row size = storage. requests × fan-out = downstream load. Most scale disputes end the moment someone multiplies.

**Fan-out per request.** One query per item in a list, one HTTP call per row, one cache lookup per field. Linear in something a user or customer controls means the ceiling is set by your worst customer.

**N+1 across a network boundary.** Tolerable in-process, fatal across a service call — 40 items × 15 ms serial is 600 ms of pure latency.

**Unbounded queries.** No pagination, no LIMIT, `SELECT *` on a wide table, an "export" endpoint that materializes everything in memory. Ask what the largest existing row set is, then what it will be in a year.

**Index reality.** An index on the column and an index on the *query shape* are different things: composite order, selectivity, sorts, and the plan the optimizer actually picks. A query pattern with no matching index is a table scan waiting for the table to get big.

**Serialization and payload size.** JSON over the wire for large objects, repeated serialize/deserialize across hops, base64 blobs in message payloads. Often a bigger cost than the business logic.

**The first wall, and when it arrives.** Name the specific limit — connection pool size, single-writer throughput, partition count, memory per instance, a provider quota — and the traffic number at which it is hit. Then compare it to the growth timeline. A wall four years out is not a finding; a wall at 3× current traffic is.

**Cost as a scaling dimension.** Per-request cost × volume, especially for managed services, egress, and model inference. A design can scale technically and be unaffordable — that is a fatal flaw with a spreadsheet instead of a stack trace.

## Operability & change

**Debuggability at 03:00.** Given only what this design emits, can someone reconstruct a single failed request across every hop? Correlation ID propagation, structured logs with the identifiers that matter, and a trace that spans async boundaries — queues break traces unless the context is carried in the message.

**The alert and the runbook.** Which specific alert fires when this breaks, and what does the responder do? "We'll monitor it" is not an answer. Symptom-based alerts (error rate, latency, queue depth, staleness) beat cause-based ones.

**Deploy and rollback.** Can this be rolled back after it has written data in the new format? Feature flags, dual-read/dual-write phases, and backward-compatible message schemas are what make rollback real.

**Migration and backfill.** Online vs. maintenance window, batched vs. one shot, resumable after a crash, and its load impact on the live system. A backfill that takes 30 hours and cannot be resumed is a fatal flaw in the plan even when the target design is fine.

**Local development and testing.** Can a developer run this? Can the failure paths be tested at all, or does the design force integration-only testing against shared environments — which means, in practice, they will not be tested.

**Bus factor and team fit.** New runtime, new datastore, new paradigm: count the concepts the team must learn and who is on call. A design only its author understands has an availability problem regardless of its technical merit. This is a legitimate KILL reason and reviewers routinely under-weight it.

**Complexity budget.** Count the moving parts a request touches and the number of failure modes each adds. Every one has to be earned by a constraint that actually exists today or is scheduled.

## Security, tenancy & compliance

**Authorization at every hop, not just the edge.** Internal services that trust their callers are one SSRF or misrouted request away from full access. Ask where the authorization decision is made, and what it is made from.

**Tenant isolation mechanism.** Enforced by the storage layer (separate schema/DB, RLS) or by every developer remembering a WHERE clause. The second one fails eventually, and it fails as a cross-tenant data leak.

**PII flow and rest.** Where personal data enters, which stores it lands in, which logs it appears in, what leaves the trust boundary. Logs and analytics pipelines are the usual leak.

**Secrets.** In environment variables, in a manager, rotatable without a deploy, absent from images and repos.

**Audit trail.** Who did what, when, immutably, in a form an auditor can read. Retrofitting one after the fact is architectural.

**Regulated and air-gapped environments.** The design's silent assumptions about network egress, external SaaS, cloud-hosted models, and third-party dependency downloads. A design that requires an outbound call from a segment that has none is not a design, no matter how good the diagram is. Data residency, retention mandates, and approval processes belong in the timeline, not in the footnotes.

## Implementation level

When actual code is in scope. Correctness before style, always.

**Find the input that breaks it** — empty collection, single element, duplicate keys, null in the middle, unicode and RTL text, very large values, negative numbers, timezone boundaries, DST, leap day, a response that arrives after the timeout, a concurrent caller.

**Resource lifecycle** — connections, file handles, subscriptions, timers, and event listeners created without a matching release on every path including the error path. Cancellation and abort propagation. A leak per request is a restart per day.

**Error handling** — swallowed exceptions, catch-and-log-and-continue that leaves inconsistent state, errors flattened into a generic 500 so the caller cannot distinguish retryable from fatal, and error paths that themselves throw.

**Boundaries of trust** — validation at the edge of the process, not deep inside; parse into a typed shape once, rather than repeatedly re-checking a loose one.

**Hot paths** — quadratic loops, allocations inside tight loops, regex compiled per call, JSON parsed repeatedly, synchronous I/O on an event loop, and blocking calls inside a lock.

**Concurrency in code** — shared mutable state without synchronization, async operations whose completion order is assumed, fire-and-forget promises with no error handler, and thread/connection pool exhaustion under a slow dependency.

**Contract stability** — response shape changes, field type changes, enum additions, and error code changes that will land on a consumer who is not in this PR.

**The 10× question** — what is fine at today's volume and lethal at ten times it, with the number attached.

## Archetypes

**Event-driven / messaging.** Outbox or dual write; consumer idempotency; ordering guarantees actually required vs. actually provided; DLQ with a human owner; schema evolution for events; replay semantics (can you rebuild state from the log, and does anything break if you do); consumer lag as the primary alert; and the question of whether the events describe facts (`OrderPlaced`) or commands in disguise (`SendEmail`), because the latter recreates synchronous coupling with extra steps.

**Microservice extraction / strangler migration.** The seam and who owns the data after the split; the interim period where both systems are live and how they stay consistent; whether the migration can pause safely halfway; the rollback path per phase; and the honest answer to whether the split solves a scaling problem, an ownership problem, or neither.

**Caching.** Invalidation trigger and staleness budget stated as a number; stampede protection; what a cold cache does to the origin; whether the cache is an optimization or a load-bearing dependency (if the system cannot serve at 0% hit rate, the cache is a database with no durability); and per-tenant/per-user key correctness — cache key bugs leak other people's data.

**Multi-tenant.** Isolation mechanism, noisy-neighbor limits, per-tenant data volume skew, onboarding and offboarding as flows, and whether a per-tenant migration can run without a global maintenance window.

**Batch / ETL / pipelines.** Idempotent reruns, late-arriving data, partial-batch failure and resume, schema drift at the source, backfill cost, and the SLA on freshness stated as a number rather than "daily".

**LLM / RAG / agentic systems.** Non-determinism as a correctness constraint, not a quirk: what happens on a wrong answer, and who catches it. Cost and latency per request at production volume. Context window limits against real document sizes. Retrieval quality measured on an actual eval set rather than assumed. Prompt injection through retrieved or user content, and what the model is allowed to do with tools if injected. Evaluation and regression detection when the model or prompt changes. Failure mode when the provider is down, rate-limits, or deprecates the model. In regulated environments, whether inference is allowed to leave the perimeter at all, and what a local model actually costs in hardware and quality.

## Reviewer failure modes

Watch for these in your own output — they are how technically correct reviews become useless.

**Cargo-culting.** Recommending CQRS, hexagonal architecture, microservices, event sourcing, or Kubernetes without a constraint in this design that requires them. The pattern is not the justification; the constraint is.

**Premature-scale criticism.** Killing a design for a ceiling that arrives long after the decision horizon. Symmetric to premature optimization and equally wasteful.

**Best-practice recitation.** "Add monitoring", "improve error handling", "consider security" — content-free unless attached to a specific gap and a specific consequence.

**Manufactured flaws.** Padding the review to look rigorous. It costs the user attention and costs you credibility on the finding that actually mattered.

**Taste presented as risk.** Dressing "I would have done it differently" in the language of failure modes. If you cannot write the causal chain, it belongs in the taste tier or nowhere.

**Missing the strength.** A review that cannot state plainly what is right about the design is not calibrated, and the user will discount the criticism accordingly.
