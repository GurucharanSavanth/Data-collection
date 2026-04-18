from __future__ import annotations

import sqlite3

from constants import DIRECT_CHILD_ROLES, MANAGEABLE_ROLES, ROLE_CANDIDATE, ROLE_SUPER_ADMIN
from repositories import UserRepository


class AuthorizationService:
    def __init__(self, user_repository: UserRepository) -> None:
        self.user_repository = user_repository

    def get_authorized_subtree(self, connection: sqlite3.Connection, actor: dict[str, object]) -> list[int]:
        actor_role = str(actor["role"])
        actor_id = int(actor["user_id"])
        if actor_role == ROLE_CANDIDATE:
            return [actor_id]
        return self.user_repository.get_subtree_user_ids(connection, actor_id)

    def is_within_subtree(
        self,
        connection: sqlite3.Connection,
        actor: dict[str, object],
        target_user_id: int | None,
    ) -> bool:
        if target_user_id is None:
            return str(actor["role"]) == ROLE_SUPER_ADMIN
        return target_user_id in self.get_authorized_subtree(connection, actor)

    def can_view_user(
        self,
        connection: sqlite3.Connection,
        actor: dict[str, object],
        target: dict[str, object],
    ) -> bool:
        actor_id = int(actor["user_id"])
        target_id = int(target["user_id"])
        if actor_id == target_id:
            return True
        return self.is_within_subtree(connection, actor, target_id)

    def can_manage_user(
        self,
        connection: sqlite3.Connection,
        actor: dict[str, object],
        target: dict[str, object],
    ) -> bool:
        actor_id = int(actor["user_id"])
        target_id = int(target["user_id"])
        actor_role = str(actor["role"])
        target_role = str(target["role"])
        if actor_id == target_id:
            return False
        if target_role not in MANAGEABLE_ROLES.get(actor_role, ()):
            return False
        if actor_role == ROLE_SUPER_ADMIN:
            return True
        return self.is_within_subtree(connection, actor, target_id)

    def can_reset_credentials(
        self,
        connection: sqlite3.Connection,
        actor: dict[str, object],
        target: dict[str, object],
    ) -> bool:
        return self.can_manage_user(connection, actor, target)

    def can_map_child(
        self,
        connection: sqlite3.Connection,
        actor: dict[str, object],
        parent: dict[str, object],
        child_role: str,
    ) -> bool:
        actor_role = str(actor["role"])
        parent_role = str(parent["role"])
        if child_role not in DIRECT_CHILD_ROLES.get(parent_role, ()):
            return False
        if child_role not in MANAGEABLE_ROLES.get(actor_role, ()):
            return False
        return self.can_view_user(connection, actor, parent)

    def can_view_record(
        self,
        connection: sqlite3.Connection,
        actor: dict[str, object],
        record: dict[str, object],
    ) -> bool:
        candidate_user_id = record.get("candidate_user_id")
        if candidate_user_id is None:
            return str(actor["role"]) == ROLE_SUPER_ADMIN
        return self.is_within_subtree(connection, actor, int(candidate_user_id))

    def can_edit_record(
        self,
        connection: sqlite3.Connection,
        actor: dict[str, object],
        record: dict[str, object],
    ) -> bool:
        if not self.can_view_record(connection, actor, record):
            return False
        if str(actor["role"]) == ROLE_CANDIDATE:
            candidate_user_id = record.get("candidate_user_id")
            return candidate_user_id is not None and int(candidate_user_id) == int(actor["user_id"])
        return True

    def can_create_record(
        self,
        connection: sqlite3.Connection,
        actor: dict[str, object],
        candidate: dict[str, object] | None,
    ) -> bool:
        actor_role = str(actor["role"])
        if actor_role == ROLE_CANDIDATE:
            if candidate is None:
                return True
            return int(candidate["user_id"]) == int(actor["user_id"])
        if candidate is None:
            return actor_role == ROLE_SUPER_ADMIN
        return self.is_within_subtree(connection, actor, int(candidate["user_id"]))

    def can_view_subtree(
        self,
        connection: sqlite3.Connection,
        actor: dict[str, object],
        node: dict[str, object],
    ) -> bool:
        return self.can_view_user(connection, actor, node)
