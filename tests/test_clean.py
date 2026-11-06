import json

from clean import clean


def rec(i, text, raw):
    return {"id": f"C{i:04d}", "text": text, "teacher_raw": raw}


def frame(intent="weather_query", date=None, time=None, place=None):
    return json.dumps({"intent": intent, "date": date, "time": time, "place": place})


def test_each_rejection_reason_and_counts_add_up():
    records = [
        rec(1, "weather in london", frame(place="london")),
        rec(2, "weather in paris", "```json {bad"),                                  # (a)
        rec(3, "weather in rome", '{"intent": "weather_query", "place": "rome"}'),  # (b)
        rec(4, "weather in oslo", frame(intent="music_play")),                       # (c)
        rec(5, "weather in kyiv", frame(place="moscow")),                           # (d)
        rec(6, "Weather in  London", frame(place="london")),                         # (e) duplicate of C0001
        rec(7, "alarm at seven am", frame("alarm_set", time="seven am")),
    ]
    kept, c = clean(records)
    assert [r["id"] for r in kept] == ["C0001", "C0007"]
    assert (c["a_invalid_json"], c["b_wrong_keys"], c["c_bad_intent"], c["d_slot_not_in_command"], c["e_duplicates"]) == (1, 1, 1, 1, 1)
    assert c["input"] == sum(v for k, v in c.items() if k != "input")


def test_output_is_in_id_order_and_keeps_raw_reply():
    raw = '{"intent":"alarm_set","date":null,"time":"six am","place":null}'
    kept, _ = clean([rec(10, "alarm six am", raw), rec(2, "weather in london", frame(place="london"))])
    assert [r["id"] for r in kept] == ["C0002", "C0010"]
    assert kept[1]["teacher_raw"] == raw
    assert json.loads(kept[1]["target"])["time"] == "six am"


def test_duplicate_keeps_smallest_id():
    kept, c = clean([rec(9, "weather in london", frame(place="london")),
                     rec(3, "weather in london", frame(place="london"))])
    assert [r["id"] for r in kept] == ["C0003"] and c["e_duplicates"] == 1
