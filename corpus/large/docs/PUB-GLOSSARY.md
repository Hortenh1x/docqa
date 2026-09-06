---
doc_id: PUB-GLOSSARY
title: Product Glossary
version: "1.0"
effective_date: 2025-07-01
owner: Go-to-Market
classification: internal
---

# Product Glossary

## 1. Scope

This glossary defines the key terms used in Kranich Route Cloud, our route-optimization platform for mid-size logistics operators. It is intended for customers, partners, and anyone who works with our product documentation or support materials. The goal is to create a shared vocabulary so that conversations about planning, dispatching, and reporting are clear and consistent.

The terms below cover the main concepts in the product. If a term is missing or unclear, please contact your Customer Success Manager or write to our support team through the in-app help center. We update this glossary as the product evolves.

## 2. Terms

**Route plan.** A complete set of routes assigned to vehicles and drivers for a given operating day. A route plan is the output of an optimization run and the starting point for dispatching. It includes stops, arrival windows, and driving instructions.

**Stop.** A single location where a vehicle pauses to perform work, such as a pickup, a delivery, or a service call. Each stop has an address, a time window if one applies, and a service duration. Stops belong to a route and appear in sequence.

**Time window.** The period during which a stop may be served. A time window can be a single interval or a set of intervals. The optimizer treats time windows as hard or soft depending on the configuration chosen by the planner.

**Hard time window.** A time window that must be respected. The optimizer will not propose a route that violates a hard time window. If no feasible route exists, the optimizer reports an infeasibility rather than suggesting an invalid plan.

**Soft time window.** A time window that the optimizer may violate if doing so improves the overall plan. Violations carry a penalty that the planner can adjust. Soft windows are useful for stops where the customer is flexible, such as internal transfers or low-priority deliveries.

**Service duration.** The time a driver spends at a stop before moving on. It excludes travel time and waiting time. Service duration is set per stop type or per individual stop.

**Travel time.** The estimated time a vehicle needs to move from one stop to the next. Travel time is calculated from our road network model and can be adjusted by a factor to reflect traffic conditions or driver experience.

**Depot.** The location where vehicles start and end their routes. A route plan typically has one or more depots. Vehicles may return to the depot between routes or at the end of the day, depending on the operating model.

**Vehicle.** A physical asset that executes routes. Each vehicle has a capacity profile, an operating schedule, and optional attributes such as refrigeration or liftgate capability. Vehicles are grouped into fleets.

**Fleet.** A collection of vehicles that share a common configuration, such as a depot, a geographic region, or a vehicle type. Fleets help planners manage capacity and assign work.

**Driver.** A person assigned to operate a vehicle. Drivers have working-time rules, preferred regions, and skill levels. The optimizer considers driver availability and legal rest requirements when building routes.

**Capacity.** The maximum load a vehicle can carry, measured in weight, volume, or both. Capacity constraints are enforced during optimization. If a route exceeds capacity, the optimizer splits the work or reports an infeasibility.

**Optimization run.** A single execution of the routing engine over a defined set of orders, vehicles, and depots. A planner can run multiple optimization runs with different settings and compare the results before publishing a route plan.

**Objective.** The criterion the optimizer minimizes or maximizes. Common objectives include total travel time, total distance, or the number of vehicles used. Planners choose the objective before each run.

**Constraint.** A rule that the optimizer must respect. Constraints include time windows, capacity, driver hours, and vehicle compatibility. Constraints are configured in the planning workspace and can be toggled per run.

**Infeasibility.** A situation where no route plan exists that satisfies all constraints. The optimizer reports the source of the infeasibility, such as a stop that cannot be reached within its time window or a vehicle that lacks the required attribute.

**Order.** A request for a pickup or delivery. An order references a stop, a requested time, and a set of items. Orders are the input to an optimization run.

**Route.** A sequence of stops assigned to a single vehicle and driver. A route starts and ends at a depot unless it is an open route, which starts or ends at a customer location.

**Open route.** A route that does not return to the depot after the final stop. Open routes are used when vehicles are staged at remote locations or when drivers end their shift at home.

**Dispatch.** The act of sending a route plan to drivers. Dispatch can be manual, where a planner confirms each route, or automatic, where routes are released when the plan is published.

**Geofence.** A virtual boundary around a location. The system uses geofences to trigger events, such as notifying a customer when a vehicle arrives or recording a stop as completed.

**ETA.** Estimated time of arrival. The system calculates ETAs from live vehicle positions and the current route plan. ETAs are updated as the vehicle moves or as traffic conditions change.

**Live tracking.** The real-time view of vehicle positions on a map. Live tracking is available to dispatchers and, optionally, to customers through a branded portal.

**Customer portal.** A web interface where customers can view their orders, track vehicles, and receive delivery notifications. Access is controlled by the operator.

**Planning workspace.** The main screen where planners build and manage route plans. The workspace shows orders, vehicles, and the optimization controls.

**Scenario.** A saved set of inputs and settings for an optimization run. Scenarios allow planners to compare alternatives, such as using a different fleet size or changing time-window flexibility.

**KPI dashboard.** A reporting view that summarizes operational metrics, such as on-time performance and utilization. The dashboard draws from completed route plans and live data.

**Integration.** A connection between Kranich Route Cloud and an external system, such as a transportation management system or an enterprise resource planning tool. Integrations exchange order and status data automatically.

**API.** Application programming interface. The API allows customers to create orders, retrieve route plans, and update vehicle status programmatically. Documentation is available in the developer portal.

**Sandbox environment.** A separate instance of the product where customers can test configurations and integrations without affecting live operations. The sandbox contains sample data and resets on a regular basis.

Example: Anna, a backend engineer in Lisbon, uses the API to test a new integration for a customer in Poland. She works in the sandbox environment first, then promotes the integration to production after the customer confirms the results.

Example: Deniz, a customer success manager in Berlin, explains to a new customer why their route plan shows an infeasibility. She opens the planning workspace, points to the stop with the hard time window, and suggests widening the window to make the plan feasible.
