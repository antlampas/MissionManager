# SPDX-License-Identifier: CC-BY-SA-4.0
"""Dettaglio assegnazione (Web): il campo "Assegnatario" mostra il nome della
persona o del gruppo, non l'UUID grezzo.
"""
import asyncio
import re
import uuid

from src.application.services._shared import acl_bypass


async def _csrf(client, path: str) -> str:
    response = await client.get(path)
    match = re.search(
        r'name="csrf-token" content="([^"]+)"',
        (await response.get_data()).decode(),
    )
    assert match
    return match.group(1)


async def _login(client):
    csrf = await _csrf(client, "/login")
    await client.post(
        "/login",
        form={"username": "admin", "password": "ValidPassword1!", "csrf_token": csrf},
    )


def _assignee_block(body: str) -> str:
    match = re.search(r"Assegnatario</dt>\s*<dd[^>]*>(.*?)</dd>", body, re.S)
    assert match, "blocco Assegnatario non trovato"
    return match.group(1)


def test_assignee_shows_person_and_group_name(web_app, seed_admin):
    app, svcs = web_app
    admin = seed_admin(svcs)
    op = uuid.UUID(admin.id)

    objectives = [{"description": "Obiettivo", "activities": [{"title": "Attività"}]}]
    mission_p = svcs.mission.create("Op Persona", "d", objectives, operator_id=op)
    mission_g = svcs.mission.create("Op Gruppo", "d", objectives, operator_id=op)

    with acl_bypass():
        person = svcs.person.add(nicknames=["Alice Rossi"])
        group = svcs.person.add_group(
            name="Squadra Alfa", zone_type="GEOGRAPHIC", zone_description="Nord"
        )

    asg_p = svcs.assignment.create(
        mission_id=mission_p.id, assignee_type="PERSON", assignee_id=person.id, operator_id=op
    )
    asg_g = svcs.assignment.create(
        mission_id=mission_g.id, assignee_type="GROUP", assignee_id=group.id, operator_id=op
    )

    async def scenario():
        client = app.test_client()
        await _login(client)

        body_p = (await (await client.get(f"/assignments/{asg_p.id}")).get_data()).decode()
        block_p = _assignee_block(body_p)
        assert "Alice Rossi" in block_p
        assert person.id not in block_p  # niente UUID grezzo

        body_g = (await (await client.get(f"/assignments/{asg_g.id}")).get_data()).decode()
        block_g = _assignee_block(body_g)
        assert "Squadra Alfa" in block_g
        assert group.id not in block_g

    asyncio.run(scenario())
