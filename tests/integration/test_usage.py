from datetime import UTC, datetime

POLICY_MD = b"# Vacation Policy\n\nEmployees receive 27 vacation days per year.\n"


async def test_usage_totals_and_daily_breakdown(client, tenant):
    created = await client.post(
        "/v1/collections", json={"name": "Usage"}, headers=tenant["headers"]
    )
    collection_id = created.json()["id"]
    upload = await client.post(
        f"/v1/collections/{collection_id}/documents",
        files={"file": ("p.md", POLICY_MD, "text/markdown")},
        headers=tenant["headers"],
    )
    assert upload.status_code == 202

    answered = await client.post(
        "/v1/query",
        json={
            "collection_id": collection_id,
            "question": "How many vacation days do employees receive?",
            "stream": False,
        },
        headers=tenant["headers"],
    )
    assert answered.status_code == 200

    usage = (await client.get("/v1/usage?days=7", headers=tenant["headers"])).json()
    assert usage["queries"] == 1
    assert usage["refused"] == 0
    assert usage["prompt_tokens"] == 100
    assert usage["cost_usd"] == 0.0
    assert len(usage["daily"]) == 1
    assert usage["daily"][0]["date"] == datetime.now(UTC).date().isoformat()
    assert usage["daily"][0]["queries"] == 1


async def test_usage_is_tenant_scoped(client, make_tenant):
    stranger = await make_tenant()
    usage = (await client.get("/v1/usage", headers=stranger["headers"])).json()
    assert usage["queries"] == 0
    assert usage["daily"] == []
