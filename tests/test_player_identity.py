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
    # The alias target is normalized like every other canonical name.
    assert canonical_name_for("Cam Skattebo", aliases=aliases) == "cameron skattebo"


def test_aliased_and_directly_spelled_names_share_one_canonical_name():
    # Regression: the alias table's canonical_name column is title-cased
    # ("Cameron Skattebo"), and it used to be returned verbatim, while a source
    # that already spells the full name took the normalized path and got
    # "cameron skattebo". One player then had two canonical_names, so the site
    # (which groups by canonical_name) listed them twice -- confirmed live
    # 2026-09-19 for Cam Ward, Cam Skattebo and Kenny Gainwell.
    aliases = {"cam skattebo": "Cameron Skattebo"}
    assert canonical_name_for("Cam Skattebo", aliases=aliases) == canonical_name_for("Cameron Skattebo", aliases=aliases)
    assert canonical_name_for("Cam Skattebo", aliases=aliases) == canonical_name_for("Cameron Skattebo", aliases={})


def test_alias_targets_with_suffixes_and_punctuation_are_normalized():
    aliases = {"ken walker": "Kenneth Walker III", "deebo samuel": "Deebo Samuel Sr."}
    assert canonical_name_for("Ken Walker III", aliases=aliases) == canonical_name_for("Kenneth Walker III", aliases={})
    assert canonical_name_for("Deebo Samuel", aliases=aliases) == "deebo samuel"


def test_canonical_name_for_falls_back_to_normalized_name_when_no_alias():
    assert canonical_name_for("Some Rookie", aliases={}) == "some rookie"


def test_load_aliases_reads_the_real_draft_aliases_file():
    # Regression test for the exact players Jared flagged as historically
    # falling through name matching -- confirms this file's real content
    # resolves them once matching ignores source/team (see plan header).
    aliases = load_aliases()
    assert aliases["cam skattebo"] == "Cameron Skattebo"
    assert aliases["kenny gainwell"] == "Kenneth Gainwell"


def test_every_real_alias_resolves_to_the_same_name_as_its_canonical_spelling():
    # For every row in the real aliases file, the short/nickname spelling and
    # the canonical spelling must produce the identical canonical_name, or that
    # player splits into two rows whenever two sources spell them differently.
    import csv
    from src.player_identity import ALIASES_PATH

    aliases = load_aliases()
    with ALIASES_PATH.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            assert canonical_name_for(row["raw_name"], aliases=aliases) == canonical_name_for(
                row["canonical_name"], aliases={}
            ), row
