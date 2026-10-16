"""Versioned hospitality interview plans shipped with the prototype."""

from __future__ import annotations

import json

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
    core_objective_ids=("primary_event", "impact", "improvement"),
)


NEW_PROCESS_ROLLOUT = InterviewPlan(
    id="new_process_rollout",
    version="1.0",
    title="New process or training rollout check-in",
    business_goal=(
        "Understand how a new hospitality process or training is working in practice, "
        "where staff need support, and which small adjustment should be reviewed."
    ),
    respondent_type="Hotel employee affected by a recent process or training change",
    target_duration_seconds=360,
    max_respondent_turns=12,
    opening_message=(
        "Hi, I'm ShiftSignal, an AI interviewer. I'd like to understand how the new "
        "process or training is working during real shifts. This is not a performance "
        "evaluation. Please don't share guest names, room numbers, or coworkers' names. "
        "You can skip any question or stop at any time. To begin, what changed in your "
        "work, and how has it gone so far?"
    ),
    closing_message=(
        "Thank you for sharing that. Your experience will be reviewed as feedback, "
        "but I can't promise a particular action or outcome."
    ),
    objectives=(
        ResearchObjective(
            id="rollout_experience",
            goal="Establish which change the respondent experienced and how it works in practice.",
            evidence_needed="A concrete process or training change and a real shift example.",
            suggested_probes=("Could you walk me through using it during a shift?",),
        ),
        ResearchObjective(
            id="expectation_clarity",
            goal="Understand whether the new expectations were clear.",
            evidence_needed="What the respondent understood, including any uncertain step.",
            suggested_probes=("Which part felt clear or unclear?",),
        ),
        ResearchObjective(
            id="preparedness",
            goal="Learn whether training, tools, and access prepared staff for the change.",
            evidence_needed="Observed readiness or a specific missing resource.",
            suggested_probes=("What helped you feel prepared?",),
        ),
        ResearchObjective(
            id="workflow_effect",
            goal="Capture how the change affects the guest-facing workflow.",
            evidence_needed="A concrete effect on timing, handoffs, consistency, guests, or staff.",
            suggested_probes=("How did it affect the shift or guest experience?",),
        ),
        ResearchObjective(
            id="friction",
            goal="Identify where the new process is difficult to apply.",
            evidence_needed=(
                "A specific point of friction, or a clear report that none was encountered."
            ),
            suggested_probes=("Where does the process become difficult to follow?",),
        ),
        ResearchObjective(
            id="support_or_workaround",
            goal="Capture support used or workarounds created by staff.",
            evidence_needed=(
                "A support path, workaround, or clear statement that neither was needed."
            ),
            suggested_probes=("What do you do when that happens?",),
        ),
        ResearchObjective(
            id="improvement",
            goal="Ask for one realistically scoped rollout adjustment.",
            evidence_needed="A respondent-proposed adjustment, or a clear statement of uncertainty.",
            suggested_probes=("What one adjustment would make this easier to use?",),
        ),
        ResearchObjective(
            id="positive_practice",
            goal="Capture one part of the rollout worth retaining.",
            evidence_needed="A useful element to preserve, or a clear statement that none comes to mind.",
            suggested_probes=("What part should stay as it is?",),
        ),
    ),
    core_objective_ids=("rollout_experience", "workflow_effect", "improvement"),
)


