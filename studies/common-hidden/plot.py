"""Plot the matched common-goal and hidden-recipe results."""
import argparse
import json
from pathlib import Path
from statistics import mean

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D

SCHEDULES = ("always", "blocks", "alternating")
LABELS = ("Always open", "Two windows", "20 s on / 40 s off")
COLORS = ("#566577", "#a94d35", "#117583")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("results", type=Path)
    ap.add_argument("prefix", type=Path)
    args = ap.parse_args()
    report = json.loads(args.results.read_text())
    if report["pending"]:
        raise ValueError("Plot requires the full scored cohort")
    fig, axes = plt.subplots(1, 3, figsize=(12, 4.7))
    for ax, (mode, title) in zip(axes[:2], (("public", "Common goals with full cards"),
                                           ("split", "Common goals with split cards"))):
        for i, (schedule, color) in enumerate(zip(SCHEDULES, COLORS)):
            values = [r["goals"] for r in report["trials"] if r["mode"] == mode and r["schedule"] == schedule]
            jitter = [(j - (len(values) - 1) / 2) * 0.045 for j in range(len(values))]
            ax.scatter(values, [i + j for j in jitter], color=color, alpha=0.45, s=23)
            ax.scatter(mean(values), i, color=color, marker="D", edgecolors="white", linewidths=1.1, s=72)
        ax.set_xlim(-0.3, 8.4)
        ax.set_xticks([0, 2, 4, 6, 8])
        ax.set_xlabel("Unique goals verified (of 8)")
        ax.set_title(title, loc="left", fontsize=10, weight="bold")
        ax.set_yticks(range(3), labels=LABELS)
        ax.set_ylim(2.43, -0.43)
    ax = axes[2]
    for i, (schedule, color) in enumerate(zip(SCHEDULES, COLORS)):
        row = report["groups"][f"hidden-{schedule}"]
        ax.barh(i + 0.13, row["mean_hidden_discoveries"], height=0.23, color=color, alpha=0.45)
        ax.barh(i - 0.13, row["mean_hidden_goals"], height=0.23, color=color)
    ax.set_xlim(0, 12.2)
    ax.set_xticks([0, 3, 6, 9, 12])
    ax.set_xlabel("Mean hidden recipes (of 12)")
    ax.set_title("Hidden recipe search and crafting", loc="left", fontsize=10, weight="bold")
    ax.set_yticks(range(3), labels=LABELS)
    ax.set_ylim(2.43, -0.43)
    for ax in axes:
        ax.grid(axis="x", color="#e2e7eb")
        ax.set_axisbelow(True)
        ax.spines[["top", "right", "left"]].set_visible(False)
        ax.spines["bottom"].set_color("#aeb7bf")
        ax.tick_params(axis="both", length=0, labelsize=8.7)
    fig.subplots_adjust(top=0.75, bottom=0.23, left=0.126, right=0.98, wspace=0.54)
    fig.text(0.126, 0.915, "What chat helped Minecraft teams complete", fontsize=19, weight="bold")
    fig.text(0.126, 0.846, "Six minutes per trial · Two GPT-6 Luna bots · Ten matched trials per cell",
             fontsize=10.5, color="#42566b")
    keys = [
        Line2D([], [], color="#273949", marker="o", linestyle="none", alpha=0.45, label="Individual trials"),
        Line2D([], [], color="#273949", marker="D", linestyle="none", label="Cell mean"),
        Line2D([], [], color="#273949", linewidth=7, alpha=0.45, label="Distinct clues found"),
        Line2D([], [], color="#273949", linewidth=7, label="Hidden recipes crafted"),
    ]
    fig.legend(handles=keys, loc="lower left", ncols=4, fontsize=9, frameon=False,
               bbox_to_anchor=(0.118, 0.060))
    for suffix in ("png", "pdf"):
        fig.savefig(args.prefix.with_suffix("." + suffix), dpi=190)


if __name__ == "__main__":
    main()
