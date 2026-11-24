"""Render episode outcomes without aggregating away the matched blocks."""
import argparse
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D

COLORS = {"bakery": "#0072B2", "harvest": "#D55E00", "dyes": "#009E73"}


def panel(ax, rows, category, order, labels):
    blocks = sorted({r["block"] for r in rows})
    for block in blocks:
        by_category = {r[category]: r for r in rows if r["block"] == block}
        if any(x not in by_category for x in order):
            continue
        points = [by_category[x] for x in order]
        values = [r["capped_completion_s"] for r in points]
        color = COLORS[points[0]["scenario"]]
        line = "-" if points[0]["mirror"] == 1 else "--"
        offset = {"bakery": -0.085, "harvest": 0, "dyes": 0.085}[points[0]["scenario"]]
        offset += points[0]["mirror"] * 0.023
        xx = [i + offset for i in range(len(order))]
        ax.plot(xx, values, color=color, linestyle=line, alpha=0.72, linewidth=1.3)
        for i, row in enumerate(points):
            ax.scatter(xx[i], values[i], facecolors=color if row["success"] else "white",
                       edgecolors=color, linewidths=1.3, zorder=3, s=38)
    ax.axhline(180, color="#666666", linewidth=0.7, linestyle=":")
    ax.set_xticks(range(len(order)))
    ax.set_xticklabels(labels)
    ax.set_xlim(-0.36, len(order) - 0.64)
    ax.set_yticks([0, 45, 90, 135, 180])
    ax.set_ylim(-3, 188)
    ax.grid(axis="y", alpha=0.18)
    ax.spines["right"].set_visible(False)
    ax.spines["top"].set_visible(False)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("onset", type=Path)
    parser.add_argument("phases", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    onset = json.loads(args.onset.read_text())["episodes"]
    phases = json.loads(args.phases.read_text())["episodes"]
    fig, axes = plt.subplots(1, 3, figsize=(10.2, 3.65), sharey=True)
    for ax, info, title in zip(axes, ("known", "partner"), ("A  Own goals known", "B  Partner holds goal card")):
        panel(ax, [r for r in onset if r["information"] == info], "delay_s",
              (0, 45), ("Immediate", "45 s delay"))
        ax.set_title(title, loc="left", fontsize=11, weight="bold")
    panel(axes[2], phases, "schedule", ("always", "upfront", "alternating"),
          ("Always\nopen", "60 s\nup front", "20/40 s\ncycles"))
    axes[2].set_title("C  Six objectives", loc="left", fontsize=11, weight="bold")
    axes[0].set_ylabel("Capped time to all objectives (s)")
    handles = [Line2D([], [], color=color, label=scenario.title(), linewidth=1.8)
               for scenario, color in COLORS.items()]
    handles += [
        Line2D([], [], marker="o", linestyle="", color="#444444", label="Complete", markersize=6),
        Line2D([], [], marker="o", linestyle="", color="#444444", markerfacecolor="white",
               label="Incomplete", markersize=6)
    ]
    fig.legend(handles=handles, loc="lower center", ncol=5, frameon=False, fontsize=9)
    fig.subplots_adjust(left=0.085, right=0.985, top=0.88, bottom=0.28, wspace=0.24)
    fig.savefig(args.output.with_suffix(".png"), dpi=240, facecolor="white")
    fig.savefig(args.output.with_suffix(".pdf"), facecolor="white")


if __name__ == "__main__":
    main()
