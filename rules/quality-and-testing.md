# Quality & testing

## Tests
- **Zero logic in tests.** No `if`, no `switch`, no loops. Arrange, act, assert — declarative and direct.
- **Independent.** No shared mutable state; execution order never changes the result.
- **Testing floor.** Non-trivial logic leaves one runnable check behind. Trivial one-liners need none.

## Verification and evidence
- A green compile, type-check or CI run shows the code builds, not that it does the job. Exercise the changed behavior (run it, call it, load the page) and quote the command with its real output. A check not run is reported as not run.
- Cheapest level that proves it: unit before integration before end-to-end; keep end-to-end for the few journeys that matter.
- Test the contract, not the implementation. Where two modules or services meet, one check pins the shape the boundary parses.
- Cover the failure path of anything that crosses a trust boundary: invalid, missing or unauthorized input, a dependency that is down.
- A fix leaves a check that fails before the change and passes after it. A flaky test is a bug: find the cause, never retry it into green.
- A test that stubs the host (a stub client or SDK object) proves layout and wiring, not the host's behaviour; say so.
