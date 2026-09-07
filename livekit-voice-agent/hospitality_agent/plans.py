"""Versioned interview plans shipped with the prototype."""

from .models import InterviewPlan, ResearchObjective


POST_SHIFT_GUEST_EXPERIENCE = InterviewPlan(
    id="post_shift_guest_experience",
    version="1.0",
    title="Post-shift guest-experience debrief",
    business_goal=(
        "Understand what most affected the guest experience during a shift, why it "
        "happened, and which practical improvement deserves attention."
    ),
    respondent_type="Hotel frontline employee or shift supervisor",
    target_duration_seconds=360,
    max_respondent_turns=12,
    opening_message=(
        "Hi, I'm ShiftSignal, an AI interviewer. I'd like to hear about your shift "
        "so your team can understand what is helping or hurting the guest experience. "
        "This is not a performance evaluation. Please don't share guest names, room "
        "numbers, or coworkers' names. You can skip any question or stop at any time. "
        "To begin, what happened during your shift that most affected a guest's experience?"
    ),
    closing_message=(
        "Thank you for sharing that. Your experience will be reviewed as feedback, "
        "but I can't promise a particular action or outcome."
    ),
    objectives=(
        ResearchObjective(
            id="primary_event",
            goal="Identify the event that most affected a guest's experience.",
            evidence_needed="A concrete event, or a clear statement that no notable event occurred.",
            suggested_probes=("What happened?", "Could you walk me through a specific example?"),
        ),
        ResearchObjective(
            id="guest_journey",
            goal="Locate where the event occurred in the guest journey.",
            evidence_needed="The service moment or operational handoff involved.",
            suggested_probes=("At what point in the guest's experience did this occur?",),
        ),
        ResearchObjective(
            id="operational_context",
            goal="Understand the operational conditions behind the event.",
            evidence_needed="Observed conditions, process breakdowns, or handoffs without assigning blame.",
            suggested_probes=("What seemed to lead to that?", "Which part of the process broke down?"),
        ),
        ResearchObjective(
            id="recurrence",
            goal="Learn whether the event appears isolated or recurring.",
            evidence_needed="The respondent's own description of frequency; never invent a number.",
            suggested_probes=("Was this unusual, or have you seen it before?",),
        ),
        ResearchObjective(
            id="impact",
            goal="Capture the consequence for guests and staff.",
            evidence_needed="A concrete observed or reported effect, clearly distinguished from inference.",
            suggested_probes=("How did that affect the guest or your team?",),
        ),
        ResearchObjective(
            id="workaround",
            goal="Capture how staff currently handle the problem.",
            evidence_needed="A workaround, escalation, or a clear statement that none exists.",
            suggested_probes=("What did the team do in the moment?",),
        ),
        ResearchObjective(
            id="improvement",
            goal="Ask for one realistically scoped improvement.",
            evidence_needed="A respondent-proposed change, or a clear statement that they do not know.",
            suggested_probes=("What is one change that could make this work better?",),
        ),
        ResearchObjective(
            id="positive_practice",
            goal="Capture something the team handled well.",
            evidence_needed="A useful positive practice, or a clear statement that none comes to mind.",
            suggested_probes=("What did your team handle especially well?",),
        ),
    ),
)
