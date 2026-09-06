---
doc_id: ENG-RFC-09
title: RFC-09: Background job scheduler
version: "1.0"
effective_date: 2025-09-10
owner: Platform & Infrastructure
classification: internal
---

# RFC-09: Background job scheduler

## 1. Context

Several Kranich Route Cloud services currently execute periodic or deferred work inside their own request handlers. Fleet Insights recalculates vehicle utilization summaries after every telematics batch import. Routing Core sends notification emails directly from the API process when a route plan is published. Customer Success relies on ad-hoc scripts to re-run failed webhook deliveries.

This approach has grown fragile. A long-running recalculation blocks the request thread. A spike in telematics imports can delay ordinary API responses. When a process restarts mid-job, the work is simply lost. Engineers have responded by adding retry loops and sleep statements inside application code, which makes behaviour hard to observe and harder to reason about.

We need a shared background job scheduler that all teams can adopt. The scheduler should accept jobs, execute them reliably, retry failures with backoff, and expose visibility into job state. It should be simple to operate and not require every team to become an expert in distributed queuing.

This RFC proposes a central scheduler service owned by Platform & Infrastructure, built on infrastructure we already run.

## 2. Proposal

We introduce a dedicated background job scheduler service, named internally "the scheduler". It provides a small HTTP API for enqueuing jobs and querying their status, plus a worker pool that executes jobs with at-least-once semantics.

The scheduler is not a general-purpose message bus. It is for jobs: discrete units of work with a type, a payload, and a timeout. Teams enqueue jobs from their services and the scheduler handles execution, retries, and dead-lettering.

We will build the scheduler on top of our existing PostgreSQL cluster, using a table-based queue. This avoids introducing a new storage technology and lets us reuse our backup, monitoring, and failover practices. Workers poll for due jobs, claim them transactionally, and update state as they run.

The service will be written in Go, matching the Platform & Infrastructure team's current stack. It will expose Prometheus metrics for queue depth, job duration, and failure rates.

## 3. Details

### 3.1 Job model

A job has the following fields:

- `id`: a unique identifier assigned by the scheduler.
- `type`: a string identifying the kind of work, for example `telematics.summary.recalculate` or `routeplan.published.notify`.
- `payload`: an opaque JSON object defined by the enqueuing service.
- `state`: one of `queued`, `running`, `succeeded`, `failed`, or `dead`.
- `attempts`: the number of execution attempts so far.
- `run_after`: the earliest time at which the job may be claimed.
- `timeout`: the maximum duration a single attempt may take.

Jobs are enqueued with a `run_after` timestamp to support delayed execution. A job that fails is requeued with an exponentially increasing delay. After the maximum number of attempts, the job moves to `dead` and is visible in the dead-letter view.

### 3.2 API

Services interact with the scheduler over HTTP:

- `POST /jobs` enqueues a new job.
- `GET /jobs/{id}` returns the current state and attempt history.
- `POST /jobs/{id}/retry` moves a dead job back to `queued`.
- `GET /jobs?state=dead` lists dead jobs for a given type.

Authentication uses the same internal service tokens as other platform services. Payload size is limited; large artifacts should be referenced by object key rather than embedded.

### 3.3 Execution semantics

Workers claim jobs by updating a claimed row within a transaction. Once claimed, the job is marked `running` and a lease timestamp is set. The worker executes the job by calling a registered handler. Handlers are registered in the scheduler process itself, not in the enqueuing service.

This is an important design decision: the scheduler does not call back into the enqueuing service over the network. Instead, teams deploy their job handler code as part of the scheduler deployment. This keeps execution local and avoids a class of distributed deadlock problems.

If a worker crashes while a job is `running`, the lease expires and the job becomes claimable again. This gives at-least-once delivery. Job handlers must therefore be idempotent. The scheduler cannot guarantee exactly-once execution.

### 3.4 Retries and dead letters

A job that panics, returns an error, or exceeds its timeout is considered failed. The scheduler increments the attempt counter and computes the next `run_after` using exponential backoff with jitter. After the attempt limit is reached, the job is marked `dead` and no further automatic attempts occur.

Dead jobs are not deleted. They remain in the dead-letter table for inspection and manual retry. Platform & Infrastructure will provide a simple dashboard view, but the primary interface is the API.

### 3.5 Observability

Every job execution emits a structured log line with the job id, type, duration, and outcome. Metrics are exposed for:

- queue depth by type and state
- execution duration histogram
- retry counts
- dead-letter rate

Alerts will be configured for sustained dead-letter growth and for queue depth exceeding a threshold that indicates a downstream problem.

## 4. Alternatives considered

### 4.1 Managed queue service

We evaluated using a managed queue offering from our cloud provider. It would reduce our operational burden and offer features like FIFO queues and built-in dead-letter handling. However, it would introduce a new dependency with per-message costs that grow with our telematics volume. It also makes local development and testing harder, since the managed service is not available in our local development environment.

### 4.2 Dedicated job queue technology

We considered running a dedicated job queue system, such as Sidekiq or Celery, on our own infrastructure. These are mature and widely used. The main drawback is operational diversity: we would run another stateful service with its own storage, backup, and failover story. Our team is small and we prefer to consolidate around PostgreSQL, which we already operate well.

### 4.3 In-process job tables

Each service could keep its own job table and run its own worker goroutines. This is where we started, and it is the status quo. The problem is duplication: every team reimplements claiming, retries, and backoff slightly differently. Debugging cross-service flows becomes difficult because job state lives in many places. A shared scheduler centralizes these concerns.

### 4.4 External task runner

We briefly considered triggering jobs through an external task runner invoked by cron. This works for periodic work but is a poor fit for event-driven jobs such as "recalculate after this import finishes". The scheduler supports both patterns: periodic jobs are enqueued by a lightweight cron loop inside the scheduler, while event-driven jobs are enqueued via the API.

## 5. Rollout

Platform & Infrastructure will build the scheduler in the current quarter. We will start with a small set of internal jobs that we own, to validate the operational model.

In the following quarter, we will invite Routing Core and Fleet Insights to migrate their first job types. The migration for each job type follows the same pattern: move the handler code into the scheduler deployment, enqueue from the service instead of executing inline, and verify behaviour in staging.

Customer Success will not need to change anything immediately. Their ad-hoc scripts will continue to work, but we will offer a path to move recurring webhook retries onto the scheduler once the service is stable.

During the transition, both the old inline execution path and the new scheduler path will exist. Teams can switch a job type back if they encounter issues. We expect the old paths to be removed by the end of the year.

## 6. Open questions

- Should the scheduler support priority classes for jobs, or is a single FIFO-with-delay queue sufficient for our current needs?
- Do we need per-tenant isolation for job queues, given that Kranich Route Cloud serves multiple logistics operators from the same deployment?
- How should we handle jobs whose payload references data that has been deleted by the time the job runs? Should the scheduler enforce a maximum job age?
- What is the right owner for the dead-letter review process? Platform & Infrastructure can build the tooling, but each team should probably review its own dead jobs.
- Should periodic jobs be defined declaratively in configuration, or remain code-level constructs inside the scheduler?
