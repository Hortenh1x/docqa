---
doc_id: ENG-ADR-04
title: ADR-04: Pipeline time budget
version: "1.0"
effective_date: 2025-05-20
owner: Platform & Infrastructure
classification: internal
---

# ADR-04: Pipeline time budget

## 1. Status

Accepted.

## 2. Context

The Platform & Infrastructure team maintains the continuous integration and continuous delivery pipelines that build, test, and deploy the Kranich Route Cloud. Over the past year, pipeline runtime has grown noticeably as the codebase expanded and the test suite matured. Several teams reported that waiting for a full pipeline run slowed down their work, particularly when a change touched multiple services at once.

We evaluated what we wanted the pipeline to guarantee. A clear upper bound helps engineers plan their day and reduces the temptation to bypass checks for the sake of speed. It also gives the Platform & Infrastructure team a concrete target when optimizing build steps, caching, and parallelization.

We considered a few options. One was to leave the pipeline unconstrained and rely on teams to optimize their own steps; this had led to the current drift. Another was to set a strict budget that applied to every commit, including trivial documentation changes; that felt unnecessarily rigid. A third option, which we chose, was to define a single budget for the full pipeline and to treat it as a hard ceiling, while allowing teams to propose exceptions through the normal change process.

The decision aligns with the engineering principles we already follow, including the guidance on deployment practices in POL-004. It also complements the financial guardrails described in FIN-RATES-2026, which govern how we allocate infrastructure spend; a time budget indirectly protects that spend by discouraging wasteful pipeline configurations.

## 3. Decision

The full pipeline must finish within 68 minutes. This budget covers the complete run from the moment a commit is picked up to the moment artifacts are ready for deployment. It includes compilation, unit and integration tests, container builds, and the packaging steps.

We define "full pipeline" as the end-to-end sequence that runs for a merge to the main branch. Short-lived checks, such as a quick lint on a pull request, are not part of this budget. However, any step that runs in the main-branch pipeline counts toward the 68 minutes, regardless of which team owns the step.

To make the budget enforceable, we add a monitoring alert that fires when a pipeline run approaches the ceiling. If a run exceeds the budget, the pipeline fails and the owning team receives a notification. The team can then investigate and either optimize the step or open a request to exempt that particular pipeline from the budget. Exemptions are reviewed by Platform & Infrastructure and are meant to be temporary; we expect teams to treat an exemption as a prompt to refactor rather than as a permanent allowance.

We also commit to reviewing the budget on a regular cadence. If the product roadmap introduces work that fundamentally changes the build shape, we may revisit this decision, but any change to the 68 minutes will go through the same architecture review process as this document.

## 4. Consequences

The primary benefit is predictability. Engineers can plan their work knowing that a full pipeline run will not stretch beyond the budget. This reduces context switching and helps teams integrate changes more smoothly.

The budget also creates a forcing function for optimization. Teams will need to keep their test suites efficient and their build steps lean. In the long run, this should lower infrastructure cost and improve developer experience.

There are trade-offs. Some teams may need to invest time in splitting large test suites or improving caching before they can comfortably fit within the budget. In rare cases, a legitimate change may require more than the ceiling allows; the exemption process exists for those situations, and we trust teams to use it honestly.

Another consequence is that the Platform & Infrastructure team takes on an ongoing duty to keep the shared build infrastructure healthy. We own the monitoring and the alerting, and we will work with teams whose pipelines regularly approach the limit.

Finally, this decision makes our engineering practices more explicit. New hires and existing employees alike can read this document and understand what we expect from the pipeline, without having to guess. We will link this ADR from the development handbook and mention it in onboarding materials.
