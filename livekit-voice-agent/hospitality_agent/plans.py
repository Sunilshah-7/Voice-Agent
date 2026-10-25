"""Versioned non-emergency call-intake plans shipped with the prototype."""

from __future__ import annotations

import json

from .models import InterviewPlan, ResearchObjective


_OPENING_PREFIX = (
    "Hi, I'm ShiftSignal, an AI non-emergency call intake agent. I can collect "
    "information for human review, but I am not a dispatcher and cannot send help. "
    "If anyone is in immediate danger or needs urgent police, fire, or medical help, "
    "call 911 or your local emergency number now. You can skip a question or end the "
    "call at any time. Please do not share names or contact information unless a later "
    "step specifically requests it. "
)

_CLOSING_MESSAGE = (
    "Thank you. The information you provided can now be forwarded for human review. "
    "I cannot promise a response, enforcement action, or outcome."
)

_OPTIONAL_CALLER_CONTACT = ResearchObjective(
    id="caller_contact",
    goal="Offer the caller an optional way to provide a name and contact method for follow-up.",
    evidence_needed=(
        "An optional caller name and contact method, a preference to remain unnamed, or a skip."
    ),
    suggested_probes=(
        "Would you like to leave a name and contact method for follow-up? This is optional.",
    ),
)


GENERAL_INQUIRY = InterviewPlan(
    id="general_inquiry",
    version="1.0",
    title="General non-emergency inquiry or request",
    business_goal=(
        "Understand and document a routine public-safety inquiry or service request that "
        "does not clearly fit parking, lost-pet, or noise-complaint intake."
    ),
    respondent_type="Community member with a non-emergency inquiry or request",
    target_duration_seconds=300,
    max_respondent_turns=10,
    opening_message=(
        _OPENING_PREFIX
        + "I can help with parking complaints, missing or found pets, noise complaints, "
        "and other routine requests. What can I help you with today?"
    ),
    closing_message=_CLOSING_MESSAGE,
    objectives=(
        ResearchObjective(
            id="request_type",
            goal="Identify what the caller is asking about and whether a primary category applies.",
            evidence_needed=(
                "Parking complaint, lost or found pet, noise complaint, another routine "
                "request, or a clear statement that the caller is unsure."
            ),
            suggested_probes=("What would you like help with today?",),
        ),
        ResearchObjective(
            id="request_details",
            goal="Capture the facts needed to understand the inquiry or request.",
            evidence_needed="A concise firsthand description without speculation or unnecessary identifiers.",
            suggested_probes=("What happened, or what information do you need?",),
        ),
        ResearchObjective(
            id="location",
            goal="Capture the relevant location when one is needed to review the request.",
            evidence_needed="A location, nearby landmark, or a clear statement that location is not relevant.",
            suggested_probes=("Where is this happening?",),
        ),
        ResearchObjective(
            id="timing",
            goal="Capture when the issue happened and whether it is still occurring.",
            evidence_needed="Reported timing and current status, or confirmation that timing is not relevant.",
            suggested_probes=("When did this happen, and is it still happening?",),
        ),
        ResearchObjective(
            id="requested_outcome",
            goal="Understand what information or follow-up the caller is seeking.",
            evidence_needed="The caller's requested outcome or a clear statement that they are unsure.",
            suggested_probes=("What would you like the reviewing team to help with?",),
        ),
        _OPTIONAL_CALLER_CONTACT,
    ),
    core_objective_ids=("request_type", "request_details"),
)


PARKING_COMPLAINT = InterviewPlan(
    id="parking_complaint",
    version="1.0",
    title="Parking complaint intake",
    business_goal=(
        "Document an illegal-parking, blocked-driveway, or potentially abandoned-vehicle "
        "complaint accurately enough for human review."
    ),
    respondent_type="Community member reporting a non-emergency parking concern",
    target_duration_seconds=300,
    max_respondent_turns=10,
    opening_message=(
        _OPENING_PREFIX
        + "I'll collect the details of your parking concern for review. Is this about "
        "illegal parking, a blocked driveway, an abandoned vehicle, or something else?"
    ),
    closing_message=_CLOSING_MESSAGE,
    objectives=(
        ResearchObjective(
            id="parking_issue",
            goal="Classify the parking concern without making a legal determination.",
            evidence_needed=(
                "The caller's report of illegal parking, a blocked driveway, an abandoned "
                "vehicle, or another parking concern."
            ),
            suggested_probes=("What kind of parking problem are you reporting?",),
        ),
        ResearchObjective(
            id="location",
            goal="Capture where the vehicle is located.",
            evidence_needed="A street, intersection, address, or nearby landmark sufficient for review.",
            suggested_probes=("Where is the vehicle located?",),
        ),
        ResearchObjective(
            id="vehicle_description",
            goal="Capture observable vehicle details that can distinguish it.",
            evidence_needed="Known make, model, color, body type, or plate; unknown details remain unknown.",
            suggested_probes=("How would you describe the vehicle?",),
        ),
        ResearchObjective(
            id="timing_and_duration",
            goal="Capture when the vehicle was observed and how long it may have been there.",
            evidence_needed="Observed time or duration stated in the caller's own terms.",
            suggested_probes=("When did you notice it, and how long has it been there?",),
        ),
        ResearchObjective(
            id="observed_impact",
            goal="Document what the vehicle is blocking or affecting.",
            evidence_needed="A firsthand impact, such as blocked access, or a clear report of no known impact.",
            suggested_probes=("What access or area is the vehicle affecting?",),
        ),
        _OPTIONAL_CALLER_CONTACT,
    ),
    core_objective_ids=("parking_issue", "location", "vehicle_description"),
)


