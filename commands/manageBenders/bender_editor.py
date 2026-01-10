"""Bender CRUD operations for Manage Benders command.

This module handles create, read, update, delete operations for
benders and dies, following SRP by separating from UI logic.
"""

from __future__ import annotations

from dataclasses import dataclass

import adsk.core

from ...storage import ProfileManager
from .input_handler import BenderFormData, DieFormData


@dataclass(slots=True)
class OperationResult:
    """Result of a CRUD operation."""

    success: bool
    message: str


class BenderEditor:
    """Handle CRUD operations for benders and dies.

    Responsible for:
    - Adding, editing, deleting benders
    - Adding, editing, deleting dies
    - Validation and user confirmation
    """

    def __init__(
        self,
        profile_manager: ProfileManager,
        ui: adsk.core.UserInterface,
    ) -> None:
        """
        Initialize the editor.

        Args:
            profile_manager: Profile manager for persistence
            ui: UI interface for message boxes
        """
        self._profile_manager = profile_manager
        self._ui = ui

    def add_bender(self, data: BenderFormData) -> OperationResult:
        """
        Add a new bender.

        Args:
            data: Bender form data

        Returns:
            OperationResult with success status and message
        """
        if not data.name:
            return OperationResult(False, "Please enter a bender name.")

        self._profile_manager.add_bender(data.name, data.min_grip, data.notes)
        return OperationResult(True, f'Bender "{data.name}" added.')

    def edit_bender(
        self,
        selected_name: str | None,
        data: BenderFormData,
    ) -> OperationResult:
        """
        Edit an existing bender.

        Args:
            selected_name: Currently selected bender name
            data: Updated bender form data

        Returns:
            OperationResult with success status and message
        """
        if not selected_name:
            return OperationResult(False, "No bender selected.")

        bender = self._profile_manager.get_bender_by_name(selected_name)
        if not bender:
            return OperationResult(False, f'Bender "{selected_name}" not found.')

        self._profile_manager.update_bender(
            bender.id, data.name, data.min_grip, data.notes
        )
        return OperationResult(True, f'Bender "{data.name}" updated.')

    def delete_bender(self, selected_name: str | None) -> OperationResult:
        """
        Delete a bender after confirmation.

        Args:
            selected_name: Bender name to delete

        Returns:
            OperationResult with success status and message
        """
        if not selected_name:
            return OperationResult(False, "No bender selected.")

        # Confirm deletion
        result = self._ui.messageBox(
            f'Delete bender "{selected_name}" and all its dies?',
            "Confirm Delete",
            adsk.core.MessageBoxButtonTypes.YesNoButtonType,
        )

        if result != adsk.core.DialogResults.DialogYes:
            return OperationResult(False, "Delete cancelled.")

        bender = self._profile_manager.get_bender_by_name(selected_name)
        if not bender:
            return OperationResult(False, f'Bender "{selected_name}" not found.')

        self._profile_manager.delete_bender(bender.id)
        return OperationResult(True, f'Bender "{selected_name}" deleted.')

    def add_die(
        self,
        selected_bender_name: str | None,
        data: DieFormData,
    ) -> OperationResult:
        """
        Add a new die to a bender.

        Args:
            selected_bender_name: Bender to add die to
            data: Die form data

        Returns:
            OperationResult with success status and message
        """
        if not selected_bender_name:
            return OperationResult(False, "No bender selected.")

        if not data.name:
            return OperationResult(False, "Please enter a die name.")

        bender = self._profile_manager.get_bender_by_name(selected_bender_name)
        if not bender:
            return OperationResult(False, f'Bender "{selected_bender_name}" not found.')

        self._profile_manager.add_die_to_bender(
            bender.id, data.name, data.tube_od, data.clr, data.offset, data.min_tail, data.notes
        )
        return OperationResult(True, f'Die "{data.name}" added to {bender.name}.')

    def edit_die(
        self,
        selected_bender_name: str | None,
        selected_die_name: str | None,
        data: DieFormData,
    ) -> OperationResult:
        """
        Edit an existing die.

        Args:
            selected_bender_name: Bender containing the die
            selected_die_name: Die to edit
            data: Updated die form data

        Returns:
            OperationResult with success status and message
        """
        if not selected_bender_name or not selected_die_name:
            return OperationResult(False, "No die selected.")

        bender = self._profile_manager.get_bender_by_name(selected_bender_name)
        if not bender:
            return OperationResult(False, f'Bender "{selected_bender_name}" not found.')

        for die in bender.dies:
            if die.name == selected_die_name:
                self._profile_manager.update_die(
                    bender.id,
                    die.id,
                    data.name,
                    data.tube_od,
                    data.clr,
                    data.offset,
                    data.min_tail,
                    data.notes,
                )
                return OperationResult(True, f'Die "{data.name}" updated.')

        return OperationResult(False, f'Die "{selected_die_name}" not found.')

    def delete_die(
        self,
        selected_bender_name: str | None,
        selected_die_name: str | None,
    ) -> OperationResult:
        """
        Delete a die after confirmation.

        Args:
            selected_bender_name: Bender containing the die
            selected_die_name: Die to delete

        Returns:
            OperationResult with success status and message
        """
        if not selected_bender_name or not selected_die_name:
            return OperationResult(False, "No die selected.")

        # Confirm deletion
        result = self._ui.messageBox(
            f'Delete die "{selected_die_name}"?',
            "Confirm Delete",
            adsk.core.MessageBoxButtonTypes.YesNoButtonType,
        )

        if result != adsk.core.DialogResults.DialogYes:
            return OperationResult(False, "Delete cancelled.")

        bender = self._profile_manager.get_bender_by_name(selected_bender_name)
        if not bender:
            return OperationResult(False, f'Bender "{selected_bender_name}" not found.')

        for die in bender.dies:
            if die.name == selected_die_name:
                self._profile_manager.delete_die(bender.id, die.id)
                return OperationResult(True, f'Die "{selected_die_name}" deleted.')

        return OperationResult(False, f'Die "{selected_die_name}" not found.')
