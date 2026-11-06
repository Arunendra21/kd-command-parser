import json

from worker import shard_lines


def test_shards_cover_every_line_exactly_once():
    lines = [json.dumps({"id": f"C{i:04d}"}) for i in range(3000)]
    for count in (2, 3, 4):
        shards = [shard_lines(lines, i, count) for i in range(count)]
        ids = [json.loads(l)["id"] for s in shards for l in s]
        assert sorted(ids) == sorted(json.loads(l)["id"] for l in lines)
        assert len(ids) == len(set(ids))


def test_shard_rule_is_line_number_mod_count():
    lines = [str(i) for i in range(10)]
    assert shard_lines(lines, 1, 3) == ["1", "4", "7"]
