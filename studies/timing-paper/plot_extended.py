"""Plot verified completions through twelve minutes for each chat schedule."""
import argparse
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from plot_long import SETTINGS
from run_extended import CHECKPOINTS, DURATION


def main():
    p = argparse.ArgumentParser()
    p.add_argument("results", type=Path)
    p.add_argument("output", type=Path)
    args = p.parse_args()
    rows = json.loads(args.results.read_text())["episodes"]
    fig, ax = plt.subplots(figsize=(8.1, 4.5))
    ax.set_axisbelow(True)
    for policy, (label, color, style) in SETTINGS.items():
        if policy == "two_blocks":
            label = "60 s per 3 min"
        completed = sorted(row["capped_s"] / 60 for row in rows if row["schedule"] == policy
                           and row["snapshots"][str(DURATION)]["success"])
        ax.step([0, *completed, DURATION/60], [0, *range(1, len(completed) + 1), len(completed)],
                where="post", linewidth=2.2, linestyle=style, color=color, label=label,
                zorder=3 if style == "--" else 2)
    for checkpoint in CHECKPOINTS:
        minute = checkpoint / 60
        ax.axvline(minute, linestyle=":", linewidth=1.1, color="#555555")
        ax.text(minute + 0.1, 6.12, f"{minute:.0f} min", fontsize=9, color="#555555")
    ax.set(xlim=(0, DURATION/60), ylim=(0, 6.45), xticks=range(0, 13),
           yticks=range(0, 7), xlabel="Elapsed time (min)", ylabel="Recipe sets completed (of 6)")
    ax.spines["right"].set_visible(False)
    ax.spines["top"].set_visible(False)
    ax.grid(axis="y", alpha=0.2)
    ax.legend(loc="lower center", bbox_to_anchor=(0.5, 1.02), ncol=3, frameon=False)
    fig.tight_layout()
    fig.savefig(args.output.with_suffix(".png"), dpi=220, facecolor="white")
    fig.savefig(args.output.with_suffix(".pdf"), facecolor="white")


if __name__ == "__main__":
    main()
