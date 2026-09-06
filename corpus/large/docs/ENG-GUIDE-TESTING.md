---
doc_id: ENG-GUIDE-TESTING
title: Testing Standards
version: "1.0"
effective_date: 2025-05-01
owner: Platform & Infrastructure
classification: internal
---

# Testing Standards

## 1. Purpose

This guide describes how we write and maintain automated tests for Kranich Route Cloud. Clear testing standards help us ship changes with confidence, keep the codebase healthy, and make it easier for anyone on the team to pick up work in an unfamiliar area.

We follow these standards across all services and repositories maintained by Platform & Infrastructure and the product teams. If a specific rule does not fit your context, raise it with your engineering manager rather than silently deviating.

## 2. Unit and integration

We distinguish between unit tests and integration tests. Both are valuable, but they serve different purposes and should be written with that distinction in mind.

A unit test exercises a single function, class, or module in isolation. It should not touch the network, the filesystem, or a database. Unit tests run fast and give precise feedback when something breaks. Write them for logic that is easy to reason about in isolation, such as validation rules, sorting and filtering functions, or date calculations.

An integration test verifies that several components work together correctly. It may start a real database container, call an internal API endpoint, or read from a message queue. Integration tests are slower and more brittle, so use them deliberately. Prefer a small number of integration tests that cover the critical paths over a large suite that duplicates unit coverage.

For a change that touches an existing service, you are expected to add or update tests at the same level as the surrounding code. For example, if you modify a routing constraint, add unit tests for the new logic and an integration test that exercises the full request path if one does not already exist.

Example: Anna, a backend engineer in Lisbon, changes how the routing engine handles time windows for multi-stop trips. She adds unit tests for the window-splitting logic and updates the integration test that runs a small route through the API.

Tests should be deterministic. Avoid relying on wall-clock time, random ordering, or environment-specific behavior. If you need a date, inject a fixed one. If you need a unique identifier, generate it explicitly rather than assuming the environment provides one.

When you find a bug, write a test that reproduces it before fixing the code. This guards against regression and documents the expected behavior for future readers.

## 3. Fixtures

Fixtures are shared pieces of test data. They help you avoid repeating setup code and keep tests readable. Use them with care: a fixture that is too broad makes tests hard to follow, while one that is too narrow leads to duplication.

Prefer small, purpose-built fixtures over a single large blob of data. When a test needs a route with several stops, build only the stops that matter for the scenario. If a field is irrelevant to the test, leave it at a sensible default rather than inventing a value that suggests meaning.

Name fixtures by what they represent, not by where they are used. A fixture called `route_with_break` is clearer than `route_for_anna_test`. Keep fixtures close to the tests that use them, either in the same file or in a dedicated fixtures module within the same package.

Example: Deniz, a customer success manager in Berlin, reports that an import of customer waypoints fails when the file contains a header row. Marek, a field solutions engineer, reproduces the issue while working with a client in Poland. Sofia, a product manager, writes a bug ticket. The backend engineer fixing it adds a minimal fixture with a header row and a single waypoint, rather than reusing the full sample file from the documentation.

Do not modify shared fixtures inside a test. If a test needs a variation, create a derived fixture or build the data inline. This prevents subtle coupling between tests that appear unrelated.

When you remove a fixture, check that no test still references it. Stale fixtures accumulate quickly and confuse future readers.

## 4. Questions

If you are unsure whether a test belongs at the unit or integration level, ask a teammate in your engineering channel. A quick conversation is cheaper than a review cycle later.

For questions about test infrastructure, such as how to run a particular suite locally or how to configure a database container, contact Platform & Infrastructure via the it-help alias.

If you believe a standard in this guide should change, propose it to your engineering manager. We review this guide periodically and welcome suggestions grounded in real experience.

For security-sensitive code, follow the additional guidance in POL-004. For questions about how testing relates to release planning or budgeting, refer to FIN-RATES-2026.

Example: Ines Duarte, an engineering manager in Berlin, notices that a new service has no integration tests because the team found the setup confusing. She brings this to the next Platform & Infrastructure sync, and the team agrees to document the recommended setup in the service template.

Above all, write tests that help the next person understand the code. A test that reads clearly and fails with a useful message is worth more than one that merely increases coverage.
