from ohol_bot.family import FamilyCoordinator, FamilyRole


def test_family_coordinator_assigns_core_roles() -> None:
    coordinator = FamilyCoordinator()

    assignments = coordinator.assign_roles([1, 2, 3])

    assert [assignment.role for assignment in assignments] == [
        FamilyRole.MOTHER,
        FamilyRole.CARETAKER,
        FamilyRole.FARMER,
    ]
    assert coordinator.family_metrics()["assigned_bot_count"] == 3.0
