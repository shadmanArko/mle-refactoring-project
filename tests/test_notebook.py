"""The refactored notebook must use the package, stay clean, and actually run."""

import ast
import os
from pathlib import Path

import nbformat
import pytest

ROOT = Path(__file__).resolve().parents[1]
NOTEBOOK = ROOT / "King-County-refactored.ipynb"


@pytest.fixture(scope="module")
def notebook():
    return nbformat.read(NOTEBOOK, as_version=4)


def code_of(notebook) -> list[str]:
    return [c.source for c in notebook.cells if c.cell_type == "code"]


def test_the_notebook_is_valid_and_committed_without_outputs(notebook):
    nbformat.validate(notebook)

    for cell in notebook.cells:
        if cell.cell_type == "code":
            assert cell.outputs == [], "commit notebooks without outputs"
            assert cell.execution_count is None


def test_every_code_cell_is_valid_python(notebook):
    for source in code_of(notebook):
        ast.parse(source)


def test_the_notebook_uses_the_package_instead_of_reimplementing_it(notebook):
    joined = "\n".join(code_of(notebook))

    for name in (
        "drop_implausible_rows",
        "fix_sqft_basement",
        "impute_view_and_waterfront",
        "add_last_known_change",
        "add_center_distance",
        "WaterDistance",
        "make_training_split",
        "build_model_pipeline",
    ):
        assert name in joined, f"{name} should come from kc_house"


def test_the_original_hand_written_steps_are_gone(notebook):
    joined = "\n".join(code_of(notebook))

    assert "15856" not in joined  # the hard-coded row position
    assert "def dist(" not in joined  # the inline distance helper
    assert "last_known_change = []" not in joined  # the row-by-row loop
    assert "for idx in kc_data.index" not in joined  # the slow nearest-water loop
    assert "kc_data.drop(" not in joined


def test_the_original_notebook_is_left_untouched():
    original = nbformat.read(ROOT / "King-County.ipynb", as_version=4)
    joined = "\n".join(c.source for c in original.cells if c.cell_type == "code")

    assert "kc_house" not in joined
    assert "15856" in joined


@pytest.mark.skipif(
    not os.environ.get("KC_RUN_NOTEBOOK"),
    reason="set KC_RUN_NOTEBOOK=1 to execute the notebook (about 20 seconds)",
)
def test_the_notebook_runs_end_to_end_and_reproduces_the_numbers(notebook, monkeypatch):
    from nbclient import NotebookClient

    monkeypatch.setenv("MPLBACKEND", "Agg")
    client = NotebookClient(
        notebook, timeout=600, resources={"metadata": {"path": str(ROOT)}}
    )

    client.execute()  # raises if any cell fails

    printed = "\n".join(
        output.text
        for cell in notebook.cells
        if cell.cell_type == "code"
        for output in cell.outputs
        if output.output_type == "stream"
    )
    assert "Grade only, test R²: 0.432" in printed
    assert "Notebook model, test R²: 0.8447" in printed
    assert "Test R²: 0.880" in printed
