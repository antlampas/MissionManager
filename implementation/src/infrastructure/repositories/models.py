# SPDX-License-Identifier: CC-BY-SA-4.0
from __future__ import annotations

import uuid as _uuid_mod
from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Table,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, relationship
from sqlalchemy.types import TypeDecorator


class _UUIDType(TypeDecorator):
    """UUID stored as VARCHAR(36) — compatible with PostgreSQL and MySQL."""

    impl = String(36)
    cache_ok = True

    def process_bind_param(self, value, dialect):
        return str(value) if value is not None else None

    def process_result_value(self, value, dialect):
        return _uuid_mod.UUID(value) if value is not None else None


class Base(DeclarativeBase):
    pass


_person_group = Table(
    "mm_person_groups",
    Base.metadata,
    Column("person_id", _UUIDType, ForeignKey("mm_persons.id"), primary_key=True),
    Column("group_id", _UUIDType, ForeignKey("mm_groups.id"), primary_key=True),
)


class ZoneRow(Base):
    __tablename__ = "mm_zones"

    id = Column(_UUIDType, primary_key=True, default=_uuid_mod.uuid4)
    type = Column(String(20), nullable=False)
    name = Column(String(255), nullable=False)
    description = Column(String(1024), nullable=True)


class GroupRow(Base):
    __tablename__ = "mm_groups"

    id = Column(_UUIDType, primary_key=True, default=_uuid_mod.uuid4)
    zone_id = Column(_UUIDType, ForeignKey("mm_zones.id"), nullable=True)

    zone = relationship("ZoneRow", lazy="joined")
    members = relationship("PersonRow", secondary=_person_group, back_populates="groups", lazy="select")


class PersonRow(Base):
    __tablename__ = "mm_persons"

    id = Column(_UUIDType, primary_key=True, default=_uuid_mod.uuid4)
    nicknames = Column(JSON, nullable=False)
    # Profilo ACL (DESIGN §10): livello intero (più basso = più privilegiato,
    # default = sentinella anonima) e lista JSON dei gruppi ACL espliciti
    # (il gruppo universale "public" è implicito e non viene persistito).
    acl_level = Column(Integer, nullable=False, default=2**31 - 1)
    acl_groups = Column(JSON, nullable=False, default=list)

    groups = relationship("GroupRow", secondary=_person_group, back_populates="members", lazy="select")


class BadgeRow(Base):
    __tablename__ = "mm_badges"

    id = Column(_UUIDType, primary_key=True, default=_uuid_mod.uuid4)
    name = Column(String(255), nullable=False)
    description = Column(String(1024), nullable=False, default="")
    image_url = Column(String(1024), nullable=True)


class BadgeAwardRow(Base):
    __tablename__ = "mm_badge_awards"
    __table_args__ = (
        UniqueConstraint("target_type", "target_id", name="uq_mm_badge_award_target"),
    )

    id = Column(_UUIDType, primary_key=True, default=_uuid_mod.uuid4)
    badge_id = Column(_UUIDType, ForeignKey("mm_badges.id"), nullable=False)
    target_type = Column(String(20), nullable=False)
    target_id = Column(_UUIDType, nullable=False)
    recipients = Column(JSON, nullable=False)
    awarded_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))


class MissionRow(Base):
    __tablename__ = "mm_missions"

    id = Column(_UUIDType, primary_key=True, default=_uuid_mod.uuid4)
    title = Column(String(255), nullable=False)
    description = Column(String(4096), nullable=False, default="")
    policy_max_total = Column(Integer, nullable=True)
    policy_max_concurrent = Column(Integer, nullable=True)


class ObjectiveRow(Base):
    __tablename__ = "mm_objectives"

    id = Column(_UUIDType, primary_key=True, default=_uuid_mod.uuid4)
    description = Column(String(4096), nullable=False, default="")
    mission_id = Column(_UUIDType, ForeignKey("mm_missions.id"), nullable=True)
    assignment_id = Column(_UUIDType, ForeignKey("mm_assignments.id"), nullable=True)


class ActivityRow(Base):
    __tablename__ = "mm_activities"

    id = Column(_UUIDType, primary_key=True, default=_uuid_mod.uuid4)
    title = Column(String(255), nullable=False)
    description = Column(String(4096), nullable=False, default="")
    status = Column(String(20), nullable=False, default="UNASSIGNED")
    objective_id = Column(_UUIDType, ForeignKey("mm_objectives.id"), nullable=False)
    assignees = Column(JSON, nullable=False, default=list)
    badge_award_id = Column(_UUIDType, ForeignKey("mm_badge_awards.id"), nullable=True)

    badge_award = relationship("BadgeAwardRow", foreign_keys=[badge_award_id], lazy="joined", uselist=False)


