"""Shared matplotlib style for the paper's figures.

Colours mirror the palette defined in the paper preamble (acl_latex.tex), so a
figure and the tables around it read as one visual system.
"""

from __future__ import annotations

import pathlib

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

ACC = "#1F4E79"       # agent, primary accent
ACC_SOFT = "#E8EEF5"
HUM = "#7A4E00"       # human stage
HUM_SOFT = "#F6EEDD"
RUN = "#2E6B3A"       # deterministic test runner, accepted
RUN_SOFT = "#E5F0E6"
WARN = "#A4471C"      # candidate, unsupported, growth
WARN_SOFT = "#F8E6DC"
RULE = "#9AA5B1"      # axes, frames, baselines
GREY = "#6B7785"
ZEBRA = "#F4F6F8"

COLUMN_IN = 3.03      # ACL single column width in inches
TEXT_IN = 6.30        # ACL full text width in inches


def apply() -> None:
    """Set rcParams for an ACL two-column paper (Times-like, 7-8 pt)."""
    matplotlib.rcParams.update({
        "font.family": "serif",
        # Liberation Serif is a TrueType, metric-compatible Times clone, so fonttype 42
        # embeds it cleanly; OpenType-CFF fonts like Nimbus Roman do not embed as Type 42.
        "font.serif": ["Liberation Serif", "Times New Roman", "DejaVu Serif"],
        "mathtext.fontset": "stix",
        "font.size": 7.5,
        "axes.titlesize": 7.5,
        "axes.labelsize": 7.5,
        "xtick.labelsize": 6.5,
        "ytick.labelsize": 6.5,
        "legend.fontsize": 6.5,
        "axes.edgecolor": RULE,
        "axes.linewidth": 0.6,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "xtick.color": GREY,
        "ytick.color": GREY,
        "xtick.major.width": 0.6,
        "ytick.major.width": 0.6,
        "axes.labelcolor": "#222222",
        "grid.color": "#E3E7EB",
        "grid.linewidth": 0.5,
        "legend.frameon": False,
        "pdf.fonttype": 42,
        "savefig.bbox": "tight",
        "savefig.pad_inches": 0.02,
    })


def save(fig, name: str) -> pathlib.Path:
    """Write out/analysis/<name>.pdf deterministically and copy it into paper/."""
    out = pathlib.Path("out/analysis") / f"{name}.pdf"
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, format="pdf", metadata={"CreationDate": None})
    paper = pathlib.Path("paper")
    if paper.is_dir():
        (paper / out.name).write_bytes(out.read_bytes())
    plt.close(fig)
    return out
