"""Plot the cumulative completion curves for the two handoff conditions."""

import argparse
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("results", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    report = json.loads(args.results.read_text())
    deadline = report["manifest"]["deadline_seconds"]
    styles = (
        ("baseline", "No note", "#0072B2", "--", 3),
        ("learned", "Frozen practice note", "#009E73", "-", 2),
    )
    fig, ax = plt.subplots(figsize=(7.2, 4.2))
    for arm, label, color, style, layer in styles:
        finished = report["arms"][arm]["completion_times_s"]
        ax.step([0, *finished, deadline], [0, *range(1, len(finished) + 1), len(finished)],
                where="post", label=label, color=color, linestyle=style, linewidth=2.2, zorder=layer)
    total = report["arms"]["baseline"]["n"]
    ax.set(xlim=(0, deadline), ylim=(0, total + 0.5), xticks=range(0, deadline + 1, 30),
           yticks=range(0, total + 1, 3), xlabel="Elapsed time (s)",
           ylabel=f"Trials completed (of {total} per condition)")
    ax.set_axisbelow(True)
    ax.grid(axis="y", alpha=0.22)
    ax.spines["right"].set_visible(False)
    ax.spines["top"].set_visible(False)
    ax.legend(loc="lower center", bbox_to_anchor=(0.5, 1.01), ncol=2, frameon=False)
    fig.tight_layout()
    fig.savefig(args.output.with_suffix(".png"), dpi=220)
    fig.savefig(args.output.with_suffix(".pdf"))


if __name__ == "__main__":
    main()
