ID: SOP-REC-012
TITLE: Recloser Operation and Lockout
SECTION: 8.2 Automatic Reclosing
URL: https://internal.example/sops/recloser_operation_and_lockout

SYNTHETIC REFERENCE — generated for the MAFD knowledge base from standard
protection practice (IEEE C37 series conventions). Not an approved JPS
procedure; review and adopt through the utility's own document control before
any operational use.

This SOP describes how to interpret and respond to automatic recloser operation
on a distribution feeder, and what lockout obliges the operator to do.

Automatic reclosing exists because most overhead faults are transient: the arc
extinguishes when current is interrupted and the line can be safely re-energized.
The reclose sequence is a controlled test of whether that has happened.

Conditions:
- A recloser or reclosing breaker has operated one or more times.
- The device either held (fault cleared) or reached lockout (fault persisted
  through the full sequence).

Trip Criteria:
- Fast (instantaneous) trip on the first operation, where fuse-saving is in use,
  to clear a transient fault before a downstream fuse operates.
- Delayed (time-overcurrent) trips on subsequent operations, allowing a fuse to
  clear a genuinely downstream permanent fault.
- Lockout after the programmed number of operations. Lockout means the fault is
  permanent until proven otherwise.

Operator Actions:
1. Read the operation count and sequence from the device, not just the final
   state. One operation followed by a successful hold is a transient fault; three
   operations to lockout is a permanent fault; repeated single operations over
   hours indicate a developing defect.
2. On a successful hold, no restoration action is needed — but record it. A
   pattern of transient operations at the same location is predictive of a future
   permanent failure and is the most useful early warning available.
3. On LOCKOUT, do not manually reclose before the section has been patrolled.
   Manual reclosing into a permanent fault re-applies full fault current, exposes
   the public to a possibly downed conductor, and adds interrupting duty to the
   device.
4. Where operating practice permits exactly one manual test-close, confirm first
   that the fault type is not one of the downed-conductor classes (SOP-SLG-005,
   SOP-OPEN-009, SOP-HIZ-010) and that no member of the public has reported a
   downed line. If in doubt, patrol first.
5. Verify that reclosing is disabled before any crew works on the line, and
   confirm the disable at the device rather than only in SCADA.
6. Re-enable reclosing after work is complete and record it. A feeder left with
   reclosing disabled will not ride through the next transient fault, turning a
   momentary interruption into a sustained outage.
7. Escalate repeated lockouts on the same feeder to protection engineering for
   coordination and settings review (SOP-MISC-002).

Notes:
- Fuse-saving versus fuse-blowing is a coordination policy decision, not an
  operator choice. Do not change the fast-trip enable without engineering
  approval.
- Each reclose attempt into a fault adds cumulative interrupting duty. Devices
  have a finite number of fault interruptions between maintenance intervals.
