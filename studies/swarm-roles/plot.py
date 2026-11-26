"""Plot matched recipe completion times and duplicate crafts by role design."""
import argparse
import json
from pathlib import Path
from statistics import mean

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

MODES = ("swarm", "fixed", "orchestrator")
NAMES = ("Swarm", "Fixed roles", "Orchestrator")
COLORS = ("#586477", "#117687", "#a54c31")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("results", type=Path)
    parser.add_argument("prefix", type=Path)
    args = parser.parse_args()
    report = json.loads(args.results.read_text())
    if report["pending"]:
        raise ValueError("Plot requires all matched trials")
    values = {(row["mode"], row["seed"]): row for row in report["trials"]}
    seeds = sorted({row["seed"] for row in report["trials"]})
    fig, (left, right) = plt.subplots(1, 2, figsize=(9.5, 4.6))
    for ax, key, title, axis in (
        (left, "elapsed", "Time to finish the recipe set", "Elapsed seconds"),
        (right, "duplicate_crafts", "Extra crafted copies", "Duplicate crafts per trial"),
    ):
        for seed in seeds:
            ys = [values[(mode, seed)][key] for mode in MODES]
            ax.plot(range(3), ys, color="#9baab2", alpha=0.46, linewidth=0.8, zorder=1)
        for i, (color, mode) in enumerate(zip(COLORS, MODES)):
            ys = [values[(mode, seed)][key] for seed in seeds]
            ax.scatter([i] * len(ys), ys, s=22, alpha=0.47, color=color, zorder=2)
            ax.scatter(i, mean(ys), marker="D", s=65, color=color, edgecolors="white", linewidths=0.9, zorder=3)
        ax.set_title(title, loc="left", fontsize=11.5, weight="bold")
        ax.set_ylabel(axis)
        ax.set_xticks(range(3), NAMES)
        ax.set_xlim(-0.35, 2.35)
        ax.set_ylim(bottom=0)
        ax.grid(axis="y", color="#e1e7ec")
        ax.set_axisbelow(True)
        ax.spines[["top", "right"]].set_visible(False)
    fig.subplots_adjust(top=0.76, bottom=0.18, left=0.09, right=0.97, wspace=0.34)
    fig.text(0.09, 0.92, "Do recipe assignments help four Minecraft cooks?", fontsize=18, weight="bold")
    fig.text(0.09, 0.858, "Eight shared recipes · Four GPT-6 Luna bots · Ten matched trials per condition",
             fontsize=10.5, color="#435566")
    fig.text(0.09, 0.065, "Lines connect matched trials and diamonds show means. Unfinished trials use 360 seconds.",
             fontsize=9, color="#435566")
    for kind in ("png", "pdf"):
        fig.savefig(args.prefix.with_suffix("." + kind), dpi=195)


if __name__ == "__main__":
    main()