RECURRING_SERVICE_BREAKDOWN = InterviewPlan(
    id="recurring_service_breakdown",
    version="1.0",
    title="Recurring service-breakdown investigation",
    business_goal=(
        "Understand a recurring hospitality service breakdown, its observed conditions "
        "and impact, and a proportionate next step for review or testing."
    ),
    respondent_type="Hotel employee familiar with a recurring service problem",
    target_duration_seconds=420,
    max_respondent_turns=14,
    opening_message=(
        "Hi, I'm ShiftSignal, an AI interviewer. I'd like to understand a recurring "
        "service problem from your firsthand experience. This is not a performance "
        "evaluation or an investigation of individuals. Please don't share guest names, "
        "room numbers, or coworkers' names. You can skip any question or stop at any "
        "time. To begin, what service problem have you seen happen more than once?"
    ),
    closing_message=(
        "Thank you for sharing that. Your experience will be reviewed as feedback, "
        "but I can't promise a particular action or outcome."
    ),
    objectives=(
        ResearchObjective(
            id="breakdown_event",
            goal="Define the recurring service breakdown using a firsthand example.",
            evidence_needed="A concrete observed event rather than a general accusation.",
            suggested_probes=("What happened in the most recent example?",),
        ),
        ResearchObjective(
            id="journey_stage",
            goal="Locate the breakdown in the guest journey or operational handoff.",
            evidence_needed="The service moment, system step, or handoff involved.",
            suggested_probes=("Where in the service process does it occur?",),
        ),
        ResearchObjective(
            id="observed_conditions",
            goal="Capture conditions present when the breakdown occurs without assigning blame.",
            evidence_needed="Firsthand conditions separated from inferred causes.",
            suggested_probes=("What conditions have you noticed when it happens?",),
        ),
        ResearchObjective(
            id="recurrence",
            goal="Preserve how often and under what circumstances it recurs.",
            evidence_needed=(
                "The respondent's wording about frequency or pattern; never an invented number."
            ),
            suggested_probes=("When have you seen it happen again?",),
        ),
        ResearchObjective(
            id="impact",
            goal="Capture the observed effect on guests, staff, or service delivery.",
            evidence_needed="A specific consequence grounded in the respondent's experience.",
            suggested_probes=("What happens to guests or the team when it occurs?",),
        ),
        ResearchObjective(
            id="workaround",
            goal="Understand how staff currently contain or recover from the breakdown.",
            evidence_needed="A workaround, escalation, or clear statement that none exists.",
            suggested_probes=("How do you manage it in the moment?",),
        ),
        ResearchObjective(
            id="prior_response",
            goal="Learn what has already been tried without asking who was responsible.",
            evidence_needed="A process change or prior response and its observed result.",
            suggested_probes=("What has already been tried, and what happened?",),
        ),
        ResearchObjective(
            id="improvement",
            goal="Ask for one realistically scoped next step.",
            evidence_needed="A review, investigation, or pilot suggested by the respondent.",
            suggested_probes=("What small next step would be worth testing?",),
        ),
        ResearchObjective(
            id="positive_practice",
            goal="Capture a recovery practice worth retaining.",
            evidence_needed="A useful practice, or a clear statement that none comes to mind.",
            suggested_probes=("What has the team done well when recovering?",),
        ),
    ),
    core_objective_ids=("breakdown_event", "impact", "improvement"),
)


INTERVIEW_PLANS: dict[str, InterviewPlan] = {
    plan.id: plan
    for plan in (
        POST_SHIFT_GUEST_EXPERIENCE,
        NEW_PROCESS_ROLLOUT,
        RECURRING_SERVICE_BREAKDOWN,
    )
}
DEFAULT_INTERVIEW_PLAN = POST_SHIFT_GUEST_EXPERIENCE


def get_interview_plan(plan_id: str | None) -> InterviewPlan:
    """Return a known versioned plan; never silently substitute an unknown ID."""
    if plan_id is None:
        return DEFAULT_INTERVIEW_PLAN
    normalized = plan_id.strip()
    if not normalized:
        return DEFAULT_INTERVIEW_PLAN
    try:
        return INTERVIEW_PLANS[normalized]
    except KeyError as exc:
        raise ValueError(f"Unknown interview plan: {normalized}") from exc


def interview_plan_from_job_metadata(raw_metadata: str | None) -> InterviewPlan:
    """Select a plan from the optional top-level LiveKit metadata field."""
    if not raw_metadata:
        return DEFAULT_INTERVIEW_PLAN
    try:
        payload = json.loads(raw_metadata)
    except json.JSONDecodeError as exc:
        raise ValueError("LiveKit job metadata must be valid JSON") from exc
    if not isinstance(payload, dict):
        raise ValueError("LiveKit job metadata must be a JSON object")
    plan_id = payload.get("interview_plan_id")
    if plan_id is not None and not isinstance(plan_id, str):
        raise ValueError("interview_plan_id must be a string")
    return get_interview_plan(plan_id)
