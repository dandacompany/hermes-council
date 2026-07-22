import pathlib, re
import council

SK = pathlib.Path(list(council.__path__)[0]) / "skills" / "council" / "SKILL.md"


def test_skill_frontmatter_and_content():
    text = SK.read_text(encoding="utf-8")
    assert text.startswith("---")
    fm = text.split("---", 2)[1]
    assert re.search(r"^name:\s*council\s*$", fm, re.M)
    desc = re.search(r"^description:\s*(.+)$", fm, re.M).group(1).strip()
    assert not desc.startswith("[") and "<" not in desc and ">" not in desc  # plain one-line
    for kw in ["council_start", "council_status", "council_collect", "sequential", "parallel"]:
        assert kw in text
