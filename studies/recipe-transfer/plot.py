"""Plot student delivery and timing contrasts against independent discovery."""
import argparse
import json
from pathlib import Path

import matplotlib.pyplot as plt


def render(results, stem):
    fig, (left, right) = plt.subplots(1, 2, figsize=(10.6, 4.5), layout="constrained")
    groups = results["groups"]
    rows = (("reuse_solo", "reuse_cards"), ("novel_solo", "novel_playbook"))
    for offset, index, color, label in ((-.13, 0, "#576171", "Independent discovery"),
                                       (.13, 1, "#05766d", "Teacher material")):
        series = [groups[row[index]]["mean_orders"] for row in rows]
        bars = left.bar([offset, 1 + offset], series, width=.235, color=color, label=label)
        left.bar_label(bars, labels=[f"{value:g}" for value in series], padding=3, fontsize=9)
    left.set(xticks=[0, 1], xticklabels=["Reused recipes\nCards vs. independent", "Held-out recipes\nPlaybook vs. independent"],
             ylim=(0, 4.5), ylabel="Mean verified orders by six minutes (out of 4)", title="Delivery at the cutoff")
    left.legend(loc="upper center", bbox_to_anchor=(.5, -.16), ncols=2, frameon=False, fontsize=8)

    keys = (("reuse_cards", "elapsed"), ("novel_playbook", "elapsed"),
            ("reuse_cards", "first_capped"), ("novel_playbook", "first_capped"))
    metrics = [results["contrasts"][arm][field] for arm, field in keys]
    all_vals = [val for row in metrics for val in (0, *row["values"], *row["interval"])]
    for y, contrast in enumerate(metrics):
        offsets = [((i * 17) % 11 - 5) * .025 for i in range(len(contrast["values"]))]
        right.scatter(contrast["values"], [y + dy for dy in offsets], color="#05766d", alpha=.47, s=18)
        midpoint = contrast["mean"]
        lower, upper = contrast["interval"]
        right.errorbar(midpoint, y, xerr=[[midpoint - lower], [upper - midpoint]], fmt="o",
                       color="#182533", capsize=4, markersize=6)
    right.axvline(0, linestyle="--", linewidth=1, color="#818893")
    right.set(xlim=(min(all_vals) - 14, max(all_vals) + 14), ylim=(3.6, -.6), yticks=range(4),
              yticklabels=["Cards · whole menu", "Playbook · whole menu", "Cards · first craft",
                           "Playbook · first craft"], title="Time through event or cutoff",
              xlabel="Teacher material minus independent discovery (seconds)\nDots are matched puzzles. Bars are 95% bootstrap intervals.")
    for ax in (left, right):
        ax.spines[["top", "right"]].set_visible(False)
        ax.set_axisbelow(True)
    left.yaxis.grid(alpha=.2)
    right.xaxis.grid(alpha=.2)
    fig.suptitle("Learning hidden Minecraft recipes from teacher logs", fontsize=15)
    for output in ("pdf", "png"):
        fig.savefig(stem.with_suffix("." + output), facecolor="white", dpi=180)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("results", type=Path)
    parser.add_argument("stem", type=Path)
    args = parser.parse_args()
    render(json.loads(args.results.read_text()), args.stem)
