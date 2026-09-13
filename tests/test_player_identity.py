from src.player_identity import canonical_name_for, load_aliases, normalize_name


def test_normalize_name_lowercases_strips_punctuation_and_hyphens():
    assert normalize_name("D.K. Metcalf") == "dk metcalf"
    assert normalize_name("Cam Skattebo") == "cam skattebo"
    assert normalize_name("Ray-Ray McCloud") == "ray ray mccloud"


def test_normalize_name_drops_generational_suffix():
    assert normalize_name("Michael Pittman Jr.") == "michael pittman"
    assert normalize_name("Kenneth Walker III") == "kenneth walker"


def test_canonical_name_for_uses_provided_alias_table():
    aliases = {"cam skattebo": "Cameron Skattebo"}
    assert canonical_name_for("Cam Skattebo", aliases=aliases) == "Cameron Skattebo"


def test_canonical_name_for_falls_back_to_normalized_name_when_no_alias():
    assert canonical_name_for("Some Rookie", aliases={}) == "some rookie"


def test_load_aliases_reads_the_real_draft_aliases_file():
    # Regression test for the exact players Jared flagged as historically
    # falling through name matching -- confirms this file's real content
    # resolves them once matching ignores source/team (see plan header).
    aliases = load_aliases()
    assert aliases["cam skattebo"] == "Cameron Skattebo"
    assert aliases["kenny gainwell"] == "Kenneth Gainwell"
