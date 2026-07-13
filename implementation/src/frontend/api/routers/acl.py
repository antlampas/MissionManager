# SPDX-License-Identifier: CC-BY-SA-4.0
"""Router REST del sistema ACL (DESIGN §10).

Gestione delle AclEntry (autoprotetta da MANAGE_ACL in AclService) e
assegnazione del profilo ACL delle persone (fuori dal catalogo delegabile,
protetta da MANAGE_PROFILES su SYSTEM:global nel middleware):

  GET    /api/acl/entries[?resource_type=&resource_id=]   lista entry
  POST   /api/acl/entries                                 crea entry
  PATCH  /api/acl/entries/<entry_id>                      aggiorna entry
  DELETE /api/acl/entries/<entry_id>                      elimina entry
  PUT    /api/persons/<id>/acl                            profilo (level/groups)
"""
from dataclasses import asdict
from uuid import UUID

from quart import jsonify, request
from quart.views import MethodView

from ....application.services.acl_service import AclService
from ....application.services.person_service import PersonService
from ....domain.exceptions import ValidationError
from ..._http import operator_id, parse_json_body, run_blocking
from ..._utils import require_field


class AclEntriesRouter(MethodView):
    def __init__(self, svc: AclService, **kwargs) -> None:
        self._svc = svc

    async def get(self):
        resource_type = request.args.get("resource_type")
        resource_id = request.args.get("resource_id")
        if resource_type and resource_id:
            entries = await run_blocking(
                self._svc.list_entries,
                resource_type,
                resource_id,
                operator_id=operator_id(),
            )
        else:
            entries = await run_blocking(
                self._svc.list_all_entries, operator_id=operator_id()
            )
        return jsonify([asdict(entry) for entry in entries]), 200

    async def post(self):
        data = await parse_json_body()
        entry = await run_blocking(
            self._svc.create_entry,
            resource_type=str(require_field(data, "resource_type")),
            resource_id=str(require_field(data, "resource_id")),
            operation=str(require_field(data, "operation")),
            permission=str(require_field(data, "permission")),
            subject_id=data.get("subject_id"),
            level=data.get("level"),
            group=data.get("group"),
            profile_join=data.get("profile_join", "OR"),
            subject_join=data.get("subject_join", "AND"),
            operator_id=operator_id(),
        )
        return jsonify(asdict(entry)), 201


class AclEntryRouter(MethodView):
    def __init__(self, svc: AclService, **kwargs) -> None:
        self._svc = svc

    async def patch(self, entry_id: str):
        data = await parse_json_body()
        entry = await run_blocking(
            self._svc.update_entry,
            entry_id,
            permission=data.get("permission"),
            level=data.get("level"),
            group=data.get("group"),
            clear_level="level" in data and data.get("level") is None,
            clear_group="group" in data and data.get("group") is None,
            operator_id=operator_id(),
        )
        return jsonify(asdict(entry)), 200

    async def delete(self, entry_id: str):
        await run_blocking(self._svc.delete_entry, entry_id, operator_id=operator_id())
        return "", 204


class PersonAclRouter(MethodView):
    """Assegna il profilo ACL (livello e gruppi) di una persona."""

    def __init__(self, svc: PersonService, **kwargs) -> None:
        self._svc = svc

    async def put(self, id: UUID):
        data = await parse_json_body()
        level = data.get("acl_level")
        groups = data.get("acl_groups")
        if level is None and groups is None:
            raise ValidationError(
                "Indicare almeno uno tra acl_level e acl_groups", field="acl_level"
            )
        if level is not None:
            try:
                level = int(level)
            except (TypeError, ValueError):
                raise ValidationError("acl_level deve essere un intero", field="acl_level")
        if groups is not None and not isinstance(groups, list):
            raise ValidationError(
                "acl_groups deve essere una lista di stringhe", field="acl_groups"
            )
        dto = await run_blocking(
            self._svc.set_acl_profile,
            str(id),
            acl_level=level,
            acl_groups=[str(g) for g in groups] if groups is not None else None,
            operator_id=operator_id(),
        )
        return jsonify(asdict(dto)), 200
