// Doosri Raay circle rules - the single source of truth for who may do what.
//
// Principal  Member::"<sub>"   attrs: sub, role (parent|guardian1|guardian2|son), circleId
// Action     Action::"ViewCase" | "ViewReport" | "ViewTasks" | "CompleteTask" | "ResetDemo"
//            | "ViewSources" | "UpdateParentSettings"
// Resource   Resource::"<id>"  attrs: circleId, assigneeSub, kind, covert (bool), status,
//                                     ownerSub, ownerRole
//
// Evaluated by common/authz (cedarpy; a minimal evaluator of this same file is the fallback).
// Every @id is mapped to a bilingual denial message in common/authz/__init__.py.

// Members of the same circle may look at the circle's cases, reports, tasks and sources.
@id("same-circle-view")
permit (
  principal,
  action in [Action::"ViewCase", Action::"ViewReport", Action::"ViewTasks", Action::"ViewSources"],
  resource
)
when { principal.circleId == resource.circleId };

// A guardian may complete any task of the circle.
@id("guardian-completes-circle-task")
permit (principal, action == Action::"CompleteTask", resource)
when {
  principal.circleId == resource.circleId &&
  (principal.role == "guardian1" || principal.role == "guardian2")
};

// The son may complete only the tasks assigned to him (the code-word challenge).
@id("son-completes-own-task")
permit (principal, action == Action::"CompleteTask", resource)
when {
  principal.circleId == resource.circleId &&
  principal.role == "son" &&
  resource.assigneeSub == principal.sub
};

// Guardians run the demo reset.
@id("guardian-resets-demo")
permit (principal, action == Action::"ResetDemo", resource)
when {
  principal.circleId == resource.circleId &&
  (principal.role == "guardian1" || principal.role == "guardian2")
};

// Everyone edits their own profile.
@id("member-updates-own-profile")
permit (principal, action == Action::"UpdateParentSettings", resource)
when { principal.sub == resource.ownerSub };

// The parent never sees the covert kinds (sos, guardian_call, neighbour, emergency):
// nothing about the ladder appears on the parent's screen.
@id("covert-hidden-from-parent")
forbid (principal, action in [Action::"ViewTasks", Action::"CompleteTask"], resource)
when { principal.role == "parent" && resource.covert == true };

// Guardians are notified about the parent; they do not change the parent's settings.
@id("guardian-notification-only")
forbid (principal, action == Action::"UpdateParentSettings", resource)
when { resource.ownerRole == "parent" && principal.sub != resource.ownerSub };

// Nothing crosses a circle boundary (handlers still answer 404 to avoid id oracles).
@id("cross-circle")
forbid (principal, action, resource)
when { principal.circleId != resource.circleId };

// A task that is not open (done / expired) cannot be completed again.
@id("task-not-open")
forbid (principal, action == Action::"CompleteTask", resource)
when { resource.status != "open" };
