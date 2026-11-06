from core import extract_json_text, load_schema, validate

GOOD = '{"intent": "alarm_set", "date": "tomorrow", "time": "seven am", "place": null}'


def test_validate_accepts_four_key_frame():
    assert validate(GOOD) == {"intent": "alarm_set", "date": "tomorrow", "time": "seven am", "place": None}


def test_validate_rejects_bad_outputs():
    assert validate("not json") is None
    assert validate('{"intent": "alarm_set", "date": null, "time": null}') is None  # missing key
    assert validate('{"intent": "alarm_set", "date": null, "time": null, "place": null, "x": 1}') is None
    assert validate('{"intent": "play_music", "date": null, "time": null, "place": null}') is None
    assert validate('{"intent": "alarm_set", "date": 7, "time": null, "place": null}') is None
    assert validate("[1, 2]") is None


def test_extract_cuts_after_first_object():
    assert extract_json_text(" " + GOOD + ' {"intent"') == GOOD
    assert extract_json_text(GOOD + "\nCommand: next") == GOOD
    assert extract_json_text('{"intent": "a}b"} tail') == '{"intent": "a}b"}'


def test_schema_file_matches_spec():
    keys, intents = load_schema("data/schema.json")
    assert keys == ["intent", "date", "time", "place"]
    assert len(intents) == 8


def test_salvage_uses_first_values_and_never_invents():
    from core import parse_output
    raw = '{"intent": "recommendation_events", "date": null, "time": null, "place": "los angeles", "place": "x"'
    frame, how = parse_output(raw, "events in los angeles")
    assert how == "salvaged" and frame["place"] == "los angeles"
    frame, how = parse_output('{"intent": "alarm_set", "date": "monday"}', "wake me at six")
    assert how == "salvaged" and frame == {"intent": "alarm_set", "date": None, "time": None, "place": None}
    assert parse_output("not json", "anything") == (None, "invalid")
    assert parse_output('{"intent": "play_music"}', "x") == (None, "invalid")
