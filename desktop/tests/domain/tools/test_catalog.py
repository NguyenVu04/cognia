from src.domain.tools import catalog


def test_specs_have_unique_names() -> None:
    names = [s.name for s in catalog.SPECS]

    assert len(names) == len(set(names))


def test_every_schema_is_an_object_with_required() -> None:
    for spec in catalog.SPECS:
        assert spec.parameters["type"] == "object", spec.name
        required = spec.parameters["required"]
        assert set(required) <= set(spec.parameters["properties"]), spec.name


def test_every_tool_says_what_it_does() -> None:
    for spec in catalog.SPECS:
        assert spec.description and spec.working, spec.name


def test_core_tools_are_in_the_set() -> None:
    assert catalog.CORE_TOOLS <= {s.name for s in catalog.SPECS}


def test_spec_unknown() -> None:
    assert catalog.spec("music") is None
    assert catalog.spec("calculate").data
