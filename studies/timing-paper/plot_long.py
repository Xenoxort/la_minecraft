"""Plot observed completion through the six-minute deadline."""
import argparse
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

SETTINGS = {
    "always": ("Always open", "#D55E00", "-"),
    "two_blocks": ("60 s per half", "#0072B2", "--"),
    "alternating": ("20 s on / 40 s off", "#009E73", "-"),
}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("results", type=Path)
    p.add_argument("output", type=Path)
    args = p.parse_args()
    rows = json.loads(args.results.read_text())["episodes"]
    fig, ax = plt.subplots(figsize=(8.1, 4.5))
    ax.set_axisbelow(True)
    for policy, (label, color, style) in SETTINGS.items():
        group = [r for r in rows if r["schedule"] == policy]
        completed = sorted(r["first_verified_s"] if r["first_verified_s"] is not None else 360
                           for r in group if r["success_360"])
        ax.step([0, *completed, 360], [0, *range(1, len(completed) + 1), len(completed)],
                where="post", linewidth=2.2, linestyle=style, color=color, label=label)
    ax.axvline(180, linestyle=":", linewidth=1.1, color="#555555")
    ax.text(184, 6.1, "Original deadline", fontsize=9, color="#555555")
    ax.set_xlim(0, 360)
    ax.set_ylim(0, 6.45)
    ax.set_xticks(range(0, 361, 60))
    ax.set_yticks(range(0, 7))
    ax.set_xlabel("Elapsed time (s)")
    ax.set_ylabel("Recipe sets completed (of 6)")
    ax.spines["right"].set_visible(False)
    ax.spines["top"].set_visible(False)
    ax.grid(axis="y", alpha=0.2)
    ax.legend(loc="upper left", frameon=False)
    fig.tight_layout()
    fig.savefig(args.output.with_suffix(".png"), dpi=220, facecolor="white")
    fig.savefig(args.output.with_suffix(".pdf"), facecolor="white")


if __name__ == "__main__":
    main()
