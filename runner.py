"""Injectable run-to-completion loop for `council run`. No real sleeping here."""
from __future__ import annotations


def drive(slug, *, status_fn, resume_fn, collect_fn, sleep_fn, stop_fn=None,
          interval=20, max_ticks=90, auto_resume=True) -> dict:
    """Poll a meeting until FINAL, auto-resuming blocked cards, then collect.

    - status_fn(slug) -> dict with "final_reached", "blocked", "runaway".
    - resume_fn(slug) -> dict (called when blocked cards appear and auto_resume).
    - stop_fn(slug) -> dict (called once if the meeting goes runaway — force-synthesize).
    - collect_fn(slug) -> dict (called once FINAL is reached).
    - sleep_fn(seconds) between polls.
    Returns {"outcome": "final"|"timeout", "slug": slug, ...collect result}.
    """
    resumes = 0
    stopped = False
    for _ in range(max_ticks):
        st = status_fn(slug)
        if st.get("final_reached"):
            return {"outcome": "final", "slug": slug, **collect_fn(slug)}
        if st.get("pending_decision"):
            # Human gate — do NOT auto-resume; hand back to the operator.
            return {"outcome": "awaiting_decision", "slug": slug,
                    "pending": st["pending_decision"]}
        if st.get("runaway") and stop_fn and not stopped:
            stop_fn(slug)          # force the moderator to synthesize now
            stopped = True
        elif auto_resume and st.get("blocked"):
            resume_fn(slug)
            resumes += 1
        sleep_fn(interval)
    return {"outcome": "timeout", "slug": slug, "resumes": resumes, "stopped": stopped}
