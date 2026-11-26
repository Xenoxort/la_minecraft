"""Plot the primary delivery counts and the secondary timing contrasts."""
import argparse
import json
from pathlib import Path

import matplotlib.pyplot as plt

NAMES = {"fixed": "Fixed handoffs", "peer": "Self-organizing", "leader": "Orchestrated"}
COLORS = {"fixed": "#596273", "peer": "#00736c", "leader": "#994a22"}


def render(data, stem):
    fig, (left, right) = plt.subplots(1, 2, figsize=(11, 4.4), width_ratios=(1, 1.13), layout="constrained")
    for idx, (mode, label) in enumerate(NAMES.items()):
        y = data["groups"][f"{mode}-normal"]["mean_orders"], data["groups"][f"{mode}-outage"]["mean_orders"]
        x = [n + (idx - 1) * .235 for n in (0, 1)]
        bars = left.bar(x, y, width=.216, color=COLORS[mode], label=label)
        left.bar_label(bars, labels=[f"{value:g}" for value in y], padding=3, fontsize=9)
    left.set(xticks=[0, 1], xticklabels=["All benches open", "Assembly outage"], ylim=(0, 11),
             ylabel="Mean orders delivered by 360 s (out of 10)", title="Deliveries by the deadline")
    left.legend(loc="upper center", bbox_to_anchor=(.5, -.115), frameon=False, ncols=3, fontsize=8)
    timing = data["leader_minus_peer_seconds"]
    rows = [timing[key] for key in ("normal", "outage", "interaction")]
    values = [v for row in rows for v in [*row["interval"], *row["values"], 0]]
    for i, row in enumerate(rows):
        center = row["mean"]
        errors = [[center - row["interval"][0]], [row["interval"][1] - center]]
        offsets = [((j * 13) % 11 - 5) * .023 for j in range(len(row["values"]))]
        right.scatter(row["values"], [i + dy for dy in offsets], color="#00736c", alpha=.54, s=18)
        right.errorbar(center, i, xerr=errors, fmt="o", color="#232b36", markersize=7, capsize=5)
    right.axvline(0, color="#7f8790", linewidth=1, linestyle="--")
    right.set(yticks=[0, 1, 2], yticklabels=["All benches open", "Assembly outage", "Outage minus open"],
              xlim=(min(values) - 12, max(values) + 12), ylim=(2.5, -.5),
              xlabel="Orchestrated minus self-organizing (seconds)\nDots are layouts. Bars show 95% bootstrap intervals.",
              title="Time differences on matched trials")
    for ax in (left, right):
        ax.spines[["top", "right"]].set_visible(False)
        ax.set_axisbelow(True)
    left.grid(axis="y", alpha=.21)
    right.grid(axis="x", alpha=.21)
    fig.suptitle("Hell’s Kitchen handoffs across ten matched layouts", fontsize=15)
    for ext in ("pdf", "png"):
        fig.savefig(stem.with_suffix("." + ext), dpi=180, facecolor="white")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("summary", type=Path)
    parser.add_argument("output_stem", type=Path)
    args = parser.parse_args()
    render(json.loads(args.summary.read_text()), args.output_stem)