LOST_PET = InterviewPlan(
    id="lost_pet",
    version="1.0",
    title="Missing or found pet intake",
    business_goal=(
        "Document a missing dog or cat, or a found animal, with enough observable detail "
        "and location information for human review."
    ),
    respondent_type="Community member reporting a missing or found animal",
    target_duration_seconds=300,
    max_respondent_turns=10,
    opening_message=(
        _OPENING_PREFIX
        + "I'll collect information about the animal for review. Are you reporting a "
        "missing pet or an animal you found?"
    ),
    closing_message=_CLOSING_MESSAGE,
    objectives=(
        ResearchObjective(
            id="pet_report_type",
            goal="Determine whether the caller is reporting a missing pet or a found animal.",
            evidence_needed="Missing, found, or an accurate statement that the caller is unsure.",
            suggested_probes=("Is the animal missing or found?",),
        ),
        ResearchObjective(
            id="animal_description",
            goal="Capture observable details that can identify the animal.",
            evidence_needed=(
                "Known species, breed or type, size, color, markings, collar, tag, and other "
                "distinctive features without inventing unknown details."
            ),
            suggested_probes=("What does the animal look like?",),
        ),
        ResearchObjective(
            id="last_known_location",
            goal="Capture where the animal was last seen or found.",
            evidence_needed="A location, nearby landmark, and direction of travel when known.",
            suggested_probes=("Where and in which direction was the animal last seen?",),
        ),
        ResearchObjective(
            id="timing",
            goal="Capture when the animal went missing or was found.",
            evidence_needed="The caller's best available date and time, with uncertainty preserved.",
            suggested_probes=("When was the animal last seen or found?",),
        ),
        ResearchObjective(
            id="current_situation",
            goal="Understand the animal's current observed situation.",
            evidence_needed=(
                "Whether the animal is contained, roaming, injured, or behaving aggressively, "
                "based only on what the caller observed."
            ),
            suggested_probes=("What is the animal doing now, if you can still see it?",),
        ),
        _OPTIONAL_CALLER_CONTACT,
    ),
    core_objective_ids=("pet_report_type", "animal_description", "last_known_location"),
)


NOISE_COMPLAINT = InterviewPlan(
    id="noise_complaint",
    version="1.0",
    title="Noise complaint intake",
    business_goal=(
        "Document a loud-party, construction-noise, or neighborhood-disturbance complaint "
        "accurately enough for human review."
    ),
    respondent_type="Community member reporting a non-emergency noise concern",
    target_duration_seconds=300,
    max_respondent_turns=10,
    opening_message=(
        _OPENING_PREFIX
        + "I'll collect the details of your noise concern for review. Is the noise from "
        "a party, construction, a neighborhood disturbance, or something else?"
    ),
    closing_message=_CLOSING_MESSAGE,
    objectives=(
        ResearchObjective(
            id="noise_source",
            goal="Identify the reported source and character of the noise.",
            evidence_needed="A party, construction, neighborhood disturbance, or another described source.",
            suggested_probes=("What kind of noise are you hearing?",),
        ),
        ResearchObjective(
            id="location",
            goal="Capture where the noise appears to be coming from.",
            evidence_needed="An address, street, intersection, unit area, or nearby landmark when known.",
            suggested_probes=("Where does the noise seem to be coming from?",),
        ),
        ResearchObjective(
            id="timing_and_duration",
            goal="Capture when the noise began, its duration, and whether it is ongoing.",
            evidence_needed="Observed start time or duration and current status, with uncertainty preserved.",
            suggested_probes=("When did it begin, and is it still happening?",),
        ),
        ResearchObjective(
            id="recurrence",
            goal="Capture whether the disturbance is isolated or recurring.",
            evidence_needed="The caller's own description of frequency; never an invented count.",
            suggested_probes=("Is this the first time, or has it happened before?",),
        ),
        ResearchObjective(
            id="observed_impact",
            goal="Document the effect of the noise without exaggeration.",
            evidence_needed="A concrete effect described by the caller, or a clear report of no additional impact.",
            suggested_probes=("How is the noise affecting you or the surrounding area?",),
        ),
        _OPTIONAL_CALLER_CONTACT,
    ),
    core_objective_ids=("noise_source", "location", "timing_and_duration"),
)


INTERVIEW_PLANS: dict[str, InterviewPlan] = {
    plan.id: plan
    for plan in (
        GENERAL_INQUIRY,
        PARKING_COMPLAINT,
        LOST_PET,
        NOISE_COMPLAINT,
    )
}
DEFAULT_INTERVIEW_PLAN = GENERAL_INQUIRY


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
    """Select a plan from optional LiveKit metadata.

    ``call_category`` is the public domain term. ``interview_plan_id`` remains accepted
    so existing LiveKit dispatch metadata does not break during the domain migration.
    """
    if not raw_metadata:
        return DEFAULT_INTERVIEW_PLAN
    try:
        payload = json.loads(raw_metadata)
    except json.JSONDecodeError as exc:
        raise ValueError("LiveKit job metadata must be valid JSON") from exc
    if not isinstance(payload, dict):
        raise ValueError("LiveKit job metadata must be a JSON object")
    plan_id = payload.get("call_category", payload.get("interview_plan_id"))
    if plan_id is not None and not isinstance(plan_id, str):
        raise ValueError("call_category must be a string")
    return get_interview_plan(plan_id)
