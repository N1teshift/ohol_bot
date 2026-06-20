from ohol_bot.biomes import BiomeCatalog
from ohol_bot.game_data import OholGameData, OholObject
from ohol_bot.model import PlayerState, Tile
from ohol_bot.relationships import relation_name


def _game_data() -> OholGameData:
    return OholGameData(
        objects={
            100: OholObject(100, "Man", male=True),
            101: OholObject(101, "Woman", male=False),
        },
        transitions=(),
        biomes=BiomeCatalog(names={0: "Grasslands"}),
    )


def _player(
    player_id: int,
    *,
    ancestor_ids: tuple[int, ...] = (),
    lineage_id: int | None = None,
    age: float = 20.0,
    display_id: int = 101,
) -> PlayerState:
    return PlayerState(
        player_id=player_id,
        tile=Tile(0, 0),
        age=age,
        food_store=20,
        max_food_store=20,
        ancestor_ids=ancestor_ids,
        lineage_id=lineage_id,
        display_id=display_id,
    )


def test_relation_mother() -> None:
    game_data = _game_data()
    self_player = _player(14, ancestor_ids=(13,), lineage_id=13)
    mother = _player(13, ancestor_ids=(), lineage_id=13, display_id=101)

    assert relation_name(self_player, mother, game_data=game_data) == "your mother"


def test_relation_sister() -> None:
    game_data = _game_data()
    self_player = _player(14, ancestor_ids=(50,), lineage_id=50, age=25.0)
    sister = _player(15, ancestor_ids=(50,), lineage_id=50, age=20.0, display_id=101)

    assert relation_name(self_player, sister, game_data=game_data) == "your little sister"


def test_relation_brother() -> None:
    game_data = _game_data()
    self_player = _player(14, ancestor_ids=(50,), lineage_id=50, age=25.0)
    brother = _player(16, ancestor_ids=(50,), lineage_id=50, age=20.0, display_id=100)

    assert relation_name(self_player, brother, game_data=game_data) == "your little brother"


def test_relation_niece() -> None:
    game_data = _game_data()
    self_player = _player(10, ancestor_ids=(5,), lineage_id=5)
    niece = _player(11, ancestor_ids=(8, 5), lineage_id=5, display_id=101)

    assert relation_name(self_player, niece, game_data=game_data) == "your niece"


def test_relation_grandmother() -> None:
    game_data = _game_data()
    self_player = _player(20, ancestor_ids=(5, 3), lineage_id=3)
    grandmother = _player(3, ancestor_ids=(), lineage_id=3, display_id=101)

    assert relation_name(self_player, grandmother, game_data=game_data) == "your grandmother"


def test_relation_distant_relative_same_eve() -> None:
    game_data = _game_data()
    self_player = _player(10, ancestor_ids=(99,), lineage_id=5)
    other = _player(11, ancestor_ids=(88,), lineage_id=5)

    assert relation_name(self_player, other, game_data=game_data) == "your distant relative"


def test_relation_unrelated() -> None:
    game_data = _game_data()
    self_player = _player(10, ancestor_ids=(99,), lineage_id=5)
    other = _player(11, ancestor_ids=(88,), lineage_id=6)

    assert relation_name(self_player, other, game_data=game_data) is None
