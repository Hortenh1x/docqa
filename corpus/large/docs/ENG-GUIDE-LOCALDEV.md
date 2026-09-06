---
doc_id: ENG-GUIDE-LOCALDEV
title: Local Development Setup
version: "1.0"
effective_date: 2025-05-01
owner: Platform & Infrastructure
classification: internal
---

# Local Development Setup

## 1. Purpose

This guide explains how to set up a local development environment for Kranich Route Cloud. A working local setup lets you iterate quickly, run tests, and debug issues without affecting shared environments.

We keep this guide deliberately short. If you hit a problem that is not covered here, ask in the Platform & Infrastructure channel on Grove, or write to it-help@kranich.example. Someone will help you promptly.

## 2. Prerequisites

Before you start, make sure you have the following:

- A laptop or workstation with a current operating system. We support the major desktop platforms.
- Access to the Kranich GitHub organization. If you do not have access yet, ask your engineering manager to add you.
- 1Password installed and unlocked. You will need it to retrieve secrets for local services.
- Docker installed and running. Most services run in containers so that your host system stays clean.
- A stable internet connection for the first setup. Later steps work offline once images are cached.

Example: Anna, a backend engineer in Lisbon, set up her environment on a fresh laptop over a weekend. She followed the steps below in order and was ready to run the full test suite by Monday morning.

## 3. Running services

### 3.1 Clone the repositories

Kranich Route Cloud consists of several repositories. Start with the main application repository, then clone the supporting repositories you need for your team.

- Routing Core: the main routing engine and API.
- Fleet Insights: telemetry and analytics services.
- Platform & Infrastructure: shared tooling, deployment scripts, and local orchestration.

Clone each repository into a directory of your choice. Use SSH, not HTTPS, so that your credentials are handled by 1Password.

### 3.2 Start the local stack

Each repository contains a `docker-compose.yml` file. From the repository root, run the standard command to start the services in the background.

The first start downloads images and may take a while. Subsequent starts are faster.

Once the stack is up, check the health endpoint in your browser. If the page loads, the core services are running.

### 3.3 Configure environment variables

Environment variables are stored in a `.env` file that is not committed to version control. Copy the example file provided in the repository and adjust it locally.

Secrets such as database passwords and API keys are not in the example file. Retrieve them from 1Password using the vault named "Local Development". Never hardcode secrets in source files or share them in chat.

Example: Deniz, a customer success manager in Berlin, does not normally run services locally. When she needed to reproduce a client issue, Marek, a field solutions engineer, walked her through the setup. She copied the example environment file, fetched the correct vault items from 1Password, and had the stack running within an hour.

### 3.4 Database migrations

Before you can use the application, apply the latest database migrations. The repository includes a script that runs all pending migrations in order. Run it from the repository root.

If the script reports a conflict, your local database may be out of sync with the migration history. In that case, reset the local database using the provided reset script, then run the migrations again. Do not reset shared databases.

### 3.5 Seed data

The application includes a seed script that creates realistic demo data: a few routes, vehicles, and customers. This is useful for manual testing and for reproducing issues reported by clients.

Run the seed script once after migrations. You can run it again later to restore a clean state.

### 3.6 Verify your setup

To confirm everything works, run the test suite for the service you are working on. The test runner is configured to use the local stack automatically.

A green test run means your environment is ready. If tests fail because of infrastructure issues, check that all containers are healthy and that the environment variables match the 1Password vault.

### 3.7 Stopping and cleaning up

When you finish working, stop the containers to free up system resources. Use the standard command to bring the stack down.

If you want to remove all local data, use the down command with the volume flag. This deletes databases and caches. You will need to run migrations and seed data again next time.

## 4. Questions

If you run into trouble, try these steps in order:

- Check the troubleshooting section in the repository README.
- Search Grove for past discussions about local development.
- Ask in the Platform & Infrastructure channel.
- Write to it-help@kranich.example.

For access requests or permission changes, copy your engineering manager. For anything related to security, contact security@kranich.example.

Example: Sofia, a product manager in Fleet Insights working remotely from Spain, needed to preview a new reporting view. She followed this guide, asked one clarifying question in the team channel, and had the stack running the same afternoon.

We update this guide as the tooling evolves. If you notice something outdated, suggest a change in the documentation repository. Small improvements from the whole company keep this guide useful for everyone.
