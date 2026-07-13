# SPDX-License-Identifier: CC-BY-SA-4.0
"""Handler Web della pagina di amministrazione ACL (DESIGN §10).

Una pagina unica (`/acl`) con due sezioni:

- **Profili** — livello e gruppi ACL delle persone (``Person.acl``); le
  mutazioni passano da ``PersonService.set_acl_profile`` e sono protette da
  ``MANAGE_PROFILES`` su ``SYSTEM:global`` (fuori dal catalogo delegabile).
- **Regole (AclEntry)** — elenco e gestione delle entry, incluse quelle di
  ambito ``SYSTEM:global`` e delle radici di tipo; le mutazioni sono
  autoprotette da ``MANAGE_ACL`` in :class:`AclService`.
"""
from dataclasses import asdict

from quart import jsonify, render_template

from ....application.services.acl_service import AclService
from ....application.services.person_service import PersonService
from ....domain.acl import Operation, Permission, SYSTEM_GLOBAL_ID, TYPE_ROOT_ID
from ....domain.enums import ResourceType
from ....domain.exceptions import ValidationError
from ..._http import operator_id, parse_json_body, run_blocking
from ..._utils import require_field


class AclRouteHandler:
    def __init__(self, acl_svc: AclService, person_svc: PersonService) -> None:
        self._acl_svc = acl_svc
        self._person_svc = person_svc

    # ------------------------------------------------------------------
    # Pagina
    # ------------------------------------------------------------------

    async def get_page(self):
        persons = await run_blocking(self._person_svc.list, {})
        entries = await run_blocking(
            self._acl_svc.list_all_entries, operator_id=operator_id()
        )
        group_names = sorted({g for p in persons for g in p.acl_groups})
        nickname_by_id = {p.id: p.primary_nickname for p in persons}
        return await render_template(
            "acl_management.html",
            persons=persons,
            entries=entries,
            group_names=group_names,
            nickname_by_id=nickname_by_id,
            operations=[op.value for op in Operation],
            permissions=[perm.value for perm in Permission],
            resource_types=[rt.value for rt in ResourceType],
            type_root_id=TYPE_ROOT_ID,
            system_global_id=SYSTEM_GLOBAL_ID,
        )

    # ------------------------------------------------------------------
    # Profili (MANAGE_PROFILES su SYSTEM:global — mappato nel middleware)
    # ------------------------------------------------------------------

    async def set_profile(self):
        data = await parse_json_body()
        person_id = str(require_field(data, "person_id"))
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
                raise ValidationError("Il livello ACL deve essere un intero", field="acl_level")
        if isinstance(groups, str):
            groups = [g.strip() for g in groups.split(",")]
        if groups is not None:
            groups = [str(g).strip() for g in groups if str(g).strip()]
        dto = await run_blocking(
            self._person_svc.set_acl_profile,
            person_id,
            acl_level=level,
            acl_groups=groups,
        )
        return jsonify(asdict(dto)), 200

    async def remove_profile_group(self):
        data = await parse_json_body()
        person_id = str(require_field(data, "person_id"))
        group = str(require_field(data, "group"))
        dto = await run_blocking(self._person_svc.remove_acl_group, person_id, group)
        return jsonify(asdict(dto)), 200

    # ------------------------------------------------------------------
    # Entry (autoprotette da MANAGE_ACL in AclService)
    # ------------------------------------------------------------------

    async def create_entry(self):
        data = await parse_json_body()
        entry = await run_blocking(
            self._acl_svc.create_entry,
            resource_type=str(require_field(data, "resource_type")),
            resource_id=str(require_field(data, "resource_id")),
            operation=str(require_field(data, "operation")),
            permission=str(require_field(data, "permission")),
            subject_id=data.get("subject_id") or None,
            level=data.get("level"),
            group=data.get("group"),
            profile_join=data.get("profile_join") or "OR",
            subject_join=data.get("subject_join") or "AND",
            operator_id=operator_id(),
        )
        return jsonify(asdict(entry)), 201

    async def delete_entry(self, entry_id: str):
        await run_blocking(
            self._acl_svc.delete_entry, str(entry_id), operator_id=operator_id()
        )
        return "", 204