class AssignmentRow(Base):
    __tablename__ = "mm_assignments"

    id = Column(_UUIDType, primary_key=True, default=_uuid_mod.uuid4)
    mission_id = Column(_UUIDType, ForeignKey("mm_missions.id"), nullable=False)
    status = Column(String(20), nullable=False, default="UNASSIGNED")
    assignee_type = Column(String(20), nullable=True)
    assignee_id = Column(_UUIDType, nullable=True)
    badge_award_id = Column(_UUIDType, ForeignKey("mm_badge_awards.id"), nullable=True)

    badge_award = relationship("BadgeAwardRow", foreign_keys=[badge_award_id], lazy="joined", uselist=False)


class CredentialRow(Base):
    """Hash bcrypt della password locale per un Person (backend 'local')."""

    __tablename__ = "mm_credentials"

    person_id = Column(_UUIDType, ForeignKey("mm_persons.id"), primary_key=True)
    hashed_password = Column(String(128), nullable=False)
    # Hardening login: tentativi falliti consecutivi e istante di sblocco del
    # blocco temporaneo (None = non bloccato). must_change_password forza il
    # cambio password al primo accesso (default per le password impostate da un
    # amministratore per conto di un altro operatore).
    failed_attempts = Column(Integer, nullable=False, default=0)
    locked_until = Column(DateTime(timezone=True), nullable=True)
    must_change_password = Column(Boolean, nullable=False, default=False)
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    changed_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


class OutboxEventRow(Base):
    """Evento di dominio persistito nella stessa transazione del caso d'uso."""

    __tablename__ = "mm_outbox_events"

    id = Column(_UUIDType, primary_key=True, default=_uuid_mod.uuid4)
    event_type = Column(String(128), nullable=False)
    payload = Column(JSON, nullable=False)
    occurred_at = Column(DateTime(timezone=True), nullable=False)


class OutboxDeliveryRow(Base):
    """Consegna idempotente di un evento a uno specifico consumer."""

    __tablename__ = "mm_outbox_deliveries"
    __table_args__ = (
        UniqueConstraint("event_id", "consumer", name="uq_mm_outbox_delivery"),
    )

    id = Column(_UUIDType, primary_key=True, default=_uuid_mod.uuid4)
    event_id = Column(_UUIDType, ForeignKey("mm_outbox_events.id"), nullable=False)
    consumer = Column(String(64), nullable=False)
    delivered_at = Column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )


class AclEntryRow(Base):
    """AclEntry del sistema ACL (DESIGN §10): l'unità atomica di autorizzazione.

    Soggetto (USER|PUBLIC), risorsa (tipo + id: UUID concreto, ``*`` per la
    radice di tipo, ``global`` per SYSTEM), operazione governata, permesso
    (ALLOW|DENY), criteri di profilo (livello e/o gruppo — almeno uno, INV-1)
    e operatori di combinazione ``profile_join``/``subject_join``.
    """

    __tablename__ = "mm_acl_entries"

    id = Column(_UUIDType, primary_key=True, default=_uuid_mod.uuid4)
    subject_type = Column(String(16), nullable=False)
    subject_id = Column(String(64), nullable=True)
    resource_type = Column(String(32), nullable=False, index=True)
    resource_id = Column(String(64), nullable=False, index=True)
    operation = Column(String(32), nullable=False)
    permission = Column(String(8), nullable=False)
    level = Column(Integer, nullable=True)
    group = Column(String(255), nullable=True)
    profile_join = Column(String(3), nullable=False, default="OR")
    subject_join = Column(String(3), nullable=False, default="AND")


class SystemStateRow(Base):
    """Flag/claim persistenti per operazioni di bootstrap atomiche."""

    __tablename__ = "mm_system_state"

    key = Column(String(64), primary_key=True)
    value = Column(String(255), nullable=False)


class ExternalIdentityRow(Base):
    """Mappa un ID opaco del provider a un UUID interno del dominio."""

    __tablename__ = "mm_external_identities"
    __table_args__ = (
        UniqueConstraint(
            "provider", "resource_type", "external_id", name="uq_mm_external_identity"
        ),
        UniqueConstraint(
            "provider", "resource_type", "internal_id", name="uq_mm_internal_identity"
        ),
    )

    id = Column(_UUIDType, primary_key=True, default=_uuid_mod.uuid4)
    provider = Column(String(64), nullable=False)
    resource_type = Column(String(32), nullable=False)
    external_id = Column(String(255), nullable=False)
    internal_id = Column(_UUIDType, nullable=False)
